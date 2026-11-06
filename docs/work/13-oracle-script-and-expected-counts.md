# Work plan: Oracle script and expected counts

**Issue:** [#13](https://github.com/mayusuk/agentMaster/issues/13) (feature)
**Branch:** `issue/13-oracle-script-and-expected-counts`
**Base:** `origin/main @ 698a463` (checked before branching)
**Status:** In progress

## Summary

Adds the independent oracle from plan section 5 ("What corpus tests check", point 2). It is a standard-library script that shares no code with `eagain`. It counts the signals from plan section 6 in Claude Code transcripts: tool results, tool errors, user interrupts, permission denials, API errors and subagent runs. Expected counts for each of the four pinned corpora are committed as `tests/corpora/<corpus>.expected.json`, holding numbers only. The corpus tier reruns the oracle and compares its output with those files.

## Context

- Plan M1.9 part 2 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T11). The plan's section 5 covers corpora, real data handling and the oracle, and section 6 lists the signals. The importer that the oracle is later compared with comes in M3 (plan M3.5). #15 reuses this oracle for the M1 live run on `~/.claude/projects`.
- No FR/NFR acceptance criterion is touched directly. FR-3 AC1, AC2, AC3 and AC5 describe what the importer will do with these signals, which is why the oracle counts the raw source signals and not importer outcomes.
- Builds on #12: `tests/corpora/registry.toml`, `corpus_fetch.py` (registry, shared cache), `corpus_gate.py` (skip, or fail when `EAGAIN_REQUIRE_CORPORA=1`) and `count_assert.py` (count-only failures).
- **Structure measured on the pinned revisions** (keys, record types and counts only, no text read or printed):
  - Tool results are `tool_result` blocks in `user` record content, with `is_error: true` on errors. armand0e has 4,166 and 191, matching plan section 6.
  - Denials are error results whose content contains Claude Code's rejection sentence ("doesn't want to proceed with this tool use"). armand0e has 20, matching section 6. No other denial wording (such as "has been denied") occurs in any corpus.
  - Interrupts are user records whose text contains `[Request interrupted by user`. armand0e has 43, matching section 6. The marker never appears inside tool result content.
  - API errors are `system` records with subtype `api_error` (armand0e 5), and assistant records with `isApiErrorMessage: true` (armand0e 50). Section 6's 59 counts every record that has the key, and 9 of those have it set to `false`.
  - Subagent runs are files of `isSidechain` records, one `agentId` per file and named `agent-<agentId>.jsonl`. armand0e has 8 at the top level. crispwisp has 41 under `<session>/subagents/workflows/wf_*/`, next to two `journal.jsonl` files that hold no sidechain records. choucsan has 53 `Agent` tool calls but no subagent transcripts.
  - `permissionDecision` never occurs in the corpora. In current local logs it is a dict on user records, with `decision` always `accept` so far (plan section 7, open item 1).
  - crispwisp has 2 unparseable lines in the middle of one file.

## Approach

- **Oracle** (`tests/corpora/oracle.py`, standard library only, no `eagain` and no test-helper imports, so #15 can run it on its own):
  - `scan(paths) -> Result` reads each file as bytes, line by line, and parses each non-blank line with `json`. A line that does not parse, or is not a JSON object, counts as malformed and is skipped.
  - `Result.counts` is a fixed set of keys: `files`, `records`, `blank_lines`, `malformed_lines`, `sessions`, `tool_results`, `tool_errors`, `interrupts`, `permission_denials`, `permission_decisions_rejected`, `api_error_records`, `api_error_messages`, `subagent_runs`. `Result.records_by_type` is kept for the #15 live summary, but not committed.
  - Signals are the ones in Context, each a separate count. Nothing is combined or deduplicated across signals, so the importer comparison in M3 can map each one onto its own rule.
  - CLI: `python tests/corpora/oracle.py PATH...` takes files or directories (searching `*.jsonl` recursively) and prints the result as JSON. The output holds only counts and record type names.
- **Expected files** (`tests/corpora/<id>.expected.json`): `{"corpus", "revision", "counts"}`. `tests/corpora/update_expected.py` regenerates them from the verified cache, scanning exactly the files listed in the registry.
- **Tests:**
  - Unit tier (`tests/corpora/test_oracle.py`), on synthetic transcripts written in `tmp_path`: each signal counted, plus its near-misses and malformed input. Also: the oracle imports only standard-library modules and nothing from `eagain` (checked on its AST), the CLI output never contains planted text, and an expected file exists for every registry corpus, with the oracle's exact key set, integer values and the registry's revision.
  - Corpus tier (`tests/corpora/test_corpora.py`): for each corpus, rerun the oracle on the registry's files and compare with the expected file using `assert_counts`. Also check that records, blank and malformed lines add up to the registry's line count.
- **Hand-check:** an independent second count on a sample of files, with a different method (byte-level pattern counts, without JSON parsing), compared file by file. armand0e's counts are also compared with the plan section 6 figures, which were measured separately. The method, sample size and agreement go in the Outcome, as aggregates only.
- Plan section 6's API error figure is corrected (59 → 50 flagged records, with 9 more having the key set to `false`), in the way #12 corrected section 5's file count.

## Steps

- [ ] Oracle with unit tests on synthetic transcripts, including the import-independence test.
- [ ] Hand-check on a sample. Generate and commit the four expected files with the update script. Add the expected-file unit test and the corpus-tier agreement test. Correct plan section 6.
- [ ] Outcome, verify, ship.

## Acceptance criteria

- Expected counts are committed for all four corpora, and the corpus tier reproduces them.
- The oracle imports nothing from `eagain`, and a test checks this.
- The hand-check method and its sample size are recorded in the work plan's Outcome, as aggregates only.

## Decisions

- **D1** [gap] Plan section 5, point 2: A permission denial is a tool result with `is_error: true` whose content contains "doesn't want to proceed with this tool use". It is also counted in `tool_errors`, because the source marks it as an error. The importer's split into `denied` and `error` (FR-3 AC3) is derived later, as `tool_errors - permission_denials`. Why: this is the only denial wording in any corpus, and it matches plan section 6's 20.
- **D2** [gap] Plan section 6 and section 7 item 1: A `permissionDecision` whose `decision` is anything but `accept` is counted in its own key, `permission_decisions_rejected`, not in `permission_denials`. Why: no rejected decision has been seen, so its link to a tool result is unknown, and merging the two could double-count.
- **D3** [ambiguity] Plan section 6, API errors: `api_error_messages` counts assistant records with `isApiErrorMessage` set to `true` (armand0e: 50). It does not count records where the key is present but `false` (9 more), and section 6's figure is corrected from 59 to 50. Why: the reading "flagged" means the flag is true. The 9 others are `<synthetic>` records that are not errors.
- **D4** [gap] Plan section 6, interrupts: An interrupt is a user record whose string content or text blocks contain `[Request interrupted by user`, counted once per record. Text inside tool result content does not count. Why: this matches section 6's 43, and the marker never appears in tool results.
- **D5** [gap] Plan section 5, point 2: A subagent run is a distinct `(sessionId, agentId)` pair on records with `isSidechain: true`, whatever the file layout. Agent tool calls with no transcript (choucsan: 53) are not runs. Why: FR-3 AC2 makes sidechain records the child `invoke_agent` spans, so the oracle counts what the importer can see. This covers both layouts in section 6.
- **D6** [gap] Plan section 5, point 2: Expected files also hold `files`, `records`, `blank_lines`, `malformed_lines` and `sessions` (distinct `sessionId` values), plus the pinned `revision` to detect stale counts. A line that parses but is not a JSON object counts as malformed. Why: these support the accounting check (section 5, point 1) at no cost, and the revision is an ID, not content.
- **D7** [gap] Plan section 5, point 2: Expected files are regenerated with `tests/corpora/update_expected.py`, which scans exactly the files listed in the registry, never by searching the cache directory. Why: a stray file in the shared cache must not change the counts.

## Verification

- `wf verify` runs `corpus-fetch` and the corpus tier, so the new agreement test runs on real data before shipping.
- The hand-check results (aggregates only) go in the Outcome.

## Risks and open questions

- The signals are text- and flag-based, and the transcript format is not a public contract. A new Claude Code version may phrase denials or interrupts differently. The corpora are pinned, so this only affects the live run in #15, which will show it as a mismatch between counts.
- The oracle is the reference for M3.5 (full oracle agreement). Its definitions are deliberately simple and raw, so differences there are importer questions, not oracle changes.

## Outcome

_Filled in before shipping._
