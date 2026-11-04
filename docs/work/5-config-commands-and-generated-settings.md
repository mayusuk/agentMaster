# Work plan: config commands and generated settings docs

**Issue:** [#5](https://github.com/mayusuk/agentMaster/issues/5) (feature)
**Branch:** `issue/5-config-commands-and-generated-settings`
**Base:** `origin/main @ e001d6d` (checked before branching)
**Status:** Done

## Summary

Adds `eagain config show [--origin]`, `eagain config validate` and `eagain config init`, plus a generated settings reference at `docs/settings.md`. All of them render from the one settings definition, so the commands, the docs and the defaults cannot drift apart. Invalid config exits 2 and names the file, the key and the reason. Secret-like values are never printed.

## Context

- Plan M1.2, part 3 (`docs/plans/2026-11-03-v0-1-m1-format.md` task T3). Builds on #3 (definition and loader) and #4 (project config limits).
- Spec 003 FR-19 AC2, AC3, AC5 and AC9. Spec 003 section 2 names the `--config <file>` and `--no-project-config` flags. Spec 001 FR-7 AC2 gives the exit codes, which `cli.ExitCode` already defines.
- Plan section 3, Settings: validation, `config show`, `config init` and the generated docs all read from one definition.
- `config.loader.load()` already merges every source, records origins, and raises `ConfigError` with diagnostics that name the file, key and reason. Warnings (unknown keys, ignored project values) come back on `Settings.warnings`, or on `ConfigError.warnings`.
- `Setting.secret` exists in the definition but no setting uses it yet.
- The core has no runtime dependencies, so TOML output is written by hand (plan section 1).

## Approach

**`src/eagain/config/render.py`** (new). Pure functions over `SETTINGS` and a loaded `Settings`, with no I/O:
- `toml_value(v)`: TOML literals for the setting kinds (bool, int, float, string, list of strings).
- `display_value(setting, v)`: what `show` prints. It hides secret settings and masks URL credentials (D2).
- `show_lines(settings, origin=False)`: one `key = value` line per active value, in definition order, then any per-tool or per-source keys that were set. With `origin`, each line ends with `# <origin>` (D1).
- `init_text()`: the commented file for `config init` (D5).
- `settings_markdown()`: the reference doc (D6).

**`src/eagain/config/definition.py`**: mark `redaction.patterns` and `redaction.allowlist` as `secret` (D2).

**`src/eagain/cli.py`**: a `config` command group with `show`, `validate` and `init`. A shared parent parser gives `show` and `validate` the `--config` and `--no-project-config` options (D7). `ConfigError` maps to exit 2, with each error on stderr. Warnings go to stderr on every command. A failed write in `init` exits 1.

**`scripts/gen_settings_docs.py`** writes `docs/settings.md` from `settings_markdown()`. `--check` exits 1 when the file is stale. A unit test fails when the committed doc differs, and its message names the command to run.

## Steps

- [x] Render module: TOML values, secret masking, `show` lines, `init` text, with unit tests (FR-19 AC2, AC5).
- [x] CLI `config show`, `config validate` and `config init`, with end-to-end tests through `main()` (FR-19 AC2, AC3, AC5).
- [x] Settings reference: `settings_markdown()`, the generator script, the committed `docs/settings.md`, and the up-to-date test (FR-19 AC9).
- [x] Update the project status line in `CLAUDE.md`, and fill in the Outcome.

## Acceptance criteria

- FR-19 AC2
- FR-19 AC3
- FR-19 AC5
- FR-19 AC9

## Decisions

- **D1** [gap] FR-19 AC2: `config show` prints one `key = value` line per active value, in definition order, using TOML literals and `none` for unset values. With `--origin`, it appends `# <layer> (<file, variable or preset>)`. Why: the spec names the command and its flag but not the output format. This form reads as config and can be copied into a file.
- **D2** [ambiguity] FR-19 AC2: "secret-like values" is read as: settings marked secret in the definition, now `redaction.patterns` and `redaction.allowlist`, shown as `<hidden: n values>`; and credentials in URL userinfo in any string value, shown as `***`. It is not read as pattern-based secret detection on every value. Why: those two settings hold exactly the strings a user wants kept out of output, and a key pasted into a URL is the likeliest leak. General detection needs the redaction patterns, which arrive in M2.
- **D3** [open] FR-21 AC1, FR-9: once `redact.py` exists (plan M2.1), `config show` should also run displayed values through the built-in redaction patterns. It should flag disabled patterns (FR-21 AC1) too. Neither is built here.
- **D4** [gap] FR-19 AC3: `config validate` prints warnings (unknown keys, ignored project values) but they do not fail it. It exits 0 if there are no errors. Errors exit 2, one per line on stderr as `error: <file>: <key>: <reason>`. `show` exits 2 the same way when config is invalid. `init` does not load settings. Why: AC3 covers types and ranges, and AC4 makes unknown keys warnings.
- **D5** [gap] FR-19 AC5: `config init` writes to the user config path (`$EAGAIN_HOME/config.toml`, else `~/.config/eagain/config.toml`). `--path` chooses another file, and `-` prints to stdout. Without `--force` it refuses to overwrite an existing file, and exits 1. Only `version = 1` is active. Every setting is a commented-out `key = default` line, so later changes to the defaults still reach the user. Wildcard keys use placeholders: `"<tool>"`, `"<source>"`, `"<agent>"` and `"<source tool>"`. Why: the spec says only "a commented file listing every setting and its default".
- **D6** [gap] FR-19 AC9, plan M6.2: the generated reference lives at `docs/settings.md`, written by `scripts/gen_settings_docs.py`, with a unit test that fails when it is stale. Plan M6.2 lists generated settings docs under the release milestone, but this issue builds them in M1. Why: the specs do not say where the generated docs live.
- **D7** [gap] Spec 003 section 2: `--config` and `--no-project-config` are options on the commands that load settings (`config show` and `config validate` so far), through a shared parent parser that later commands will reuse. They are not top-level options, and `config init` does not take them. Why: the spec does not say where the flags sit in the command line, and `init` writes a file without reading any config.

## Verification

Standard checks. The generated doc is checked by a unit test, so CI catches drift.

## Risks and open questions

None that need the owner. The decisions above go to a spec follow-up issue.

## Outcome

Built as planned: `config show [--origin]`, `config validate` and `config init` in `cli.py`, all rendering from `config/render.py`, and `docs/settings.md` generated by `scripts/gen_settings_docs.py`. Tests: `tests/test_config_render.py`, `tests/test_cli_config.py` and `tests/test_settings_docs.py`, named after FR-19 AC2, AC3, AC5 and AC9.

No deviations from the approach. The generator was brought forward from plan M6.2 (D6). D3 (redaction of displayed values and disabled-pattern flagging) waits for M2.1 and goes to the spec follow-up issue with the other decisions. No new issues were filed.
