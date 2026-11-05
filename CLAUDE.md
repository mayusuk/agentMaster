# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`eagain` (repo: `agentMaster`) is a planned open-source Python 3.11+ CLI that analyses coding-agent session logs. It reports failures, finds similar past work, and suggests automation.

Implementation has started (v0.1, milestone M1). So far `eagain --version` and `eagain config show|validate|init` work, and the other commands in the specs are not built yet. `docs/settings.md` is generated from the settings definition by `uv run python scripts/gen_settings_docs.py`, and a unit test fails when it is out of date.

## Commands

```sh
uv sync                                  # install dev dependencies
uv run ruff check . && uv run ruff format --check .
uv run mypy                              # strict, covers src, tests and scripts
uv run pytest                            # unit tests; live tests are excluded by default
uv run pytest tests/test_cli.py::test_version_flag   # one test
uv run python tests/corpora/corpus_fetch.py fetch   # download and verify the pinned corpora (~190 MB, into .corpora/)
EAGAIN_REQUIRE_CORPORA=1 uv run pytest -m corpus     # corpus tier; without the variable, missing data skips
uv run pytest -m live                    # live tier on your own ~/.claude/projects
uv run python scripts/spec_coverage.py   # criteria and their tests; fails on gaps in finished milestones
uv build
```

CI (`.github/workflows/ci.yml`) runs lint, types and unit tests on Python 3.11 and 3.14, a `corpus` job that downloads the corpora (cached) and runs the corpus tier, and the spec coverage report. A milestone counts as finished when the line after its heading in a plan reads `**Status:** Finished`. Tests cannot open network connections unless they are marked `network`.

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
- Committed test fixtures must be synthetic. Real data comes only from the pinned Hugging Face corpora and local live runs. Never commit it, quote it, or print its text in test output (plan section 5).
- The Claude Code transcript format is not a public contract, so the importer must count and skip unknown record types rather than fail.

## Gate for all work

Work is done only when the plan's definition of done is met: lint, type checks and unit tests pass, the corpus tier passes against real datasets with any snapshot change explained, and every acceptance criterion touched has a test named after it. A milestone also needs a live run on local logs. Never pass the gate by skipping the corpus tier.

## Issue workflow

GitHub issues are the only task tracker. Work goes through the user-level `plan-work` and `work-issue` skills, which use `~/.claude/skills/work-issue/scripts/wf.py`. This repository's settings for them are in `.wf.toml`: the files to read, the checks (including the corpus tier, once it exists) and the FR/AC test-name rule. Plans go in `docs/plans/`, and their tasks become issues labelled `feature`, under a tracking issue labelled `plan`. Bugs are labelled `bug`. Each issue is built in `.worktrees/`, on `issue/<n>-<slug>`, with its work plan committed at `docs/work/<n>-<slug>.md`. The checks run on `origin/main` before the branch is created, and again before it is pushed. Merging closes the issue (`.github/workflows/wf-issue-status.yml`).

Pull requests are reviewed with the user-level `review-pr` skill, which hands the review to a separate `pr-reviewer` agent and posts it with `~/.claude/skills/review-pr/scripts/review.py`. The reviewer judges the PR against the specs (the `[review] sources` in `.wf.toml`). It stops and asks questions if the intent is unclear. It requires CI to pass on the PR head (it does not run checks locally), decisions recorded in the work plan and filed in a `spec` issue, and tests for positive, negative and edge cases. Every comment has a score from 1 to 5, and scores of 4 or 5 block the merge. A re-review rules on every earlier finding before raising new ones. Approval and merging stay with the owner.
