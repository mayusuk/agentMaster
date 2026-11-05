"""Text rendered from the settings definition (Spec 003 FR-19 AC2, AC5)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from eagain.config.definition import SETTINGS, concrete_settings, lookup, parse_key
from eagain.config.loader import Layer, Origin, Settings, load
from eagain.config.render import (
    display_value,
    example_key,
    init_text,
    show_lines,
    toml_value,
)


@pytest.mark.parametrize(
    "value",
    [
        *(True, False, 0, 2048, 0.5, -1.25),
        *("", 'quote " and \\ back', "tab\tnew\nline\x7f"),
        *([], ["a", "b"]),
    ],
)
def test_toml_value_round_trips(value: object) -> None:
    assert tomllib.loads(f"v = {toml_value(value)}")["v"] == value


def test_toml_value_has_no_null() -> None:
    with pytest.raises(ValueError, match="no null"):
        toml_value(None)


def defaults() -> Settings:
    values = {s.key: s.default for s in concrete_settings()}
    return Settings(values, {k: Origin(Layer.DEFAULT) for k in values})


# --- FR-19 AC2: show ---------------------------------------------------------


def test_fr19_ac2_show_lists_every_active_value_in_definition_order() -> None:
    lines = show_lines(defaults())
    names = [line.split(" = ", 1)[0] for line in lines]
    assert names == [s.name for s in SETTINGS if not s.is_pattern]
    assert "retention.max_store_mb = 2048" in lines
    assert "retention.max_traces = none" in lines
    assert 'reports.formats = ["json", "md", "html"]' in lines


def test_fr19_ac2_show_origin_names_the_source(tmp_path: Path) -> None:
    home, repo = tmp_path / "home", tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    user = home / ".config" / "eagain" / "config.toml"
    user.parent.mkdir(parents=True)
    user.write_text("[capture.tools.WebFetch]\ntool_output_ok_kb = 0.5\n", encoding="utf-8")
    settings = load(env={"EAGAIN_RETENTION_MAX_TRACES": "10"}, home=home, cwd=repo)
    lines = show_lines(settings, origin=True)
    assert "retention.max_traces = 10  # environment (EAGAIN_RETENTION_MAX_TRACES)" in lines
    assert "retention.max_store_mb = 2048  # default" in lines
    assert f"capture.tools.WebFetch.tool_output_ok_kb = 0.5  # user config ({user})" in lines
    # A key set under a wildcard follows its pattern's place in the definition.
    names = [line.split(" = ", 1)[0] for line in lines]
    assert names.index("capture.tools.WebFetch.tool_output_ok_kb") > names.index(
        "capture.exclude_paths"
    )


def test_fr19_ac2_secret_settings_are_never_printed() -> None:
    settings = defaults()
    settings.values[parse_key("redaction.patterns")] = ["acme-internal-token-123"]
    settings.values[parse_key("redaction.allowlist")] = ["AKIAFAKE0000", "sk-not-real"]
    out = "\n".join(show_lines(settings, origin=True))
    for secret in ("acme-internal-token-123", "AKIAFAKE0000", "sk-not-real"):
        assert secret not in out
    assert "redaction.patterns = <hidden: 1 value>" in out
    assert "redaction.allowlist = <hidden: 2 values>" in out
    # Nothing is hidden when there is nothing to hide.
    assert display_value(lookup(parse_key("redaction.patterns")), []) == "[]"


def test_fr19_ac2_url_credentials_are_masked() -> None:
    setting = lookup(parse_key("llm.endpoint"))
    shown = display_value(setting, "https://user:s3cr3t@llm.example.test/v1")
    assert "s3cr3t" not in shown
    assert shown == '"https://***@llm.example.test/v1"'
    paths = lookup(parse_key("sources.claude-code.paths"))
    shown = display_value(paths, ["ftp://me:pw@host/x", "~/logs"])
    assert shown == '["ftp://***@host/x", "~/logs"]'


def test_only_redaction_lists_are_secret() -> None:
    assert sorted(s.name for s in SETTINGS if s.secret) == [
        "redaction.allowlist",
        "redaction.patterns",
    ]


# --- FR-19 AC5: init ---------------------------------------------------------


def test_fr19_ac5_init_lists_every_setting_with_its_default() -> None:
    lines = init_text().splitlines()
    for s in SETTINGS:
        expected = f"# {example_key(s)} =" + (
            "" if s.default is None else f" {toml_value(s.default)}"
        )
        assert expected in lines, s.name
    # The only active line is the version, so the file changes nothing as written.
    active = [line for line in lines if line.strip() and not line.startswith("#")]
    assert active == ["version = 1"]


def test_fr19_ac5_init_file_loads_cleanly_as_written_and_uncommented(tmp_path: Path) -> None:
    home, repo = tmp_path / "home", tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    user = home / ".config" / "eagain" / "config.toml"
    user.parent.mkdir(parents=True)
    text = init_text()

    user.write_text(text, encoding="utf-8")
    assert load(env={}, home=home, cwd=repo).warnings == []

    # Uncommenting every default gives the defaults back, with no warnings or errors.
    prefixes = {f"# {s.name} = " for s in concrete_settings() if s.default is not None}
    uncommented = [
        line[2:] if any(line.startswith(p) for p in prefixes) else line
        for line in text.splitlines()
    ]
    user.write_text("\n".join(uncommented), encoding="utf-8")
    settings = load(env={}, home=home, cwd=repo)
    assert settings.warnings == []
    for s in concrete_settings():
        assert settings.get(s.key) == s.default, s.name
        if s.default is not None:
            assert settings.origin(s.key).layer is Layer.USER, s.name


def test_init_placeholders_name_what_to_fill_in() -> None:
    names = {example_key(s) for s in SETTINGS if s.is_pattern}
    assert 'capture.tools."<tool>".message_kb' in names
    assert 'capture.sources."<source>".message_kb' in names
    assert 'sources."<agent>".paths' in names
    assert 'tool_names."<source tool>"' in names
    assert not any("<name>" in n for n in names)
