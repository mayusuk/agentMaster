"""The single definition of every setting (Spec 003 section 3, plan section 3).

Loading, validation, ``config show``, ``config init`` and the generated settings
docs all read from ``SETTINGS``, so they cannot drift apart (FR-19 AC9).

Only settings whose defaults the specs fix are defined here. Settings for
features not built yet are added by the task that builds the feature.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

KeyPath = tuple[str, ...]
"""A setting key split into segments. Tuples keep quoted TOML keys containing dots intact."""

WILDCARD = "*"
CURRENT_VERSION = 1


class Kind(StrEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STR = "str"
    ENUM = "enum"
    STR_LIST = "list[str]"


class Applies(StrEnum):
    """When a change takes effect (Spec 003 section 3)."""

    QUERY = "query"
    REINDEX = "reindex"
    NEW_DATA = "new data"
    NEXT_PRUNE = "next prune"


class ProjectAccess(StrEnum):
    """What a repository's untrusted ``.eagain.toml`` may do with a setting (FR-20)."""

    ALLOW = "allow"
    TIGHTEN = "tighten"
    """Only a stricter value than the one in effect (FR-20 AC2)."""
    LITERAL = "literal"
    """Only literal strings, never regular expressions (FR-20 AC3)."""
    DENY = "deny"


@dataclass(frozen=True)
class Setting:
    key: KeyPath
    kind: Kind
    default: Any
    description: str
    applies: Applies = Applies.QUERY
    project: ProjectAccess = ProjectAccess.DENY
    optional: bool = False
    """``None`` is a valid value (shown as "none" in the spec tables)."""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    secret: bool = False

    @property
    def name(self) -> str:
        return format_key(self.key)

    @property
    def is_pattern(self) -> bool:
        return WILDCARD in self.key

    def matches(self, key: KeyPath) -> bool:
        return len(key) == len(self.key) and all(
            p in (WILDCARD, k) for p, k in zip(self.key, key, strict=True)
        )

    def check(self, value: Any) -> str | None:
        """Return why ``value`` is invalid for this setting, or ``None`` if it is valid."""
        if value is None:
            return None if self.optional else "must be set"
        if self.kind is Kind.BOOL:
            return None if isinstance(value, bool) else "must be true or false"
        if self.kind is Kind.STR_LIST:
            ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
            return None if ok else "must be a list of strings"
        if self.kind in (Kind.STR, Kind.ENUM):
            if not isinstance(value, str):
                return "must be a string"
            if self.choices and value not in self.choices:
                return f"must be one of {', '.join(self.choices)}"
            return None
        # Numbers. bool is a subclass of int, so rule it out first.
        if isinstance(value, bool):
            return f"must be {'an integer' if self.kind is Kind.INT else 'a number'}"
        if self.kind is Kind.INT and not isinstance(value, int):
            return "must be an integer"
        if self.kind is Kind.FLOAT and not isinstance(value, int | float):
            return "must be a number"
        if self.minimum is not None and value < self.minimum:
            return f"must be at least {self.minimum:g}"
        return None


def format_key(key: Sequence[str]) -> str:
    """Dotted form, quoting segments TOML would need quoted (``capture.tools."a.b".x``)."""
    safe = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-*")
    return ".".join(s if s and set(s) <= safe else f'"{s}"' for s in key)


def parse_key(name: str) -> KeyPath:
    """Inverse of ``format_key`` for unquoted dotted names."""
    return tuple(name.split("."))


def _s(name: str, kind: Kind, default: Any, description: str, **kw: Any) -> Setting:
    return Setting(parse_key(name), kind, default, description, **kw)


_TIGHT_DATA: dict[str, Any] = {"applies": Applies.NEW_DATA, "project": ProjectAccess.TIGHTEN}
_TIGHT_PRUNE: dict[str, Any] = {"applies": Applies.NEXT_PRUNE, "project": ProjectAccess.TIGHTEN}

# Kilobyte limits per item; each can be overridden per tool and per source (Spec 003 "Capture").
_CAPTURE_KB: list[tuple[str, float, str]] = [
    ("message_kb", 4, "User and assistant message text kept per message"),
    ("final_response_kb", 8, "Final response text kept per turn"),
    ("tool_args_kb", 2, "Tool call arguments kept per call"),
    ("tool_output_ok_kb", 2, "Output kept per successful tool call"),
    ("tool_output_error_kb", 8, "Output kept per failed tool call"),
    ("diff_kb", 2, "Diff excerpt kept per edit"),
    ("reasoning_kb", 2, "Reasoning text kept per block"),
]


def _build() -> tuple[Setting, ...]:
    out: list[Setting] = [
        _s(
            "preset",
            Kind.ENUM,
            "balanced",
            "Capture and retention preset",
            choices=("minimal", "balanced", "full"),
            applies=Applies.NEW_DATA,
        ),
        # Retention (Spec 003 section 3). v0.2 behaviour, defined now for presets and FR-20.
        _s(
            "retention.max_store_mb",
            Kind.FLOAT,
            2048,
            "Maximum store size",
            minimum=0,
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.max_traces",
            Kind.INT,
            None,
            "Maximum number of traces kept",
            optional=True,
            minimum=0,
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.max_age_days",
            Kind.INT,
            None,
            "Delete traces older than this",
            optional=True,
            minimum=0,
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.content_max_age_days",
            Kind.INT,
            None,
            "Remove text from older traces, but keep their structure",
            optional=True,
            minimum=0,
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.keep_failed_days",
            Kind.INT,
            None,
            "Keep traces with failures for longer than the above",
            optional=True,
            minimum=0,
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.on_limit",
            Kind.ENUM,
            "compact",
            "What to do when a limit is reached",
            choices=("compact", "delete_oldest", "warn", "stop_indexing"),
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.warn_at_percent",
            Kind.INT,
            80,
            "Warn when the store reaches this share of its limit",
            minimum=0,
            project=ProjectAccess.TIGHTEN,
        ),
        _s(
            "retention.keep_rollups",
            Kind.BOOL,
            True,
            "Keep daily failure and token counts after traces are deleted",
            **_TIGHT_PRUNE,
        ),
        _s(
            "retention.auto_prune",
            Kind.BOOL,
            True,
            "Prune after each index",
            project=ProjectAccess.TIGHTEN,
        ),
    ]
    # Capture (Spec 003 section 3). v0.2 behaviour, defined now for presets and FR-20.
    for key, default, desc in _CAPTURE_KB:
        out.append(_s(f"capture.{key}", Kind.FLOAT, default, desc, minimum=0, **_TIGHT_DATA))
    out += [
        _s("capture.reasoning", Kind.BOOL, True, "Keep reasoning text at all", **_TIGHT_DATA),
        _s("capture.diffs", Kind.BOOL, True, "Keep diff excerpts at all", **_TIGHT_DATA),
        _s(
            "capture.max_trace_mb",
            Kind.FLOAT,
            50,
            "Maximum size of one stored trace",
            minimum=0,
            **_TIGHT_DATA,
        ),
        _s(
            "capture.max_record_mb",
            Kind.FLOAT,
            10,
            "Larger source records are skipped and counted",
            minimum=0,
            **_TIGHT_DATA,
        ),
        _s(
            "capture.exclude_tools",
            Kind.STR_LIST,
            [],
            "Tools whose calls keep no content",
            **_TIGHT_DATA,
        ),
        _s(
            "capture.exclude_paths",
            Kind.STR_LIST,
            [],
            "Globs; matching spans keep no path or content",
            **_TIGHT_DATA,
        ),
    ]
    for table in ("tools", "sources"):
        for key, _default, desc in _CAPTURE_KB:
            out.append(
                _s(
                    f"capture.{table}.*.{key}",
                    Kind.FLOAT,
                    None,
                    f"{desc}, for one {table[:-1]}",
                    optional=True,
                    minimum=0,
                    **_TIGHT_DATA,
                )
            )
    out += [
        # Sources and paths. Never settable from a repository (FR-20 AC4).
        _s(
            "sources.claude-code.paths",
            Kind.STR_LIST,
            ["~/.claude/projects"],
            "Where Claude Code sessions are read from (Spec 001 FR-3)",
        ),
        _s("sources.*.paths", Kind.STR_LIST, [], "Where an agent's sessions are read from"),
        _s("sources.*.enabled", Kind.BOOL, True, "Whether an agent's sessions are read"),
        _s("paths.reports", Kind.STR, "eagain-report", "Directory reports are written to"),
        # Project identity (Spec 002, source 1).
        _s(
            "project.id",
            Kind.STR,
            None,
            "Explicit project ID",
            optional=True,
            project=ProjectAccess.ALLOW,
        ),
        # Redaction (Spec 001 FR-9, Spec 003 FR-20 AC3 and FR-21).
        _s(
            "redaction.patterns",
            Kind.STR_LIST,
            [],
            "Extra patterns to redact",
            project=ProjectAccess.LITERAL,
        ),
        _s("redaction.allowlist", Kind.STR_LIST, [], "Values never redacted (false positives)"),
        _s("redaction.disabled", Kind.STR_LIST, [], "Built-in patterns to disable"),
        # Reports (Spec 001 FR-7; section 8 writes all formats by default).
        _s(
            "reports.formats",
            Kind.STR_LIST,
            ["json", "md", "html"],
            "Report formats written by default",
            project=ProjectAccess.ALLOW,
        ),
        # LLM explainer (Spec 001 FR-8). No model default, so none can go stale (plan M5 task 5).
        _s("llm.provider", Kind.STR, None, "LLM provider for --explain", optional=True),
        _s("llm.model", Kind.STR, None, "Model name for --explain", optional=True),
        _s(
            "llm.endpoint", Kind.STR, None, "Provider endpoint, including local ones", optional=True
        ),
        _s(
            "llm.api_key_env",
            Kind.STR,
            None,
            "Name of the environment variable holding the API key (never the key)",
            optional=True,
        ),
        _s("llm.confirm", Kind.BOOL, True, "Ask before sending anything (FR-8 AC2)"),
        # Operation.
        _s(
            "operation.log_level",
            Kind.ENUM,
            "warning",
            "Log level",
            choices=("debug", "info", "warning", "error"),
        ),
    ]
    return tuple(out)


SETTINGS: tuple[Setting, ...] = _build()

# Provisional: Spec 003 names the presets but not their values. "balanced" is the defaults.
PRESETS: dict[str, dict[KeyPath, Any]] = {
    "minimal": {
        parse_key("capture.message_kb"): 1,
        parse_key("capture.final_response_kb"): 2,
        parse_key("capture.tool_args_kb"): 0.5,
        parse_key("capture.tool_output_ok_kb"): 0,
        parse_key("capture.tool_output_error_kb"): 2,
        parse_key("capture.diff_kb"): 0,
        parse_key("capture.reasoning_kb"): 0,
        parse_key("capture.reasoning"): False,
        parse_key("capture.diffs"): False,
        parse_key("retention.max_store_mb"): 512,
    },
    "balanced": {},
    "full": {
        parse_key("capture.message_kb"): 16,
        parse_key("capture.final_response_kb"): 32,
        parse_key("capture.tool_args_kb"): 8,
        parse_key("capture.tool_output_ok_kb"): 8,
        parse_key("capture.tool_output_error_kb"): 32,
        parse_key("capture.diff_kb"): 8,
        parse_key("capture.reasoning_kb"): 8,
        parse_key("retention.max_store_mb"): 8192,
    },
}


@dataclass
class _Index:
    exact: dict[KeyPath, Setting] = field(default_factory=dict)
    patterns: list[Setting] = field(default_factory=list)


def _index(settings: Sequence[Setting]) -> _Index:
    idx = _Index()
    for s in settings:
        if s.is_pattern:
            idx.patterns.append(s)
        else:
            idx.exact[s.key] = s
    return idx


_INDEX = _index(SETTINGS)


def lookup(key: KeyPath) -> Setting | None:
    """The setting for a concrete key. Exact keys win over wildcard patterns."""
    if (s := _INDEX.exact.get(key)) is not None:
        return s
    return next((p for p in _INDEX.patterns if p.matches(key)), None)


def concrete_settings() -> Iterator[Setting]:
    """Settings with a single key, i.e. those that have a default in effect."""
    return iter(_INDEX.exact.values())


def known_names() -> list[str]:
    return [s.name for s in SETTINGS]
