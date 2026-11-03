# Spec 003: Configuration and Retention

| | |
|---|---|
| **Status** | Draft for review |
| **Applies to** | Specs 001 and 002 |
| **Scope** | Config system in v0.1. Capture and retention settings in v0.2. Suggestion settings in v0.3 |

## 1. Goals

1. The tool works well with no configuration.
2. Every limit, threshold, retention period and capture choice can be changed.
3. Users can always see which value is active, where it came from, and when a change takes effect.
4. Configuration cannot be used to weaken the tool's safety guarantees, especially from a file inside a repository.

## 2. Configuration sources

Later sources override earlier ones:

1. Built-in defaults
2. Preset selected by `preset = "..."`
3. User config: `~/.config/agentlog/config.toml`, or the path in `AGENTLOG_HOME`
4. Project config: `.agentlog.toml` at the project root, restricted (FR-20)
5. Environment variables: `AGENTLOG_<SECTION>_<KEY>`
6. Command-line flags, including `--config <file>` and `--no-project-config`

Files use TOML, which Python 3.11+ can read with no extra dependency. Overrides per project and per tool use tables:

```toml
preset = "balanced"

[retention]
max_store_mb = 2048
max_age_days = 365
content_max_age_days = 90
on_limit = "compact"

[capture]
message_kb = 4
tool_output_ok_kb = 2

[capture.tools.WebFetch]
tool_output_ok_kb = 0.5

[rules.retry-loop]
min_attempts = 4

[projects."github.com/acme/secret-repo"]
index = false
```

## 3. Settings

"Applies" says when a change takes effect:

- **Query:** the next command
- **Reindex:** after `agentlog reindex`
- **New data:** newly indexed data only. Raising a capture limit cannot restore content that was already cut, unless the source transcript still exists and `agentlog index --backfill` is run

### Retention

| Key | Default | Meaning | Applies |
|---|---|---|---|
| `retention.max_store_mb` | 2048 | Maximum store size | Next prune |
| `retention.max_traces` | none | Maximum number of traces kept | Next prune |
| `retention.max_age_days` | none | Delete traces older than this | Next prune |
| `retention.content_max_age_days` | none | Remove text from older traces, but keep their structure | Next prune |
| `retention.keep_failed_days` | none | Keep traces with failures for longer than the above | Next prune |
| `retention.on_limit` | `compact` | `compact`, `delete_oldest`, `warn` or `stop_indexing` | Next prune |
| `retention.warn_at_percent` | 80 | Warn when the store reaches this share of its limit | Query |
| `retention.keep_rollups` | true | Keep daily failure and token counts after traces are deleted | Next prune |
| `retention.auto_prune` | true | Prune after each `index` | Query |
| `projects."<id>".retention.*` | inherited | Any of the above, per project | Next prune |

### Capture

Kilobyte limits are per item. 0 keeps structure with no text. Each can be overridden with `capture.tools."<tool>".*`, per tool, and `capture.sources."<source>".*`, per agent.

| Key | Default | Applies |
|---|---|---|
| `capture.message_kb` | 4 | New data |
| `capture.final_response_kb` | 8 | New data |
| `capture.tool_args_kb` | 2 | New data |
| `capture.tool_output_ok_kb` | 2 | New data |
| `capture.tool_output_error_kb` | 8 | New data |
| `capture.diff_kb` | 2 | New data |
| `capture.reasoning_kb` | 2 | New data |
| `capture.reasoning` | true | New data |
| `capture.diffs` | true | New data |
| `capture.max_trace_mb` | 50 | New data |
| `capture.max_record_mb` | 10 (larger source records are skipped and counted) | New data |
| `capture.exclude_tools` | [] | New data |
| `capture.exclude_paths` | [] (globs; matching spans keep no path or content) | New data |

### Presets

Presets set capture and retention values together, for users who don't want to tune individual keys.

| Preset | Summary |
|---|---|
| `minimal` | Structure, errors and token counts, with little text |
| `balanced` (default) | The defaults in this spec |
| `full` | Larger excerpts, for users who prioritise reuse over disk space |

### Other settings

| Section | Settings |
|---|---|
| **Paths** | `paths.store`, `paths.reports`, `paths.drafts`, `sources.<agent>.paths`, `sources.<agent>.enabled` |
| **Projects** | `projects."<id>".index`, `.sharing`, `.group`, `.retention`, explicit project ID, monorepo sub-project roots |
| **Rules** (001) | Per rule: `enabled`, `severity`, thresholds. Suppressions by rule, fingerprint, project or tool. Extra fingerprint normalisation patterns |
| **Recommendations** (001) | Ranking order, maximum shown, template text overrides |
| **Reports** (001) | Default formats, top-N limits, sections shown, excerpt length, whether excerpts appear at all, `fail_on`, time zone |
| **Redaction** (001) | Extra patterns, false-positive allowlist, per-pattern disable (see FR-20, FR-21) |
| **LLM** (001) | Provider, model, endpoint, name of the API key's environment variable, token budget per run, excerpt size, timeout, confirmation prompt. Keys are never stored in config, and local endpoints are supported |
| **Work items** (002) | Follow-up length that joins the previous item, tool names treated as edits or commands |
| **Search** (002) | Default scope and limit, output token budget, ranking weights per field, age that triggers a staleness warning, usage logging on or off, search backend |
| **Suggestions** (002) | Thresholds per pattern, day and session minimums, enabled forms, risky-command list (can only be extended), dismissal resurfacing factor, maximum shown, draft exporter |
| **Operation** | `log_level`, log file, parallel workers, memory limit, batch size, backup before migration, number of backups kept |

## 4. Functional requirements

### FR-19 Configuration system

- **AC1:** With no config file, every command works using documented defaults.
- **AC2:** `agentlog config show [--origin]` prints active values and, with `--origin`, the source of each. Secret-like values are never printed.
- **AC3:** `agentlog config validate` checks types and ranges. Invalid config exits 2, naming the file, key and reason.
- **AC4:** An unknown key produces a warning naming the closest valid key, so a typo cannot silently leave a limit unenforced.
- **AC5:** `agentlog config init` writes a commented file listing every setting and its default.
- **AC6:** Config files have a version field, and older versions keep working or give a clear migration message.
- **AC7:** Each report and each store record a hash of the settings that affect results. Spec 001's determinism guarantee becomes "same input and same settings".
- **AC8:** Data that was not captured because of a setting is listed in coverage, and rules relying on it are listed as not evaluated.
- **AC9:** The documentation is generated from one settings definition, so docs and defaults cannot drift apart.

### FR-20 Limits on project config

A repository is not a trusted source of settings. Cloning one must not change where data goes or how much is protected.

- **AC1:** Project config can set: rule thresholds, severities, suppressions, tool name mappings, report defaults, and an explicit project ID.
- **AC2:** Project config can only tighten capture and retention, for example by lowering a limit.
- **AC3:** Project config can add redaction patterns only as literal strings, never as regular expressions, because a crafted pattern could stall the tool.
- **AC4:** Project config cannot set LLM settings, paths, sharing, groups, allowlists, or draft locations. Those keys are ignored with a warning.
- **AC5:** Reports state when a project config was applied and how many findings it suppressed.

### FR-21 Protected behaviour

Some guarantees are not settings. No config option or flag can change these:

- Source transcripts are read only.
- Hooks, rules and skills are never installed automatically.
- No network calls except an explicitly requested LLM run, and no telemetry.
- The store is owner-only.
- The LLM explainer has no tools.
- Search results are marked as untrusted.
- Rule drafts never copy transcript free text.

Redaction is configurable within limits:

- **AC1:** User config can add patterns, allowlist false positives and disable individual built-in patterns. A report and `config show` flag any disabled pattern.
- **AC2:** Redaction as a whole cannot be turned off.
- **AC3:** Disabled built-in patterns still apply to anything sent to an LLM.

### FR-22 Retention

`agentlog prune [--dry-run]` applies retention, and also runs after `index` when `auto_prune` is on.

`compact` removes data in this order, stopping once the store is within its limits:

1. Text from the oldest unpinned traces, keeping their structure, tokens and fingerprints
2. Whole oldest unpinned traces, keeping daily rollups

- **AC1:** `--dry-run` shows exactly how many traces and how much space would be affected, and changes nothing.
- **AC2:** When several limits are set, the strictest one applies.
- **AC3:** `agentlog pin <item, session or project>` exempts data from retention. If pinned data alone exceeds a limit, the tool warns and deletes nothing pinned.
- **AC4:** Traces removed by retention are not re-imported by the next `index` from still-existing transcripts. `agentlog index --backfill` brings them back on request.
- **AC5:** Reports state when pruning limited the history analysed, and for what date range.
- **AC6:** Rollups preserve long-term failure and token trends after traces are deleted. `forget` removes rollups too, but retention does not.
- **AC7:** A per-project retention setting overrides the global one for that project only.
- **AC8:** Space is reclaimed from the file after pruning, so the store really shrinks.
- **AC9:** `agentlog store stats` shows size by layer and project, trace counts, date range, compacted and pinned counts, and space used against limits.

### FR-23 Safe upgrades

- **AC1:** A backup of the store is made before a schema migration, by default, and the number kept is configurable.
- **AC2:** A failed migration leaves the store usable at its previous version.

## 5. Non-functional requirements

- **NFR-12:** Loading configuration adds under 50 ms to any command.
- **NFR-13:** A setting's meaning does not change between minor versions without a deprecation warning.

## 6. End-to-end acceptance scenario

1. With no config, `agentlog index` and `agentlog search` work with the defaults.
2. A typo such as `max_stor_mb` gives a warning naming `max_store_mb`.
3. `agentlog config show --origin` attributes a value set by an environment variable to that variable.
4. A cloned repository whose `.agentlog.toml` sets an LLM endpoint and raises capture limits has both ignored, with warnings.
5. With a low `max_store_mb`, `prune --dry-run` changes nothing, and `prune` then compacts the oldest text first while search still finds those items by title, files and commands.
6. A pinned session survives pruning.
7. Pruned traces do not return on the next `index`, but do with `--backfill`.
8. `capture.tools.WebFetch.tool_output_ok_kb = 0` stores no output for that tool, and other tools are unaffected.
9. Disabling one redaction pattern is flagged in the report, and no setting can turn off redaction as a whole.
10. Changing a rule threshold changes the settings hash in the report.

## 7. Milestones

- **v0.1:** Config loading, validation, origin display, rule and report settings, project config limits (FR-19, FR-20, FR-21).
- **v0.2:** Capture settings, retention, pinning, store stats, safe upgrades (FR-22, FR-23).
- **v0.3:** Suggestion settings.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Too many settings overwhelm users | Good defaults, presets, generated docs, `config init` |
| Each setting multiplies test combinations | Test defaults and presets fully; test each setting on its own for range and effect; do not attempt all combinations |
| A setting silently degrades results | Coverage lists uncaptured data, and the settings hash is in every report |
| Retention deletes data someone later wants | Default keeps structure and rollups, plus dry run, pinning and backfill while sources exist |
| Default limits are wrong | Measure against real use in v0.2-M1. These numbers are starting guesses |
