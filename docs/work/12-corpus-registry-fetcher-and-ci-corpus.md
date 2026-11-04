# Work plan: Corpus registry, fetcher and CI corpus job

**Issue:** [#12](https://github.com/mayusuk/agentMaster/issues/12) (feature)
**Branch:** `issue/12-corpus-registry-fetcher-and-ci-corpus`
**Base:** `origin/main @ 7f79edb` (checked before branching)
**Status:** Done

## Summary

Adds the corpus test tier from plan section 5:
- `tests/corpora/registry.toml`, which pins the four public Claude Code corpora: full revision, license, and a SHA-256, size and line count for every data file;
- a standard-library fetcher that downloads into a shared `.corpora/` cache and verifies every hash;
- count-only assertion helpers;
- a first corpus test;
- a `corpus` CI job that downloads, with caching, before the tests start.

## Context

- Plan section 5 ("Test tiers", "Corpora", "Handling real data") and task M1.9 part 1 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T10). No FR/NFR criterion is touched directly. NFR-4 (synthetic fixtures only) is why real data stays out of the repository.
- **Measured on the pinned revisions (structure only):**
  - armand0e: 63 `.jsonl` files, 75.1 MB;
  - AlinCiocan: 18 files, 49.9 MB;
  - crispwisp: 104 files, 25.3 MB;
  - choucsan: 1,017 files, 40.5 MB (plan section 5 said 984, which was only the first page of the tree API; corrected here).
  - This matches plan section 5. Most files are plain git blobs rather than LFS objects, so the SHA-256 hashes must come from the downloads themselves.
- **Rules:**
  - never commit, quote or print corpus content;
  - tests can't open sockets, so downloading happens only in the fetch step;
  - if a download fails, CI fails;
  - locally, the tier is skipped unless `EAGAIN_REQUIRE_CORPORA=1`.

## Approach

- **Registry** (`tests/corpora/registry.toml`): one `[[corpus]]` table per dataset, with `id`, `dataset`, the full 40-character `revision`, `license`, `role`, and a `files` array of `{path, sha256, size, lines}`. Only the `.jsonl` data files are listed. READMEs and images are not test data.
- **Fetcher** (`tests/corpora/corpus_fetch.py`, standard library only):
  - `fetch` downloads every missing or mismatching file from `https://huggingface.co/datasets/<dataset>/resolve/<revision>/<path>` into `<cache>/<id>/<revision>/<path>`. It writes to a temporary file, checks the hash and size, then renames. A mismatch exits non-zero and names the corpus and file, never the content.
  - `pin <dataset> <revision> ...` lists the files through the Hugging Face tree API, downloads them, and writes their entries into the registry. So the hashes are reproducible from the command, not typed in by hand.
  - The cache defaults to `.corpora/` in the primary checkout, so every worktree shares one copy. It's found by reading `.git`/`commondir`, with no subprocess. `EAGAIN_CORPORA_DIR` overrides it.
- **Gate** (`tests/corpora/corpus_gate.py`): a session-scoped check that each corpus is complete and verified. If it isn't, it skips with the fetch command, or fails when `EAGAIN_REQUIRE_CORPORA=1`.
- **Count helpers** (`tests/corpora/count_assert.py`): `assert_counts(expected, actual, label)` takes only `str` → `int` mappings. It rejects anything else without echoing it, and fails with `pytest.fail(..., pytrace=False)`, whose message holds keys and numbers only. So pytest's assertion rewriting never shows values.
- **First corpus test:** every pinned file exists, matches its hash, and has its registered line count. Per-corpus totals of files and lines are compared with the registry through the count helpers.
- **Test selection:** `pytest` excludes both `live` and `corpus`, and `pytest -m corpus` runs only the corpus tier. `.wf.toml` gains a `corpus-fetch` step before `corpus`, and both apply only once the registry exists.
- **CI:** a separate `corpus` job. It restores `.corpora/` from `actions/cache`, keyed on the registry's hash with a prefix restore key, then runs `fetch`, then `pytest -m corpus` with `EAGAIN_REQUIRE_CORPORA=1`.

## Steps

- [x] Fetcher, pin, gate and count helpers, with unit tests on synthetic files served from `file://` URLs (hash mismatch, require flag, count messages).
- [x] Pin the four corpora from real downloads; add the first corpus test, the test selection change, and the `.wf.toml` fetch step.
- [x] CI `corpus` job with caching.
- [x] Outcome, verify, ship.

## Acceptance criteria

- A hash mismatch fails the run, and the failure message names the file but no content.
- With `EAGAIN_REQUIRE_CORPORA=1` and no data, the tier fails rather than skips.
- The count helpers' failure messages contain counts and IDs only, and a test asserts this.
- The corpus CI job passes on the pull request.

## Verification

- `wf verify` runs the new `corpus-fetch` and `corpus` steps, so the local gate exercises a real download and verification.
- The CI corpus job must pass on the PR.
- Download size and time are recorded in the Outcome.

## Risks and open questions

- **Hugging Face changes:** files stay addressable by their pinned revision even if a dataset is later updated or rewritten. Deletion of a revision would fail CI loudly, which is the intended behaviour.
- **Cache size:** the CI cache holds about 190 MB, within GitHub's limits.
- **Worktrees:** they share the primary checkout's cache, so parallel fetches can race. Writes go through a temporary file and an atomic rename, so the worst case is a duplicate download.

## Outcome

- **Done:**
  - `tests/corpora/registry.toml`: 4 corpora, 1,202 `.jsonl` files, 190.8 MB, each with SHA-256, size and line count;
  - `corpus_fetch.py` (fetch, pin, verify, shared cache);
  - `corpus_gate.py` (skip, or fail when required);
  - `count_assert.py`;
  - the first corpus test (`test_corpus_files_match_the_registry`, one per corpus);
  - a registry check in the unit tier;
  - 23 unit tests on synthetic files served from `file://`;
  - the `corpus` CI job;
  - a `corpus-fetch` step in `.wf.toml`.
- **Download:** pinning downloaded and hashed 190.8 MB in 292 s on this machine. A cached `fetch` re-verifies everything in under a second. The corpus tier takes about 0.6 s.
- **Deviations:**
  - choucsan has 1,017 data files, not 984. Plan section 5's count stopped at the first page of the Hugging Face tree API (988 files plus 12 directories fill a 1,000-entry page). The fetcher follows the `Link` header, and plan section 5 is corrected.
  - `pytest` now runs only the unit tier (`not live and not corpus`). Otherwise corpus tests would skip in every unit run.
  - Registry paths are checked to be relative with no `..`, so a tampered registry can't write outside the cache.
- **Decisions for review:**
  - Only `.jsonl` data files are pinned, not READMEs or images.
  - The local cache is shared with the primary checkout through `.git`/`commondir`, so worktrees don't download 190 MB each. `EAGAIN_CORPORA_DIR` overrides the location.
  - The CI corpus job runs on Python 3.14 only.
- **Follow-ups:** none filed. #13 adds the oracle and expected counts on top of this.
