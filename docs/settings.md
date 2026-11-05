# Settings reference

<!-- Generated from src/eagain/config/definition.py by `uv run python scripts/gen_settings_docs.py`.
     Do not edit by hand: a unit test fails when this file is out of date. -->

eagain works with no configuration. Every setting below can be changed. Sources are
applied in this order, and later ones win (Spec 003 section 2):

1. Built-in defaults
2. The preset chosen by `preset`
3. User config: `~/.config/eagain/config.toml`, or `config.toml` in `$EAGAIN_HOME`
4. Project config: `.eagain.toml` at the project root, restricted (Spec 003 FR-20)
5. Environment variables, named in the tables below
6. Command-line flags, including `--config <file>` and `--no-project-config`

`eagain config show --origin` prints every active value and where it came from.
`eagain config validate` checks types and ranges. `eagain config init` writes a
commented file listing every setting and its default.

Environment variables take lists as a TOML array or a comma-separated list, and
`none` or an empty value clears an optional setting. Keys with a placeholder such
as `"<tool>"` are tables you fill in, for example
`capture.tools.WebFetch.tool_output_ok_kb`. They have no environment variable.

**Project config** says what a repository's `.eagain.toml` may do: *yes*, *tighten only*
(a stricter value than the one in effect), *literal strings only* (never regular
expressions), or *no* (ignored with a warning).

## general

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `preset` | one of minimal, balanced, full | `"balanced"` | new data | no | `EAGAIN_PRESET` | Capture and retention preset |

## retention

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `retention.max_store_mb` | number, at least 0 | `2048` | next prune | tighten only | `EAGAIN_RETENTION_MAX_STORE_MB` | Maximum store size |
| `retention.max_traces` | integer, at least 0 | none | next prune | tighten only | `EAGAIN_RETENTION_MAX_TRACES` | Maximum number of traces kept |
| `retention.max_age_days` | integer, at least 0 | none | next prune | tighten only | `EAGAIN_RETENTION_MAX_AGE_DAYS` | Delete traces older than this |
| `retention.content_max_age_days` | integer, at least 0 | none | next prune | tighten only | `EAGAIN_RETENTION_CONTENT_MAX_AGE_DAYS` | Remove text from older traces, but keep their structure |
| `retention.keep_failed_days` | integer, at least 0 | none | next prune | tighten only | `EAGAIN_RETENTION_KEEP_FAILED_DAYS` | Keep traces with failures for longer than the above |
| `retention.on_limit` | one of compact, delete_oldest, warn, stop_indexing | `"compact"` | next prune | no | `EAGAIN_RETENTION_ON_LIMIT` | What to do when a limit is reached |
| `retention.warn_at_percent` | integer, at least 0 | `80` | query | tighten only | `EAGAIN_RETENTION_WARN_AT_PERCENT` | Warn when the store reaches this share of its limit |
| `retention.keep_rollups` | true or false | `true` | next prune | tighten only | `EAGAIN_RETENTION_KEEP_ROLLUPS` | Keep daily failure and token counts after traces are deleted |
| `retention.auto_prune` | true or false | `true` | query | tighten only | `EAGAIN_RETENTION_AUTO_PRUNE` | Prune after each index |

## capture

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `capture.message_kb` | number, at least 0 | `4` | new data | tighten only | `EAGAIN_CAPTURE_MESSAGE_KB` | User and assistant message text kept per message |
| `capture.final_response_kb` | number, at least 0 | `8` | new data | tighten only | `EAGAIN_CAPTURE_FINAL_RESPONSE_KB` | Final response text kept per turn |
| `capture.tool_args_kb` | number, at least 0 | `2` | new data | tighten only | `EAGAIN_CAPTURE_TOOL_ARGS_KB` | Tool call arguments kept per call |
| `capture.tool_output_ok_kb` | number, at least 0 | `2` | new data | tighten only | `EAGAIN_CAPTURE_TOOL_OUTPUT_OK_KB` | Output kept per successful tool call |
| `capture.tool_output_error_kb` | number, at least 0 | `8` | new data | tighten only | `EAGAIN_CAPTURE_TOOL_OUTPUT_ERROR_KB` | Output kept per failed tool call |
| `capture.diff_kb` | number, at least 0 | `2` | new data | tighten only | `EAGAIN_CAPTURE_DIFF_KB` | Diff excerpt kept per edit |
| `capture.reasoning_kb` | number, at least 0 | `2` | new data | tighten only | `EAGAIN_CAPTURE_REASONING_KB` | Reasoning text kept per block |
| `capture.reasoning` | true or false | `true` | new data | tighten only | `EAGAIN_CAPTURE_REASONING` | Keep reasoning text at all |
| `capture.diffs` | true or false | `true` | new data | tighten only | `EAGAIN_CAPTURE_DIFFS` | Keep diff excerpts at all |
| `capture.max_trace_mb` | number, at least 0 | `50` | new data | tighten only | `EAGAIN_CAPTURE_MAX_TRACE_MB` | Maximum size of one stored trace |
| `capture.max_record_mb` | number, at least 0 | `10` | new data | tighten only | `EAGAIN_CAPTURE_MAX_RECORD_MB` | Larger source records are skipped and counted |
| `capture.exclude_tools` | list of strings | `[]` | new data | tighten only | `EAGAIN_CAPTURE_EXCLUDE_TOOLS` | Tools whose calls keep no content |
| `capture.exclude_paths` | list of strings | `[]` | new data | tighten only | `EAGAIN_CAPTURE_EXCLUDE_PATHS` | Globs; matching spans keep no path or content |
| `capture.tools."<tool>".message_kb` | number, at least 0 | none | new data | tighten only | — | User and assistant message text kept per message, for one tool |
| `capture.tools."<tool>".final_response_kb` | number, at least 0 | none | new data | tighten only | — | Final response text kept per turn, for one tool |
| `capture.tools."<tool>".tool_args_kb` | number, at least 0 | none | new data | tighten only | — | Tool call arguments kept per call, for one tool |
| `capture.tools."<tool>".tool_output_ok_kb` | number, at least 0 | none | new data | tighten only | — | Output kept per successful tool call, for one tool |
| `capture.tools."<tool>".tool_output_error_kb` | number, at least 0 | none | new data | tighten only | — | Output kept per failed tool call, for one tool |
| `capture.tools."<tool>".diff_kb` | number, at least 0 | none | new data | tighten only | — | Diff excerpt kept per edit, for one tool |
| `capture.tools."<tool>".reasoning_kb` | number, at least 0 | none | new data | tighten only | — | Reasoning text kept per block, for one tool |
| `capture.sources."<source>".message_kb` | number, at least 0 | none | new data | tighten only | — | User and assistant message text kept per message, for one source |
| `capture.sources."<source>".final_response_kb` | number, at least 0 | none | new data | tighten only | — | Final response text kept per turn, for one source |
| `capture.sources."<source>".tool_args_kb` | number, at least 0 | none | new data | tighten only | — | Tool call arguments kept per call, for one source |
| `capture.sources."<source>".tool_output_ok_kb` | number, at least 0 | none | new data | tighten only | — | Output kept per successful tool call, for one source |
| `capture.sources."<source>".tool_output_error_kb` | number, at least 0 | none | new data | tighten only | — | Output kept per failed tool call, for one source |
| `capture.sources."<source>".diff_kb` | number, at least 0 | none | new data | tighten only | — | Diff excerpt kept per edit, for one source |
| `capture.sources."<source>".reasoning_kb` | number, at least 0 | none | new data | tighten only | — | Reasoning text kept per block, for one source |

## sources

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `sources.claude-code.paths` | list of strings | `["~/.claude/projects"]` | query | no | `EAGAIN_SOURCES_CLAUDE_CODE_PATHS` | Where Claude Code sessions are read from (Spec 001 FR-3) |
| `sources."<agent>".paths` | list of strings | `[]` | query | no | — | Where an agent's sessions are read from |
| `sources."<agent>".enabled` | true or false | `true` | query | no | — | Whether an agent's sessions are read |

## paths

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `paths.reports` | string | `"eagain-report"` | query | no | `EAGAIN_PATHS_REPORTS` | Directory reports are written to |

## project

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `project.id` | string | none | query | yes | `EAGAIN_PROJECT_ID` | Explicit project ID |

## redaction

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `redaction.patterns` | list of strings | `[]` | query | literal strings only | `EAGAIN_REDACTION_PATTERNS` | Extra patterns to redact |
| `redaction.allowlist` | list of strings | `[]` | query | no | `EAGAIN_REDACTION_ALLOWLIST` | Values never redacted (false positives) |
| `redaction.disabled` | list of strings | `[]` | query | no | `EAGAIN_REDACTION_DISABLED` | Built-in patterns to disable |

## reports

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `reports.formats` | list of strings | `["json", "md", "html"]` | query | yes | `EAGAIN_REPORTS_FORMATS` | Report formats written by default |

## llm

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `llm.provider` | string | none | query | no | `EAGAIN_LLM_PROVIDER` | LLM provider for --explain |
| `llm.model` | string | none | query | no | `EAGAIN_LLM_MODEL` | Model name for --explain |
| `llm.endpoint` | string | none | query | no | `EAGAIN_LLM_ENDPOINT` | Provider endpoint, including local ones |
| `llm.api_key_env` | string | none | query | no | `EAGAIN_LLM_API_KEY_ENV` | Name of the environment variable holding the API key (never the key) |
| `llm.confirm` | true or false | `true` | query | no | `EAGAIN_LLM_CONFIRM` | Ask before sending anything (FR-8 AC2) |

## suppressions

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `suppressions.rules` | list of strings | `[]` | query | yes | `EAGAIN_SUPPRESSIONS_RULES` | Suppress findings by rule ID |
| `suppressions.fingerprints` | list of strings | `[]` | query | yes | `EAGAIN_SUPPRESSIONS_FINGERPRINTS` | Suppress findings by error fingerprint |
| `suppressions.projects` | list of strings | `[]` | query | yes | `EAGAIN_SUPPRESSIONS_PROJECTS` | Suppress findings by project ID |
| `suppressions.tools` | list of strings | `[]` | query | yes | `EAGAIN_SUPPRESSIONS_TOOLS` | Suppress findings by tool name |

## tool_names

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `tool_names."<source tool>"` | string | none | query | yes | — | Name rules should use for this source tool name |

## operation

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `operation.log_level` | one of debug, info, warning, error | `"warning"` | query | no | `EAGAIN_OPERATION_LOG_LEVEL` | Log level |

## rules

| Key | Type | Default | Applies | Project config | Environment variable | Description |
|---|---|---|---|---|---|---|
| `rules.tool-failure.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_TOOL_FAILURE_ENABLED` | Run tool-failure |
| `rules.tool-failure.severity` | one of low, medium, high | `"low"` | query | yes | `EAGAIN_RULES_TOOL_FAILURE_SEVERITY` | Severity of tool-failure findings |
| `rules.repeated-error.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_REPEATED_ERROR_ENABLED` | Run repeated-error |
| `rules.repeated-error.severity` | one of low, medium, high | `"medium"` | query | yes | `EAGAIN_RULES_REPEATED_ERROR_SEVERITY` | Severity of repeated-error findings |
| `rules.repeated-error.min_occurrences` | integer, at least 1 | `3` | query | yes | `EAGAIN_RULES_REPEATED_ERROR_MIN_OCCURRENCES` | Times one error fingerprint repeats in a session |
| `rules.retry-loop.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_RETRY_LOOP_ENABLED` | Run retry-loop |
| `rules.retry-loop.severity` | one of low, medium, high | `"high"` | query | yes | `EAGAIN_RULES_RETRY_LOOP_SEVERITY` | Severity of retry-loop findings |
| `rules.retry-loop.min_attempts` | integer, at least 1 | `3` | query | yes | `EAGAIN_RULES_RETRY_LOOP_MIN_ATTEMPTS` | Calls with the same tool and normalised arguments in a session |
| `rules.unresolved-failure.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_UNRESOLVED_FAILURE_ENABLED` | Run unresolved-failure |
| `rules.unresolved-failure.severity` | one of low, medium, high | `"high"` | query | yes | `EAGAIN_RULES_UNRESOLVED_FAILURE_SEVERITY` | Severity of unresolved-failure findings |
| `rules.recurring-failure.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_RECURRING_FAILURE_ENABLED` | Run recurring-failure |
| `rules.recurring-failure.severity` | one of low, medium, high | `"high"` | query | yes | `EAGAIN_RULES_RECURRING_FAILURE_SEVERITY` | Severity of recurring-failure findings |
| `rules.recurring-failure.min_sessions` | integer, at least 1 | `2` | query | yes | `EAGAIN_RULES_RECURRING_FAILURE_MIN_SESSIONS` | Sessions sharing one error fingerprint |
| `rules.permission-denied.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_PERMISSION_DENIED_ENABLED` | Run permission-denied |
| `rules.permission-denied.severity` | one of low, medium, high | `"low"` | query | yes | `EAGAIN_RULES_PERMISSION_DENIED_SEVERITY` | Severity of permission-denied findings |
| `rules.user-interrupt.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_USER_INTERRUPT_ENABLED` | Run user-interrupt |
| `rules.user-interrupt.severity` | one of low, medium, high | `"medium"` | query | yes | `EAGAIN_RULES_USER_INTERRUPT_SEVERITY` | Severity of user-interrupt findings |
| `rules.subagent-failure.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_SUBAGENT_FAILURE_ENABLED` | Run subagent-failure |
| `rules.subagent-failure.severity` | one of low, medium, high | `"medium"` | query | yes | `EAGAIN_RULES_SUBAGENT_FAILURE_SEVERITY` | Severity of subagent-failure findings |
| `rules.runtime-error.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_RUNTIME_ERROR_ENABLED` | Run runtime-error |
| `rules.runtime-error.severity` | one of low, medium, high | `"medium"` | query | yes | `EAGAIN_RULES_RUNTIME_ERROR_SEVERITY` | Severity of runtime-error findings |
| `rules.context-pressure.enabled` | true or false | `true` | query | yes | `EAGAIN_RULES_CONTEXT_PRESSURE_ENABLED` | Run context-pressure |
| `rules.context-pressure.severity` | one of low, medium, high | `"low"` | query | yes | `EAGAIN_RULES_CONTEXT_PRESSURE_SEVERITY` | Severity of context-pressure findings |
| `rules.context-pressure.min_compactions` | integer, at least 1 | `2` | query | yes | `EAGAIN_RULES_CONTEXT_PRESSURE_MIN_COMPACTIONS` | Compaction events in a session |

## Presets

A preset sets capture and retention values together. `balanced` is the default and
uses the defaults above. The `minimal` and `full` values are provisional, because
Spec 003 names the presets but not their values.

| Key | `minimal` | `balanced` | `full` |
|---|---|---|---|
| `capture.diff_kb` | `0` | `2` | `8` |
| `capture.diffs` | `false` | `true` | `true` |
| `capture.final_response_kb` | `2` | `8` | `32` |
| `capture.message_kb` | `1` | `4` | `16` |
| `capture.reasoning` | `false` | `true` | `true` |
| `capture.reasoning_kb` | `0` | `2` | `8` |
| `capture.tool_args_kb` | `0.5` | `2` | `8` |
| `capture.tool_output_error_kb` | `2` | `8` | `32` |
| `capture.tool_output_ok_kb` | `0` | `2` | `8` |
| `retention.max_store_mb` | `512` | `2048` | `8192` |
