# Implementation Plan: v0.1

**Status:** Approved

Implements [Spec 001](spec.md) and the v0.1 parts of [Spec 003](../003-configuration/spec.md) (FR-19, FR-20, FR-21). Spec 002 is out of scope, but v0.1 emits the attributes it needs.

## 1. Technical decisions

| Area | Decision | Why |
|---|---|---|
| Python | Requires 3.11+, CI on 3.11 and the latest release | `tomllib` is in the standard library from 3.11 |
| Project tooling | `uv`, `src/` layout, `hatchling` build backend | Supports the `uvx eagain` install path in NFR-3 |
| Runtime dependencies | None for the core | Fast install, and a small supply chain for a tool that reads private logs |
| CLI | `argparse` | Enough for this interface, with no dependency |
| OTLP handling | Hand-written JSON reader and writer | We only need the JSON encoding of traces, so the OpenTelemetry SDK and protobuf packages would be unused weight |
| HTML reports | Standard library `string.Template`, with every value passing through one `html.escape` helper | Single file, no dependency. Tests assert the escaping (FR-7 AC3) |
| LLM | Optional extra, `eagain[anthropic]`, behind a provider interface | The core stays vendor-neutral and offline (FR-8 AC8, NFR-2) |
| Plugins | Python entry points: `eagain.rules`, `eagain.importers` | Add a rule or importer with no core change (NFR-5) |
| Quality tools | `pytest`, `hypothesis`, `ruff`, `mypy --strict`, GitHub Actions | Property tests suit determinism and fingerprints |

Dev-only dependencies include `jsonschema`, used to test published schemas.

## 2. Code structure

```
src/eagain/
  cli.py            Commands, exit codes
  config/           One settings definition, loading, origin tracking, project config limits
  semconv.py        Pinned versions and every attribute name
  otlp/             Read, write and validate OTLP JSON Lines
  normalise.py      OTLP spans -> internal model. The only reader of gen_ai.* names
  model.py          Session, Step, ToolCall, ModelCall, Outcome
  importers/        Importer interface, claude_code.py
  redact.py         Redaction patterns
  fingerprint.py    Error text normalisation and hashing
  rules/            Rule interface, registry, one module per rule
  metrics.py        FR-5
  recommend.py      FR-6 templates and ranking
  report/           Terminal, Markdown, HTML, JSON
  explain/          Optional LLM explainer
schemas/            Published JSON schemas for reports
tests/fixtures/     Synthetic data only
```

Dependency direction: `rules`, `metrics` and `report` import `model`, never `otlp`, `semconv` or `importers`. A test enforces this, because it is what keeps a conventions change contained.

## 3. Key mechanisms

**Pipeline.** Importers yield OTLP-shaped spans. `analyze --from claude-code` passes these straight to the normaliser, and `import` writes the same spans to disk. Both routes share one code path, so a file and a direct run give the same findings.

**Order of text processing.** Redact, then fingerprint, then truncate. Truncating first could cut a secret in half so that its pattern no longer matches. Fingerprinting after redaction means no secret ever feeds a hash.

**Determinism.** Spans are sorted by `(start time, span ID)` after loading, so line order cannot matter. IDs are the first bytes of a SHA-256 hash of source identifiers: trace ID from the session ID, span ID from the session ID, record UUID and span kind. Finding IDs hash the rule ID and fingerprint. Only `generated_at` may differ between runs, and it sits in a metadata block.

**Memory.** Text is bounded as it is loaded, and sessions are released after their rules run. Cross-session rules keep only fingerprints, counts and cited IDs.

**Rule interface.** Session rules take a `Session` and config, and return findings. Run rules take per-session summaries. A rule declares what data it requires, so the engine can report "not evaluated" (FR-4) with no logic inside the rule.

**Settings.** One typed definition holds each setting's name, default, validation and whether project config may set it. Validation, `config show`, `config init` and generated docs all read from it (FR-19 AC9).

**Project identity in v0.1.** The importer sets `eagain.project.id` and `eagain.project.id_source`, using the sources in Spec 002 except explicit config. Sharing, `link`, and approximate commit lookup wait for v0.2.

## 4. Tasks

Each milestone ends with its acceptance tests passing. Tasks are in order.

### M1 Format (FR-1, FR-2, FR-19 to FR-21)

1. Project scaffold, `.gitignore`, CI, and a stub `eagain --version`. Package metadata declares `Apache-2.0`, matching `LICENSE`.
2. Settings definition and loader: sources, precedence, origin tracking, typo warnings, project config limits, `config show`, `validate` and `init`.
3. `semconv.py` with pinned versions.
4. OTLP reader and writer: attribute value decoding, integer-as-string timestamps, hex IDs.
5. `eagain validate`, including the logs and metrics rejection.
6. Internal model and normaliser, including outcome and error text resolution.
7. Synthetic fixture generator and the fictional-agent fixture.
8. Capture the real OTLP fixture once: OpenTelemetry Python SDK through a Collector with its file exporter, using made-up content.
9. Test gate: corpus registry and fetcher (standard library only, hash-checked, cached), the oracle script and its first expected counts, CI caching, the `live` marker, count-only assertion helpers, and the spec coverage report.
10. Turn on branch protection for `main`, requiring the CI checks. This changes repository settings, so it needs the owner's approval when it is done.

### M2 Analysis (FR-4, FR-5, FR-9)

1. Redaction, with one test per built-in pattern, including split and encoded near-misses.
2. Fingerprinting, with property tests that varying paths, numbers, UUIDs, hex and timestamps keeps the same hash.
3. Rule engine and the ten default rules, each with firing and non-firing tests.
4. Recovery detection and wasted steps.
5. Suppressions, thresholds and the settings hash.
6. Metrics, JSON report with schema, terminal summary, `eagain analyze`, exit codes and `--fail-on`.

### M3 Real logs (FR-3)

1. Finish settling the mapping from section 6: what a rejected `permissionDecision` looks like, and where compaction appears. If compaction is never recorded, `context-pressure` is reported as not evaluated for Claude Code, and the spec says so.
2. Write synthetic fixtures that copy the structures found, covering both transcript generations.
3. Implement the importer: joining a session's files under both subagent layouts, pairing calls and results, usage, thinking counts, and skip counts by record type.
4. Project identity from local repository data, with no repository-defined commands run. Strip credentials from remote URLs.
5. Bring the corpus tier to full oracle agreement on all four corpora.
6. Hand-check a sample of 30 high-severity findings from the primary corpus, aiming for at least 90% judged correct, then tune thresholds on the corpora. Record only aggregates and finding IDs.
7. Run the live tier and record its summary.

### M4 Reports (FR-6, FR-7)

1. Recommendation templates and fixed ranking.
2. Markdown report.
3. Self-contained HTML report, with a test that planted `<script>` content comes out escaped and that the file references nothing external.
4. Coverage section, and `--since`.
5. Spec 001 end-to-end scenario as an automated test, run with network access blocked.

### M5 LLM (FR-8)

1. Provider interface and a fake provider for tests.
2. Excerpt selection within budget, reusing redaction.
3. Pre-send summary, confirmation and `--yes`.
4. Citation check, separate labelled output, and failure fallback.
5. Anthropic provider as an optional extra. The model is user-configured and has no hard-coded default that can go stale.
6. Tests that a planted instruction in a transcript changes no findings and causes no action.

### M6 Release

1. Contributor guides for rules and importers, with a sample plugin in tests.
2. Generated settings docs, and a README updated with real commands and output.
3. Performance test against NFR-1 and NFR-12, using a generated 100 MB input.
4. Reserve the PyPI name, then publish. Do a trademark search first.
5. Update `CLAUDE.md` with real commands.

## 5. Verification and gates

### Test tiers

| Tier | Data | When it runs | Network | Gate |
|---|---|---|---|---|
| **Unit** | Synthetic fixtures in the repository | Every commit, locally and in CI | None | Required for every pull request |
| **Corpus** | Public Hugging Face datasets, pinned to a revision | Every pull request in CI, with downloads cached | Download step only, before tests start | Required for every pull request |
| **Live** | The developer's own `~/.claude/projects` | Locally, before each milestone is signed off and before release | None | Required for milestone sign-off. Never runs in CI |

Unit tests check behaviour precisely. Corpus tests show that the tool holds up on real sessions written by other people. Live tests catch format changes, because the public datasets come from older Claude Code versions than the ones in use now.

### Corpora

| Corpus | Revision | License | Contents | Claude Code versions | Role |
|---|---|---|---|---|---|
| [`armand0e/claude-fable-5-claude-code`](https://huggingface.co/datasets/armand0e/claude-fable-5-claude-code) | `7388ef9` | MIT | 63 files, 75 MB, 55 sessions, 8 subagent files | 2.1.170 to 2.1.176 | Primary: oracle checks, snapshots, performance |
| [`AlinCiocan/fable-5-claude-code-traces`](https://huggingface.co/datasets/AlinCiocan/fable-5-claude-code-traces) | `e33ebbc` | CC BY 4.0 (credit in docs) | 18 files, 50 MB | 2.1.173 | Second source from a different user |
| [`crispwisp/wisp-claude-code-sessions`](https://huggingface.co/datasets/crispwisp/wisp-claude-code-sessions) | `c2c90b5` | MIT | 104 small files, 25 MB, nested in per-project folders | 2.1.168 | Directory layout like `~/.claude/projects`, and a different model |
| [`choucsan/mimo-claude-code-traces-1k`](https://huggingface.co/datasets/choucsan/mimo-claude-code-traces-1k) | `39cc3fc` | MIT | 1,017 files, 41 MB | Version field overwritten by the publisher | Robustness only: altered fields, a non-Claude model, many files |

Only datasets with an explicit license are used. Others found in the search, such as `nlile/misc-merged-claude-code-traces-v1`, have none and are excluded. The registry lives in `tests/corpora/registry.toml`: dataset, revision, license, and a SHA-256 for every file. A hash mismatch fails the run.

### What corpus tests check

1. **Accounting:** every source record is either imported or counted as skipped by type, and the totals match the source line counts exactly.
2. **Oracle agreement:** the number of tool results, errors, interrupts, permission denials, API errors and subagent runs matches an independent oracle script, which shares no code with `eagain`. The oracle's numbers were first checked by hand on a sample, and are committed as `tests/corpora/<corpus>.expected.json`, holding numbers only.
3. **Spec guarantees across the whole corpus:** identical output on repeat and on shuffled input, no network use, source files unchanged, a canary secret planted in a temporary copy absent from all outputs, HTML escaping, and valid JSON against the published schemas.
4. **Snapshots:** finding counts per rule and the headline metrics. A change fails the test until the snapshot is updated, and the pull request explains why.
5. **Performance:** time and peak memory on the primary corpus, extrapolated to check NFR-1.
6. **Damaged input:** temporary copies with a truncated last line and a corrupted middle line are handled as Spec 001 requires.

### Live tests

`pytest -m live` runs the same accounting, determinism, source safety and no-network checks on the developer's own logs. It reports aggregates only: sessions, records by type, skip counts, findings per rule, and run time. It also fails if records of unknown types make up more of the data than a set threshold, because that signals a new transcript format. The aggregate summary is pasted into the milestone sign-off.

### Definition of done

A task's pull request merges only when:

1. `ruff`, `mypy --strict` and unit tests pass.
2. The corpus tier passes, and any snapshot change is explained.
3. Every acceptance criterion the task touches has a test named after it (`test_fr4_ac3_...`). A spec coverage report, built from these names, shows no gaps for finished milestones.

CI enforces points 1 to 3, and branch protection on `main` requires them. A milestone is signed off only after the live tier also passes, with its summary recorded.

### Handling real data

- Never commit corpus files or excerpts from them. Commit only revisions, file hashes and counts.
- Test output and failure messages show IDs and counts, never transcript text. Tests on corpus data use assertion helpers that compare counts, because pytest's default assertion messages would print the values being compared.
- Corpus files are untrusted input. They are parsed and never executed, and LLM tests never use them.
- If a download fails, CI fails. Locally the corpus tier is skipped with a clear message, unless `EAGAIN_REQUIRE_CORPORA=1` is set, so a gate is never passed by skipping silently.

### Other checks

| Check | Approach |
|---|---|
| Network | A test fixture fails on any socket use, except in explicit LLM tests that use the fake provider |
| Source safety | Run against read-only copies and assert that source hashes are unchanged |
| Secrets | A planted canary key must be absent from all outputs |

## 6. What the data already shows

A first look at the primary corpus and at local logs, counting structure only, answers part of M3 task 1:

| Signal | What was found | Effect on the importer |
|---|---|---|
| Tool errors | `is_error` on 191 of 4,166 tool results in the primary corpus | Maps directly to `outcome: error` |
| Permission denials | 20 error results with denial wording. Newer versions also have a `permissionDecision` field, but only `accept` values have been seen | Detect from both. Confirm what a rejection looks like |
| User interrupts | 43 `[Request interrupted by user` markers | Becomes `eagain.interrupt` |
| API errors | 5 `system` records with subtype `api_error`, and 59 assistant records flagged `isApiErrorMessage` with model `<synthetic>` | `runtime-error`. Synthetic records are not counted as model calls |
| Compaction | Not seen in any sample | `context-pressure` cannot be tested on real data yet. Needs a source that contains it |
| Subagents | Top-level `agent-*.jsonl` files in the dataset, but a `subagents/` folder in current local logs | Support both layouts |
| Format drift | Datasets are 2.1.168 to 2.1.176. Local logs are 2.1.316, and add `api-request*`, `atis-latch` and `permissionDecision` records | Live tests are the only check on the newer format |
| Large content | Edit results include `originalFile`, the whole file before the edit | Never store it. Keep only the diff excerpt |

## 7. Open items

1. **Transcript details.** How denials, interrupts and compaction appear is confirmed in M3 task 1. If one is not recorded, the matching rule is reported as not evaluated for Claude Code, and the spec is updated to say so.
2. **Collector availability.** M1 task 8 needs a Collector binary or container once. The captured file is committed, so CI does not need it.
