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
- **D2** [ambiguity] FR-19 AC2: "secret-like values" is read as: settings marked secret in the definition, now `redaction.patterns` and `redaction.allowlist`, shown as `<hidden: n values>`; and credentials in URL userinfo in any string value, shown as `***`. Everything from `://` to the last `@` before whitespace is masked, because raw tokens may contain `@` or `/`; a URL with an `@` later in its path is masked too far rather than leaking. It is not read as pattern-based secret detection on every value. Why: those two settings hold exactly the strings a user wants kept out of output, and a key pasted into a URL is the likeliest leak. General detection needs the redaction patterns, which arrive in M2.
- **D3** [open] FR-21 AC1, FR-9: once `redact.py` exists (plan M2.1), `config show` should also run displayed values through the built-in redaction patterns. It should flag disabled patterns (FR-21 AC1) too. Neither is built here.
- **D4** [gap] FR-19 AC3: `config validate` prints warnings (unknown keys, ignored project values) but they do not fail it. It exits 0 if there are no errors. Errors exit 2, one per line on stderr as `error: <file>: <key>: <reason>`. `show` exits 2 the same way when config is invalid. `init` does not load settings. Why: AC3 covers types and ranges, and AC4 makes unknown keys warnings.
- **D5** [gap] FR-19 AC5: `config init` writes to the user config path (`$EAGAIN_HOME/config.toml`, else `~/.config/eagain/config.toml`). `--path` chooses another file, and `-` prints to stdout. Without `--force` it refuses to overwrite an existing file, and exits 1. Only `version = 1` is active. Every setting is a commented-out `key = default` line, so later changes to the defaults still reach the user. Wildcard keys use placeholders: `"<tool>"`, `"<source>"`, `"<agent>"` and `"<source tool>"`. Why: the spec says only "a commented file listing every setting and its default".
- **D6** [gap] FR-19 AC9, plan M6.2: the generated reference lives at `docs/settings.md`, written by `scripts/gen_settings_docs.py`, with a unit test that fails when it is stale. Plan M6.2 listed generated settings docs under the release milestone. This issue builds them in M1, and M6.2 now says to review them. Why: the specs do not say where the generated docs live.
- **D7** [gap] Spec 003 section 2: `--config` and `--no-project-config` are options on the commands that load settings (`config show` and `config validate` so far), through a shared parent parser that later commands will reuse. They are not top-level options, and `config init` does not take them. Why: the spec does not say where the flags sit in the command line, and `init` writes a file without reading any config.
- **D8** [gap] FR-20, FR-19 AC2: a key segment that is not a bare TOML key is printed as a TOML basic string, with every control, DEL and non-ASCII character escaped (`tool_names."\u001b[31m"`). Code points above U+FFFF use `\UXXXXXXXX`, since TOML rejects surrogate-pair escapes. Values use the same escaping. The one form that cannot be read back is a lone surrogate, which only comes from an environment variable whose bytes are not valid UTF-8. It is still escaped, so it is safe to print. This applies everywhere a key is shown: `config show`, warnings and errors. Why: keys can come from an untrusted `.eagain.toml`, so they must not write control sequences to the terminal, and the escaped form keeps `show` output valid TOML (D1).
- **D9** [gap] FR-19 AC3: on success, `config validate` prints one line on stdout: `config is valid (<file>, <file>)`, listing the config files read, or `config is valid (no config files, using the defaults)`. Why: the spec gives only the failure behaviour.
- **D10** [gap] FR-19 AC5, Spec 001 FR-7 AC2: when `config init` cannot write its file (a missing or unwritable directory), it exits 1 with `error: cannot write <path>: <reason>` on stderr, as for an existing file (D5). Why: it is a runtime failure, not invalid input, so exit 2 does not fit.
- **D11** [gap] FR-19 AC2: in `config show`, keys set under a wildcard (per tool, per source) are listed together at their pattern's place in the definition order, sorted by key. Why: D1 gives definition order, which does not order the keys a user adds.
- **D12** [gap] FR-19 AC2: a secret setting with an empty value is shown as it is (`[]`), not as `<hidden: 0 values>`. Why: an empty list holds no secret, and showing it tells the user that no extra patterns are set.
- **D13** [gap] FR-19 AC4: every command that loads settings prints each warning on stderr as `warning: <file>: <key>: <reason>`, the same form as errors (D4), with warnings before errors. Why: the spec says unknown keys warn but not where or how.
- **D14** [gap] Spec 001 FR-7 AC2: `eagain` with no command prints help and exits 0. `eagain config` with no action is a usage error and exits 2. Why: a bare `eagain` is a request for help, while a group without an action is incomplete input.

## Verification

Standard checks. The generated doc is checked by a unit test, so CI catches drift.

## Risks and open questions

None that need the owner. The decisions above go to a spec follow-up issue.

## Outcome

Built as planned: `config show [--origin]`, `config validate` and `config init` in `cli.py`, all rendering from `config/render.py`, and `docs/settings.md` generated by `scripts/gen_settings_docs.py`. Tests: `tests/test_config_render.py`, `tests/test_cli_config.py` and `tests/test_settings_docs.py`, named after FR-19 AC2, AC3, AC5 and AC9.

No deviations from the approach. The generator was brought forward from plan M6.2 (D6). D3 (redaction of displayed values and disabled-pattern flagging) waits for M2.1 and goes to the spec follow-up issue with the other decisions. No new issues were filed.

Review round 1 (PR #24): all six findings were valid and changed the branch, with no pushbacks. R1: environment values now name their variable. R2: untrusted keys are printed escaped (D8). R3: URL masking runs to the last `@` (D2). R4: details recorded as D9 to D14. R5: a test for warnings alongside errors. R6: plan M6.2 narrowed. A coverage check (coverage.py, branch mode) then found untested branches in `render.py` and the generator. Tests were added for them, and the changed files are now fully covered.

Review round 2: R7 was valid and fixed. Characters outside the BMP were escaped as surrogate pairs, which TOML rejects, so `toml_string` now escapes one character at a time (D8). There were no pushbacks.
