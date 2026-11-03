# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`eagain` (repo: `agentMaster`) is a planned open-source Python 3.11+ CLI that analyses coding-agent session logs. It reports failures, finds similar past work, and suggests automation.

The project is at the spec stage: there is no code, build, lint or test setup yet. The `eagain` commands in the specs describe intended behaviour and do not exist yet. Replace this paragraph with real commands, including how to run a single test, once tooling exists.

## Spec-driven development

The specs in `specs/` are the source of truth, and all three are approved. Releases go in spec order: v0.1, then v0.2, then v0.3.

| Spec | Covers | Release |
|---|---|---|
| `001-agent-log-tracer` | OTLP format and mapping, Claude Code importer, rule engine, reports, LLM explainer, redaction | v0.1 |
| `002-work-history-search` | Local store, project identity, search, automation suggestions | v0.2, v0.3 |
| `003-configuration` | Settings, project config limits, protected behaviour, retention | v0.1 to v0.3 |

- Requirement numbers continue across specs (`FR-n`, `NFR-n`, each with `ACn` acceptance criteria), so cite them by number. FR-17 appears before FR-15 in Spec 002.
- Each spec ends with an end-to-end acceptance scenario, which is the main definition of done.
- Technical decisions, code structure and task order for v0.1 are in `specs/001-agent-log-tracer/plan.md`.
- The trace mapping is pinned to specific OpenTelemetry convention versions (Spec 001 section 5, `src/eagain/semconv.py` once it exists). Re-check it before moving to a newer version.

## Architecture

```
Claude Code transcripts -> Importer -+
                                     +-> OTLP JSONL -> Normaliser -> Internal model -> Rule engine -> Findings -> Report
Any OTel GenAI producer -------------+                                                                  |          ^
                                                                                                        v          |
                                                                                                Optional LLM explainer
```

Design points that span several specs:

- **Importers are the only agent-aware code.** Analysis must stay agent-neutral.
- **Rules read the internal model, not OTel attributes.** The GenAI conventions and the OTLP file format are at Development stability, so changes to them should touch only the normaliser.
- **Rules are deterministic, and the LLM is additive.** The same input and settings give byte-identical findings, regardless of line order. LLM output never alters findings.
- **The store has three layers.** The trace layer (redacted, bounded spans) and the state layer (user decisions) cannot be rebuilt once transcripts are gone. The derived layer can, using `reindex`, so anything recomputable belongs there and records its algorithm version.
- **Project identity and sharing are separate.** The project ID is set per span, because one session can span several directories. Sharing is checked at query time and is never written onto traces.

## Rules that must hold

- Spec 003 FR-21 lists guarantees that no setting may change, including: source logs are read-only, hooks and rules are never installed automatically, and there are no network calls except an explicitly requested LLM run.
- A repository's `.eagain.toml` is untrusted, and Spec 003 FR-20 restricts what it can set.
- Text from transcripts is untrusted: redact it before storing it, escape it in reports, mark it in search results, and never copy it into rule drafts.
- Test fixtures must be synthetic. Never commit real transcripts.
- The Claude Code transcript format is not a public contract, so the importer must count and skip unknown record types rather than fail.
