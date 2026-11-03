# Implementation Plan: v0.1

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

### M2 Analysis (FR-4, FR-5, FR-9)

1. Redaction, with one test per built-in pattern, including split and encoded near-misses.
2. Fingerprinting, with property tests that varying paths, numbers, UUIDs, hex and timestamps keeps the same hash.
3. Rule engine and the ten default rules, each with firing and non-firing tests.
4. Recovery detection and wasted steps.
5. Suppressions, thresholds and the settings hash.
6. Metrics, JSON report with schema, terminal summary, `eagain analyze`, exit codes and `--fail-on`.

### M3 Real logs (FR-3)

1. Inspect real transcript structure, without committing any of it, to settle the mapping for permission denials, interrupts, compaction and subagent files. Spec 001 requires these, but how each appears in transcripts is not yet confirmed.
2. Write synthetic fixtures that copy that structure.
3. Implement the importer: joining a session's files, pairing calls and results, subagents, usage, thinking counts, and skip counts by record type.
4. Project identity from local repository data, with no repository-defined commands run. Strip credentials from remote URLs.
5. Run on real local sessions, compare a sample against the transcripts by hand, and tune thresholds. Record the results as aggregates only.

Sessions on this machine are few, so threshold tuning here is provisional.

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

## 5. Test strategy

| Layer | Approach |
|---|---|
| Acceptance | One test per AC, named after it (`test_fr4_ac3_...`), so spec coverage can be listed mechanically |
| Determinism | Run twice and with shuffled input, compare bytes |
| Network | A test fixture fails on any socket use, except in explicit LLM tests that use the fake provider |
| Source safety | Run against read-only copies and assert that source hashes are unchanged |
| Secrets | A planted canary key must be absent from all outputs |
| Real logs | Never in CI or the repository. Local checks only, reporting aggregates |

## 6. Open items

1. **Transcript details.** How denials, interrupts and compaction appear is confirmed in M3 task 1. If one is not recorded, the matching rule is reported as not evaluated for Claude Code, and the spec is updated to say so.
2. **Collector availability.** M1 task 8 needs a Collector binary or container once. The captured file is committed, so CI does not need it.
