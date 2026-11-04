# Work plan: Project config limits

**Issue:** [#4](https://github.com/mayusuk/agentMaster/issues/4) (feature)
**Branch:** `issue/4-project-config-limits`
**Base:** `origin/main @ 7f79edb` (checked before branching)
**Status:** Draft

## Summary

Enforces Spec 003 FR-20 on a repository's untrusted `.eagain.toml`. It may set rule settings, suppressions, tool name mappings, report defaults and `project.id`. It may only tighten capture and retention, and may add redaction patterns only as literal strings. LLM settings, paths, sources, sharing, groups, allowlists and draft locations are ignored with a warning. Adds the rule, suppression and tool-name settings that the specs fix, so AC1 has real settings to test against.

## Context

- Spec 003 FR-20 AC1 to AC4. Plan task M1.2 part 2 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T2). Builds on #3. That loader is fail-closed: project config may set only `allow` settings.
- Spec 001 FR-4 fixes the ten rule IDs, their default severities (`low`, `medium`, `high`) and their thresholds: `repeated-error` 3, `retry-loop` 3, `recurring-failure` 2 sessions, `context-pressure` 2 compactions. Spec 003's example names `rules.retry-loop.min_attempts`. FR-4 AC6 names suppressions by rule, fingerprint or project, and Spec 003 adds tool.
- CLAUDE.md: `.eagain.toml` is untrusted, and FR-21 guarantees are not settings.

## Approach

**Definition.**
- Each `tighten` setting gets a direction (`Tighter`):
  - **lower** for kilobyte, megabyte, count and day limits. `none` means unlimited, so any number is tighter than `none`.
  - **false** for `capture.reasoning`, `capture.diffs` and `retention.keep_rollups`.
  - **true** for `retention.auto_prune`.
  - **superset** for the `capture.exclude_*` lists. Project entries are added to the inherited list, never replace it.
- `retention.on_limit` has no agreed strictness order between its four actions, so it becomes `deny`.
- New `allow` settings:
  - `rules.<id>.enabled` and `rules.<id>.severity` for the ten FR-4 rules;
  - the four FR-4 thresholds (`min_occurrences`, `min_attempts`, `min_sessions`, `min_compactions`);
  - `suppressions.rules`, `.fingerprints`, `.projects` and `.tools`;
  - `tool_names.*`, which maps a source tool name to the name rules should use.

**Loader.** Project values are applied during the merge, so tightening compares against the value already in effect from defaults, preset and user config:
- A looser value is ignored, with a warning that shows both values and cites FR-20 AC2.
- Per-tool and per-source overrides compare against the inherited base limit.
- Project `redaction.patterns` are passed through `re.escape` and added to the inherited patterns. A crafted pattern can therefore only ever match itself literally (AC3).
- Keys in a denied namespace (`llm`, `paths`, `sources`, `projects`, `sharing`, `groups`, `preset`) are ignored with a "cannot be set by project config" warning, even when the key is not defined yet (Spec 002's `projects.<id>.sharing`, `.group`, `paths.drafts`). So they are never reported as mere typos (AC4).

## Steps

- [x] Definition: rule, suppression and tool-name settings; tightening directions; tests.
- [x] Loader: tightening, literal redaction patterns, denied namespaces; FR-20 AC1 to AC4 tests.
- [ ] Outcome, verify, ship.

## Acceptance criteria

- FR-20 AC1
- FR-20 AC2
- FR-20 AC3
- FR-20 AC4

## Verification

Standard checks only.

## Risks and open questions

- The threshold key names other than `min_attempts` are mine (`min_occurrences`, `min_sessions`, `min_compactions`). The M2 rule tasks use them.
- Spec 003 doesn't define what "tool name mappings" look like. `tool_names."<source tool>" = "<name>"` is the smallest shape that fits.
- `retention.on_limit` is denied rather than ordered. A repository that wants a stricter action can say so in its README; users can still set it themselves.

## Outcome

_Filled in before shipping._
