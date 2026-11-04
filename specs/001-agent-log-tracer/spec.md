# Spec 001: Agent Log Tracer

| | |
|---|---|
| **Status** | Approved |
| **Name** | `eagain` (exact name free on PyPI and npm when checked; not yet reserved, no trademark search done) |
| **Scope** | First release (v0.1) |
| **Constraints** | Python 3.11+; OpenTelemetry as the trace format |

This spec says *what* the tool does and how we know it works. Libraries and code structure belong in the implementation plan that follows it.

## 1. Problem

Coding agents leave long transcripts that almost nobody reads. The same mistakes therefore repeat across sessions: the same failing command, the same retry loop, the same missing setup. Developers notice a bad session, but they cannot easily see which failures recur, what they cost, or what to change to stop them.

## 2. Goal

An open-source command-line tool that a developer can point at agent session logs to answer four questions:

1. **What went wrong?** Failures in a session, each linked to the spans that prove it.
2. **What keeps going wrong?** The same failure recurring within and across sessions.
3. **What did it cost?** Steps spent on failures, and whether the agent recovered.
4. **What should change?** Concrete, prioritised improvements.

### Primary user

A developer who uses coding agents and wants to improve their setup (instructions, hooks, tooling, environment). They run the tool locally on their own logs.

### Non-goals for v0.1

- Adding any logging, hooks or instrumentation to agents. The tool reads what agents already record
- Hosted service, accounts, team aggregation, or acting as an OTLP network receiver
- OpenTelemetry logs and metrics as input (traces only)
- Web dashboard or live session monitoring
- Automatically editing agent configuration (the report suggests changes; the developer applies them)
- Judging code quality of what the agent produced
- Native importers for every agent (see FR-3)
- Persistent history, search and automation suggestions (see [Spec 002](../002-work-history-search/spec.md))

## 3. Principles

- **Local by default.** Nothing leaves the machine unless the user opts in to a specific LLM provider for a specific run.
- **Evidence over opinion.** Every finding cites the spans behind it.
- **Deterministic core.** Rules produce the same findings from the same input. The LLM layer only adds to them and is never required.
- **Agent-neutral core.** Analysis contains no agent-specific logic.
- **Standard at the boundary, stable inside.** OpenTelemetry is the external format, but the rules read a small internal model. The GenAI conventions are still changing, and a change to them should touch only the mapping layer.

## 4. Architecture

```
Claude Code transcripts -> Importer -+
                                     +-> OTLP JSONL -> Normaliser -> Internal model -> Rule engine -> Findings -> Report
Any OTel GenAI producer -------------+                                                                  |          ^
                                                                                                        v          |
                                                                                                Optional LLM explainer
```

Importers are the only agent-aware components. Importing can also happen in memory, so analysing Claude Code sessions does not require an intermediate file.

## 5. Trace format

The input contract is OpenTelemetry trace data in the [OTLP File format](https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/) (JSON Lines, one `resourceSpans` object per line), using the [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai).

Both are still at Development stability, which has three consequences:

- The tool pins one conventions version or commit and records it in every report.
- Lines are not guaranteed to be ordered, so spans are assembled by `traceId` and `parentSpanId` rather than by file position.
- The mapping below has been checked against the pinned versions: `semantic-conventions-genai` commit `9d1e748` (which has no tagged release yet), and `semantic-conventions` v1.45.0 for `vcs.*` and `error.type`. Moving to a newer version means re-checking it.

### Mapping

| Concept | OpenTelemetry representation |
|---|---|
| Session | One trace, with a root span with `gen_ai.operation.name = invoke_agent` and `gen_ai.conversation.id` set to the session ID |
| Agent identity | `gen_ai.provider.name` (required by the conventions), `gen_ai.agent.name`, `gen_ai.agent.id`, `gen_ai.agent.version` |
| Subagent run | Child `invoke_agent` span. Its descendants belong to that subagent |
| Model call | `chat` span with `gen_ai.request.model` and `gen_ai.usage.input_tokens`, `output_tokens`, `cache_read.input_tokens`, `cache_write.input_tokens` |
| Repository | `vcs.repository.url.full`, `vcs.ref.head.name`, `vcs.ref.head.revision` with any credentials removed. These are at release candidate stability |
| Tool call | `execute_tool` span with `gen_ai.tool.name`, `gen_ai.tool.call.id`, and `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`, which are opt-in, so third-party traces may omit them |
| Skill load | `execute_tool` span with `gen_ai.skill.name` |
| Failure | Span status `ERROR` plus `error.type`, with an optional `gen_ai.client.operation.exception` event |
| Compaction | `gen_ai.conversation.compacted = true` on later model calls, plus an `eagain.compaction` event from importers that can see the moment it happened |
| Message and reasoning content | Optional `gen_ai.client.inference.operation.details` event with `gen_ai.input.messages` and `gen_ai.output.messages`. Reasoning uses the conventions' `reasoning` message part. Rules never require them |

### Extensions

The conventions do not cover everything the rules need. Additions use the `eagain.` prefix and are always optional, so third-party traces remain valid without them.

| Name | Kind | Meaning |
|---|---|---|
| `eagain.tool.outcome` | Span attribute | `ok`, `error`, `denied` or `unknown` |
| `eagain.interrupt` | Span event | The user stopped the agent mid-turn |
| `eagain.compaction` | Span event | The moment the agent's context was summarised or truncated. The conventions only mark calls that used a compacted context, so without this event each change from uncompacted to compacted counts as one compaction |
| `eagain.source.*` | Span attribute | Pointer to the source record, for tracing evidence back |
| `eagain.project.id`, `eagain.project.id_source` | Span attribute | Stable project identity, set per span because one session can span several directories (defined in Spec 002) |
| `eagain.cwd` | Span attribute | Working directory for the span |
| `eagain.turn.id` | Span attribute | Groups spans under the user request that caused them (used by Spec 002) |
| `eagain.skill` | Span attribute | Skill active for this span, when recorded. `gen_ai.skill.name` only covers the call that loaded the skill (used by Spec 002) |

### Determining a tool's outcome

Applied in order:

1. Use `eagain.tool.outcome` if present.
2. Status `ERROR` or an `error.type` attribute means `error`.
3. Otherwise `ok`, because OpenTelemetry instrumentation normally leaves the status unset on success.

Importers set `unknown` explicitly when a call has no recorded result, for example when a session was cut off.

### Error text for fingerprints

Use the first available of: status message, the `exception.message` of an `exception` or `gen_ai.client.operation.exception` event, the tool result, `error.type`. Producers that omit content yield coarser fingerprints, and the report's coverage section says when this happened.

## 6. Functional requirements

### FR-1 Trace validation

`eagain validate <file>` checks a file against the OTLP JSON structure and the GenAI expectations above.

- **AC1:** A valid file exits 0 and prints trace, span and `execute_tool` counts.
- **AC2:** Malformed OTLP exits 2 and reports the line number and reason for each error.
- **AC3:** A span whose parent is missing, or spans with no `gen_ai.operation.name`, produce warnings rather than errors. Traces can be partial and can contain unrelated spans.
- **AC4:** A logs or metrics file exits 2 with a message saying that only traces are supported.

### FR-2 Generic ingestion

Any producer writing OTLP JSON traces with GenAI conventions can be analysed with no code changes to the tool.

- **AC1:** A fixture for a fictional agent, using no `eagain.*` extensions, yields `tool-failure`, `repeated-error` and `recurring-failure` findings.
- **AC2:** A fixture captured once from real OpenTelemetry tooling (the Collector's file exporter), then committed, loads with no errors. This proves we read real OTLP, not only our own output.
- **AC3:** Non-GenAI spans are ignored and counted in coverage.

### FR-3 Claude Code importer

Claude Code already records its sessions under `~/.claude/projects` as JSONL. The importer reads those files in place and translates them to the mapping in section 5. It adds no logging, and needs no Claude Code configuration, so existing history can be analysed immediately.

Commands: `eagain import claude-code [path] -o <out.jsonl>`, or directly `eagain analyze --from claude-code [path]`. The path defaults to `~/.claude/projects`. The importer interface is documented so others can be contributed.

- **AC1:** Tool calls and results are paired into `execute_tool` spans, and error results map to `outcome: error`.
- **AC2:** Records marked as sidechain become child `invoke_agent` spans and are not mistaken for the main agent.
- **AC3:** Permission denials map to `outcome: denied`, not `error`.
- **AC4:** Token usage on assistant records maps to `gen_ai.usage.*`, including cache read and cache write tokens. Cached tokens are most of the volume in real sessions, so totals without them would mislead.
- **AC5:** Unknown record types are skipped and counted, never fatal. The source format is not a public contract and contains many internal record types.
- **AC6:** A truncated final line is tolerated with a warning.
- **AC7:** Trace and span IDs are derived from source identifiers, so re-importing the same files gives byte-identical output.
- **AC8:** Source files are only ever read.
- **AC9:** Thinking blocks with text become `reasoning` message parts. Blocks with empty text, which are common, are counted only. Coverage reports both counts.
- **AC10:** User prompts, final responses, session titles, working directory per record and git branch are preserved, and spans carry the project, turn and skill attributes where available. Spec 002 depends on this, so the importer must not need rewriting for it.

Claude Code's own OpenTelemetry export is a separate path and not the v0.1 source. Its detail is opt-in, tool output requires its beta tracing, it does not export thinking, and it does not cover sessions from before it was enabled.

### FR-4 Rule engine

Rules read the internal model and emit findings. The default rule set is:

| Rule ID | Fires when | Category | Default severity |
|---|---|---|---|
| `tool-failure` | A tool's outcome is `error` | tool | low |
| `repeated-error` | Same error fingerprint at least 3 times in a session | behaviour | medium |
| `retry-loop` | Same tool with same normalised arguments at least 3 times in a session, with at least one failure | behaviour | high |
| `unresolved-failure` | The last call to a tool in a session failed and no later call to that tool succeeded | behaviour | high |
| `recurring-failure` | Same error fingerprint in at least 2 sessions | systemic | high |
| `permission-denied` | A tool's outcome is `denied` | permission | low |
| `user-interrupt` | An `eagain.interrupt` event occurs | behaviour | medium |
| `subagent-failure` | A child `invoke_agent` span has status `ERROR` | behaviour | medium |
| `runtime-error` | A `chat` span has status `ERROR` (rate limit, API or context-limit errors) | environment | medium |
| `context-pressure` | At least 2 `eagain.compaction` events in a session | context | low |

Thresholds and severities can be configured, and rules can be disabled. Rules that need an extension simply do not fire without it, and the report lists them as not evaluated. `retry-loop` is also listed as not evaluated when arguments are absent.

**Error fingerprint:** a hash of the tool name plus the error text after normalising paths, numbers, UUIDs, hex strings and timestamps. Two errors that differ only in those values share a fingerprint.

- **AC1:** Running twice on the same input and settings gives byte-identical findings, regardless of line order in the file. Settings are defined in [Spec 003](../003-configuration/spec.md).
- **AC2:** Each finding has a stable ID, rule ID, severity, category, session IDs, and at least one cited `traceId` and `spanId`.
- **AC3:** `File not found: /a/x.ts` and `File not found: /b/y.ts` from the same tool share a fingerprint.
- **AC4:** A failure followed by success of the same tool on the same normalised arguments is marked `recovered`, and the steps between them are counted as wasted steps.
- **AC5:** A session matching no rule produces no findings and is still counted as analysed.
- **AC6:** Findings can be suppressed by rule, fingerprint or project through a config file, and the report shows how many were suppressed. This handles expected failures, such as a search with no matches or a test written to fail first.

### FR-5 Metrics

For each session and for the whole run, report: sessions analysed, tool calls, failure rate, recovery rate, wasted steps, top failing tools, and tokens when present.

- **AC1:** Failure rate is `error` outcomes divided by all outcomes. `denied` and `unknown` are reported separately and excluded from the numerator.

### FR-6 Recommendations

Each high-priority finding group gets a recommended action from a rule-based template, for example "This command failed in 6 sessions: document the correct invocation in the agent's instructions or add a pre-flight check."

- **AC1:** Findings are ranked by severity, then session count, then wasted steps, with a fixed tie-break.
- **AC2:** Recommendations are available with no LLM configured.

### FR-7 Reports

`eagain analyze <paths...> [--since <date>] [--format md,html,json] [--out <dir>]` prints a terminal summary and writes reports.

Report order: headline metrics, top recommendations, recurring failures across sessions, per-session breakdown with evidence, then coverage (skipped records, ignored spans, rules not evaluated, suppressions, conventions version).

- **AC1:** JSON output has a published, versioned schema.
- **AC2:** Exit codes: 0 analysed successfully (even with findings), 1 runtime error, 2 invalid input. An optional `--fail-on <severity>` exits 3 when matched, for CI use.
- **AC3:** HTML is one self-contained file with no network requests, and all transcript content is escaped.
- **AC4:** Reports state their coverage so that a clean result cannot hide skipped data.

### FR-8 Optional LLM explainer

`--explain` sends the top finding groups to a configured LLM to get root-cause hypotheses and improvement suggestions, including failures rules cannot see, such as the agent ignoring an instruction. Reasoning text, when recorded, is available to it as evidence.

- **AC1:** Off by default. With no provider configured, `--explain` exits with a clear message and sends nothing.
- **AC2:** Before sending, the tool shows the provider, number of findings, approximate size and estimated tokens, and asks for confirmation. `--yes` skips the prompt.
- **AC3:** Only redacted excerpts around cited spans are sent, not whole transcripts, within a configurable budget.
- **AC4:** LLM content is visibly labelled as generated and kept separate from rule findings. It never alters them.
- **AC5:** Each LLM suggestion must cite a finding ID. Suggestions citing unknown IDs are dropped and counted.
- **AC6:** If the LLM call fails, the report is still written with rule findings and a note about the failure.
- **AC7:** Transcript text is treated as untrusted data. Instructions inside it cannot trigger tool actions, because the explainer has no tools, and its output is escaped like all other content.
- **AC8:** The provider sits behind an interface. The core has no dependency on one vendor.

### FR-9 Redaction

Transcripts routinely contain secrets, so redaction applies to all excerpts in reports, all LLM input and all imported OTLP output.

- **AC1:** Common credential patterns (API keys, bearer tokens, private keys, `.env`-style assignments) are replaced with `[REDACTED:<kind>]`.
- **AC2:** Users can add patterns through config.
- **AC3:** Source log files are never modified.
- **AC4:** Reports state that redaction is best-effort and should be reviewed before sharing.

## 7. Non-functional requirements

- **NFR-1 Performance:** Analyse 100 MB of logs in under 60 seconds on a typical laptop. Long content is truncated to a bounded excerpt when loaded, so memory does not grow with transcript size.
- **NFR-2 Offline:** Everything except `--explain` works with no network and makes no network calls, including telemetry.
- **NFR-3 Install:** One-command install on macOS and Linux using `uvx` or `pipx`, with no required services.
- **NFR-4 Test data:** Repository fixtures are entirely synthetic. Real transcripts are never committed.
- **NFR-5 Extensibility:** A contributor can add a rule or an importer without changing the core, following a documented guide.
- **NFR-6 Robustness:** One malformed session never aborts a multi-session run. It is reported in coverage.

## 8. End-to-end acceptance scenario

Given a synthetic set of 5 Claude Code sessions, in which:

- 3 sessions fail with the same error differing only by path,
- 1 session contains a 4-attempt retry loop that recovers,
- 1 session is clean, and
- 1 file has a truncated last line,

when `eagain analyze --from claude-code` runs with no network available, then:

1. It exits 0, and all formats are written.
2. One `recurring-failure` group covers the 3 sessions and ranks first, with a recommendation.
3. The retry loop is reported as `recovered`, with its wasted steps counted.
4. The clean session counts as analysed with no findings.
5. The truncation appears in coverage.
6. A fake API key planted in a failing output appears in no report.
7. A second run produces identical JSON apart from the generation timestamp.
8. Importing the same sessions to a file with shuffled lines and analysing that file gives the same findings.

## 9. Milestones

1. **M1 Format:** pin the conventions, verify the mapping, build the OTLP reader, normaliser, `validate` and synthetic fixtures (FR-1, FR-2).
2. **M2 Analysis:** rule engine, metrics, JSON and terminal output (FR-4, FR-5, FR-9).
3. **M3 Real logs:** Claude Code importer (FR-3). This is the first check of the rules against real sessions, so expect to tune thresholds here.
4. **M4 Reports:** recommendations, Markdown and HTML (FR-6, FR-7).
5. **M5 LLM:** optional explainer (FR-8).
6. **M6 Release:** packaging, contributor guides, public v0.1.

## 10. Risks

| Risk | Mitigation |
|---|---|
| GenAI conventions or the OTLP file format change | Pin a version, isolate mapping in the normaliser, record the version in reports |
| Few producers emit GenAI spans with the detail rules need | Rules degrade visibly (coarser fingerprints, rules listed as not evaluated); the bundled importer covers the first use case |
| Noisy findings make people stop reading | Group by fingerprint, rank strictly, support suppressions, tune in M3 |
| Claude Code transcript format changes without notice | Tolerant importer, skip counts in coverage, version-tagged fixtures |
| Agents clean up old local transcripts, shrinking history | Document it. Saved OTLP exports can be analysed later |
| Secrets leak through reports, exports or the LLM | Redact by default, send excerpts only, confirm before sending, state the limits |
| Reasoning text is mostly unavailable | Rules never depend on it; coverage reports how much was present |

## 11. Open questions

1. **Name reservation.** Reserve `eagain` on PyPI and do a trademark search before public release. The license is Apache-2.0.
2. **Second importer.** Codex and Gemini CLI are the obvious candidates after v0.1. Claude Code's native OpenTelemetry output could also be supported once its tracing leaves beta.
