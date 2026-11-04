# Work plan: Settings definition and loader

**Issue:** [#3](https://github.com/mayusuk/agentMaster/issues/3) (feature)
**Branch:** `issue/3-settings-definition-and-loader`
**Base:** `origin/main @ f792f1b` (checked before branching)
**Status:** Draft

## Summary

Adds `src/eagain/config/`: one typed definition of every setting, and a loader that merges the six configuration sources of Spec 003 section 2 in order, records where each value came from, checks the file version, validates types, and warns about unknown keys with the closest valid one. No CLI commands yet; `config show`, `validate` and `init` follow in #5, and the full project config limits in #4.

## Context

- Spec 003 sections 2 and 3, FR-19, and plan section 3 ("Settings": one definition feeds validation, `config show`, `config init` and generated docs). Plan task M1.2, part 1 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T1).
- Plan section 1: no runtime dependencies. TOML via `tomllib`; closest-key suggestions via `difflib`.
- CLAUDE.md: a repository's `.eagain.toml` is untrusted (FR-20). This task fails closed on it: project config may set only keys marked as freely project-settable; everything else is ignored with a warning until #4 implements tightening and literal-only redaction.
- NFR-12: loading adds under 50 ms. The loader reads at most four small files and does no subprocess or network work.
- The only existing code is `cli.py` (exit codes, FR-7 AC2) and the test network block.

## Approach

**Definition (`config/definition.py`).** A frozen `Setting` dataclass: dotted key (segments may be `*` for per-tool, per-source or per-agent tables), kind (`int`, `float`, `bool`, `str`, `enum`, `list[str]`), optional flag, default, choices, minimum, "applies" (`query`, `reindex`, `new_data`, `next_prune`), project access (`allow`, `tighten`, `literal`, `deny`), and a one-line description for docs. `SETTINGS` is the single registry; `PRESETS` maps preset names to value overrides.

Only settings whose defaults or values the specs already fix are defined now:
- `preset`; all `retention.*` and `capture.*` keys from Spec 003 section 3 with their stated defaults, plus `capture.tools.*.<kb limits>` and `capture.sources.*.<kb limits>` overrides;
- `sources.claude-code.paths` (default `~/.claude/projects`, Spec 001 FR-3), `sources.*.paths`, `sources.*.enabled`;
- `paths.reports` (default `eagain-report`, matching `.gitignore`);
- `project.id` (explicit project ID, Spec 002 project identity source 1);
- `redaction.patterns`, `redaction.allowlist`, `redaction.disabled` (empty lists);
- `reports.formats` (default all of `json`, `md`, `html`, Spec 001 section 8 step 1);
- `llm.provider`, `llm.model`, `llm.endpoint`, `llm.api_key_env` (no defaults, plan M5 task 5), `llm.confirm` (true, FR-8 AC2);
- `operation.log_level` (`warning`).

Settings whose defaults the specs leave open (report top-N, excerpts, `fail_on`, LLM budget and timeout, workers, rule thresholds) are added by the task that builds their feature, so no default is invented ahead of its use. Capture and retention are v0.2 features but are defined now because presets set them and #4 needs them for FR-20 AC2.

Preset values for `minimal` and `full` are not given in Spec 003; they are provisional, and marked so in the code (Spec 003 section 8 already calls the default limits starting guesses).

**Loader (`config/loader.py`).** `load(...)` takes the environment, home directory, working directory, `--config` file, `--no-project-config` and flag overrides as arguments, so tests never touch the real home. Layers in order, later wins:
1. defaults, 2. preset (chosen by the highest source that sets `preset`), 3. user config (`$EAGAIN_HOME/config.toml`, else `~/.config/eagain/config.toml`), 4. project `.eagain.toml` (found by walking up from the working directory, stopping at a directory containing `.git`), 5. `EAGAIN_<SECTION>_<KEY>` environment variables for non-wildcard keys, 6. `--config <file>` then explicit flags.

Each value keeps an `Origin` (layer plus file path, variable name or preset name). Files are flattened to key paths (tuples, so quoted TOML keys with dots survive). A top-level `version` must be an integer: missing means the current version 1; newer than supported is an error saying to upgrade; older runs registered migrations or fails with a clear migration message. Type and range errors are collected as diagnostics naming file, key and reason, and raised together as `ConfigError`. Unknown keys warn and name the closest valid key from `difflib.get_close_matches`.

## Steps

- [x] Settings definition: `Setting`, `SETTINGS`, `PRESETS`, key matching with wildcards; tests that every default validates, keys are unique and preset keys exist.
- [ ] Loader core: file reading, flattening, version check and migrations, type validation, origins, unknown-key warnings; FR-19 AC4 and AC6 tests.
- [ ] Layers: user, project (fail-closed), environment, `--config`, flags, presets; precedence test setting one key in every source; FR-19 AC1 test.
- [ ] Outcome, verify, ship.

## Acceptance criteria

- FR-19 AC1
- FR-19 AC4
- FR-19 AC6
- The precedence order of Spec 003 section 2 holds, with a test that sets one key in every source.

## Verification

Standard checks. No fixtures beyond `tmp_path` files written by the tests. A timing test checks that loading every layer stays well under NFR-12's 50 ms.

## Risks and open questions

- `--config <file>` is treated as part of the flags layer (Spec 003 section 2 lists it under flags): its values beat the environment, and explicit flags beat it.
- `EAGAIN_HOME` is read as a directory holding `config.toml`, by analogy with `~/.config/eagain/`.
- The explicit project ID key is named `project.id`; Spec 002 names the source but not the key.

## Outcome

_Filled in before shipping._
