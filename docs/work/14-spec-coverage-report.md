# Work plan: Spec coverage report

**Issue:** [#14](https://github.com/mayusuk/agentMaster/issues/14) (feature)
**Branch:** `issue/14-spec-coverage-report`
**Base:** `origin/main @ 7f79edb` (checked before branching)
**Status:** Done

## Summary

Adds `scripts/spec_coverage.py`, a standard-library report of every acceptance criterion in `specs/*/spec.md`, the tests named after it, and the milestone that owns it. It exits 1 only when a criterion in a milestone marked finished has no test, so it passes on `main` today. It runs as its own CI job and as a `.wf.toml` check.

## Context

- Plan section 5 "Definition of done", point 3: a spec coverage report built from test names shows no gaps for finished milestones. Plan task M1.9 part 3 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T12).
- Specs state criteria as `### FR-n Title` headings followed by `- **ACm:**` lines: 42 in Spec 001, 56 in Spec 002 and 28 in Spec 003. Spec 002 lists FR-17 before FR-15. NFRs are single `- **NFR-n ...:**` bullets with no AC numbers.
- Test names follow `test_frN_acM_...` and `test_nfrN_...`, for example `test_fr19_ac4_*` and `test_nfr12_*`. The `.wf.toml` `[acceptance]` rule already enforces them per work plan. This report is the repository-wide view.
- Milestones and their requirements are listed in plan headings, for example `### M1 Format (FR-1, FR-2, FR-19 to FR-21)`. Only v0.1 has a plan so far.

## Approach

- **Criteria.** Each `FR-n ACm` under an FR heading is one criterion. Each NFR bullet is one criterion with ID `NFR-n`, covered by any test starting `test_nfrN_`. An NFR written as a heading with ACs is treated like an FR. File order is irrelevant: criteria are sorted by number, so FR-17 before FR-15 doesn't matter.
- **Tests.** Every `def test_*` in `tests/**/*.py`. A criterion `FR-4 AC3` is covered by `test_fr4_ac3` or by any name starting `test_fr4_ac3_`. Because of that trailing underscore, `AC1` never matches `test_fr4_ac10_...`.
- **Milestones.** Read from `### Mn Title (refs)` headings in `specs/*/plan.md`. Refs can be `FR-n`, `NFR-n`, ranges like `FR-19 to FR-21`, or one criterion like `FR-18 AC4` (Spec 002's style). A requirement in no planned milestone is reported as unplanned and never fails. A ref to a requirement that doesn't exist is an error (exit 2), so typos can't hide gaps.
- **Finished marker.** This is the smallest marker that fits: the first non-empty line after a milestone heading reads `**Status:** Finished`. Without it the milestone is unfinished. #15 adds it for M1.
- **Output.** A text report per milestone, with `--json` for tools. The exit code is 0, 1 for gaps in a finished milestone, or 2 for parse errors.
- **Wiring.** A separate `spec-coverage` job in `ci.yml`, a `[[verify]]` step in `.wf.toml`, and `scripts` added to mypy's files and to pytest's `pythonpath`.

## Steps

- [x] Parser and report, with tests on synthetic specs, a plan and tests (finished gap fails, unfinished gap passes) and on the real specs (every criterion listed).
- [x] Wiring: pyproject, CI job, `.wf.toml` check; CLAUDE.md command list.
- [x] Outcome, verify, ship.

## Acceptance criteria

- The report lists every criterion in Specs 001 to 003 with its covering tests.
- A gap in a finished milestone fails the check, and a gap in an unfinished milestone does not. Tests cover both.

## Verification

Standard checks, plus `python scripts/spec_coverage.py` passes on the branch.

## Risks and open questions

- The M1 heading includes FR-21, whose criteria are redaction limits that arrive with M2 redaction. Marking M1 finished (#15) will flag them unless they are tested by then or the heading changes. That is a plan decision for #15, not this task.

## Outcome

- **Done:**
  - `scripts/spec_coverage.py` is the report.
  - `tests/test_spec_coverage.py` has 10 tests:
    - synthetic repositories cover a finished gap (fails), an unfinished gap (passes), number-order parsing, prefix matching that doesn't cross `AC1`/`AC10`, ranges, unknown references and JSON;
    - the real specs check that all 139 criteria are listed (Spec 001: 42 ACs and 6 NFRs, Spec 002: 56 and 5, Spec 003: 28 and 2), counted independently of the parser.
  - Wiring: a CI job, a `.wf.toml` check, pyproject (`scripts` in mypy files and pytest `pythonpath`) and `CLAUDE.md`.
- **On `main` today:** 8 of 139 criteria have tests and no milestone is finished, so the report passes.
- **Decisions for review:**
  - **Finished marker:** `**Status:** Finished` as the first non-empty line after a milestone heading in `specs/*/plan.md`.
  - **NFRs:** each NFR is one criterion, `NFR-n`, covered by `test_nfrN_...`. NFRs belong to a milestone only if a plan heading lists them, so today they are all unplanned.
  - **Unplanned requirements:** a requirement in no plan heading is reported as unplanned and never fails. Spec 002 and Spec 003's v0.2 work have no plan yet.
  - **CI:** the job runs with `uv run --no-project`, since the report uses only the standard library.
- **For #15:** the M1 heading includes FR-21 (redaction limits, built with M2 redaction). Marking M1 finished will report those criteria as gaps unless they are tested or the heading changes.
- **Follow-ups:** none filed.
