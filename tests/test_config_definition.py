from __future__ import annotations

import tomllib

import pytest

from eagain.config.definition import (
    PRESETS,
    RULES,
    SETTINGS,
    Kind,
    ProjectAccess,
    Setting,
    Tighter,
    format_key,
    lookup,
    parse_key,
)


def test_every_default_is_valid_for_its_setting() -> None:
    for s in SETTINGS:
        assert s.check(s.default) is None, s.name


def test_keys_are_unique() -> None:
    names = [s.name for s in SETTINGS]
    assert len(names) == len(set(names))


def test_every_setting_has_a_description() -> None:
    assert all(s.description for s in SETTINGS)


def test_preset_values_name_real_settings_and_are_valid() -> None:
    preset = lookup(("preset",))
    assert preset is not None
    assert set(PRESETS) == set(preset.choices)
    assert PRESETS["balanced"] == {}
    for name, values in PRESETS.items():
        for key, value in values.items():
            setting = lookup(key)
            assert setting is not None, (name, key)
            assert setting.check(value) is None, (name, key)


def test_spec_003_defaults() -> None:
    def default(name: str) -> object:
        s = lookup(parse_key(name))
        assert s is not None, name
        return s.default

    assert default("retention.max_store_mb") == 2048
    assert default("retention.max_traces") is None
    assert default("retention.on_limit") == "compact"
    assert default("retention.warn_at_percent") == 80
    assert default("capture.message_kb") == 4
    assert default("capture.tool_output_error_kb") == 8
    assert default("capture.max_record_mb") == 10
    assert default("capture.exclude_paths") == []
    assert default("sources.claude-code.paths") == ["~/.claude/projects"]


def test_wildcard_lookup_and_exact_keys_win() -> None:
    per_tool = lookup(("capture", "tools", "WebFetch", "tool_output_ok_kb"))
    assert per_tool is not None
    assert per_tool.name == "capture.tools.*.tool_output_ok_kb"
    assert per_tool.default is None
    claude = lookup(("sources", "claude-code", "paths"))
    assert claude is not None
    assert claude.default == ["~/.claude/projects"]
    assert lookup(("sources", "other-agent", "paths")) is not None
    assert lookup(("capture", "tools", "WebFetch", "nope")) is None


def test_repository_cannot_set_paths_llm_or_sources() -> None:
    for s in SETTINGS:
        if s.key[0] in ("paths", "llm", "sources", "preset") or s.name == "redaction.allowlist":
            assert s.project is ProjectAccess.DENY, s.name


@pytest.mark.parametrize(
    ("kind", "value", "problem"),
    [
        (Kind.INT, True, "must be an integer"),
        (Kind.INT, 1.5, "must be an integer"),
        (Kind.FLOAT, "4", "must be a number"),
        (Kind.FLOAT, -1, "must be at least 0"),
        (Kind.BOOL, 1, "must be true or false"),
        (Kind.STR_LIST, ["a", 1], "must be a list of strings"),
        (Kind.ENUM, "loud", "must be one of a, b"),
        (Kind.STR, None, "must be set"),
    ],
)
def test_check_rejects_wrong_values(kind: Kind, value: object, problem: str) -> None:
    s = Setting(("x",), kind, None, "x", choices=("a", "b"), minimum=0)
    assert s.check(value) == problem


def test_format_key_quotes_unusual_segments() -> None:
    assert format_key(("capture", "tools", "mcp.server.tool", "diff_kb")) == (
        'capture.tools."mcp.server.tool".diff_kb'
    )
    assert format_key(parse_key("retention.max_store_mb")) == "retention.max_store_mb"


@pytest.mark.parametrize(
    "segment",
    [
        *('say "hi"', "back\\slash", "\x1b[2Jclear", "tab\tnew\nline"),
        *("del\x7f", "c1\x9b31m", "naïve", ""),
    ],
)
def test_format_key_escapes_quoted_segments_as_toml(segment: str) -> None:
    """Keys can come from an untrusted .eagain.toml (FR-20), so they are printed escaped."""
    shown = format_key(("tool_names", segment))
    assert shown.isascii()
    assert shown.isprintable()
    assert tomllib.loads(f"{shown} = 1") == {"tool_names": {segment: 1}}


def test_every_tightened_setting_says_which_way_is_stricter() -> None:
    for s in SETTINGS:
        if s.project is ProjectAccess.TIGHTEN:
            assert s.tighter is not None, s.name
            if s.kind in (Kind.INT, Kind.FLOAT):
                assert s.tighter is Tighter.LOWER, s.name
            elif s.kind is Kind.BOOL:
                assert s.tighter in (Tighter.TRUE, Tighter.FALSE), s.name
            else:
                assert s.tighter is Tighter.SUPERSET, s.name
        else:
            assert s.tighter is None, s.name


def test_capture_and_retention_are_only_tightened_or_denied() -> None:
    for s in SETTINGS:
        if s.key[0] in ("capture", "retention"):
            assert s.project in (ProjectAccess.TIGHTEN, ProjectAccess.DENY), s.name
    on_limit = lookup(parse_key("retention.on_limit"))
    assert on_limit is not None
    assert on_limit.project is ProjectAccess.DENY


def test_spec_001_rule_defaults() -> None:
    assert len(RULES) == 10

    def default(name: str) -> object:
        s = lookup(parse_key(name))
        assert s is not None, name
        assert s.project is ProjectAccess.ALLOW, name
        return s.default

    assert default("rules.tool-failure.severity") == "low"
    assert default("rules.retry-loop.severity") == "high"
    assert default("rules.context-pressure.enabled") is True
    assert default("rules.repeated-error.min_occurrences") == 3
    assert default("rules.retry-loop.min_attempts") == 3
    assert default("rules.recurring-failure.min_sessions") == 2
    assert default("rules.context-pressure.min_compactions") == 2
    assert default("suppressions.fingerprints") == []
    assert lookup(("tool_names", "Bash")) is not None
