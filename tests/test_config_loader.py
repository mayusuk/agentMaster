"""Settings loader (Spec 003 section 2, FR-19)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from eagain.config import loader
from eagain.config.definition import PRESETS, concrete_settings, parse_key
from eagain.config.loader import ConfigError, Layer, Origin, load


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / ".git").mkdir(parents=True)
    return r


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def user_file(home: Path, text: str) -> Path:
    return write(home / ".config" / "eagain" / "config.toml", text)


def load_in(
    home: Path, repo: Path, env: dict[str, str] | None = None, **kw: Any
) -> loader.Settings:
    return load(env=env or {}, home=home, cwd=repo, **kw)


# --- FR-19 AC1: defaults with no config -------------------------------------


def test_fr19_ac1_no_config_gives_documented_defaults(home: Path, repo: Path) -> None:
    settings = load_in(home, repo)
    assert settings.warnings == []
    assert settings.files == []
    for s in concrete_settings():
        assert settings.get(s.key) == s.default, s.name
        assert settings.origin(s.key) == Origin(Layer.DEFAULT), s.name


def test_fr19_ac1_defaults_are_not_shared_between_loads(home: Path, repo: Path) -> None:
    first = load_in(home, repo)
    first.get("reports.formats").append("pdf")
    assert load_in(home, repo).get("reports.formats") == ["json", "md", "html"]


# --- Precedence (Spec 003 section 2) ----------------------------------------


def test_precedence_one_key_set_in_every_source(
    home: Path, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = parse_key("reports.formats")
    # Shipped presets only set capture and retention; give one a value for this key.
    monkeypatch.setitem(PRESETS, "full", {**PRESETS["full"], key: ["preset"]})
    user = user_file(home, 'preset = "full"\n[reports]\nformats = ["user"]\n')
    project = write(repo / ".eagain.toml", '[reports]\nformats = ["project"]\n')
    extra = write(tmp_path / "extra.toml", '[reports]\nformats = ["config-file"]\n')
    env = {"EAGAIN_REPORTS_FORMATS": "env"}
    flags: dict[str | tuple[str, ...], Any] = {"reports.formats": ["flag"]}
    config: Path | None = extra

    expected = [
        (["flag"], Origin(Layer.FLAG)),
        (["config-file"], Origin(Layer.CONFIG_FILE, str(extra))),
        (["env"], Origin(Layer.ENV, "EAGAIN_REPORTS_FORMATS")),
        (["project"], Origin(Layer.PROJECT, str(project))),
        (["user"], Origin(Layer.USER, str(user))),
        (["preset"], Origin(Layer.PRESET, "full")),
    ]
    for value, origin in expected:
        settings = load_in(home, repo, env, config_file=config, flags=flags)
        assert (settings.get(key), settings.origin(key)) == (value, origin)
        # Remove the winning source and check the next one takes over.
        if origin.layer is Layer.FLAG:
            flags = {}
        elif origin.layer is Layer.CONFIG_FILE:
            config = None
        elif origin.layer is Layer.ENV:
            env = {}
        elif origin.layer is Layer.PROJECT:
            project.unlink()
        elif origin.layer is Layer.USER:
            write(user, 'preset = "full"\n')
    settings = load_in(home, repo, env, config_file=config, flags=flags)
    assert settings.origin(key) == Origin(Layer.PRESET, "full")
    write(user, "")
    assert load_in(home, repo, env).origin(key) == Origin(Layer.DEFAULT)


def test_preset_is_chosen_by_the_highest_source(home: Path, repo: Path) -> None:
    user_file(home, 'preset = "minimal"\n')
    settings = load_in(home, repo, {"EAGAIN_PRESET": "full"})
    assert settings.get("capture.message_kb") == 16
    assert settings.origin("capture.message_kb") == Origin(Layer.PRESET, "full")
    # An explicit value still beats the preset.
    user_file(home, 'preset = "minimal"\n[capture]\nmessage_kb = 3\n')
    assert load_in(home, repo).get("capture.message_kb") == 3


def test_eagain_home_moves_the_user_config(home: Path, repo: Path, tmp_path: Path) -> None:
    custom = write(tmp_path / "elsewhere" / "config.toml", '[operation]\nlog_level = "debug"\n')
    settings = load_in(home, repo, {"EAGAIN_HOME": str(custom.parent)})
    assert settings.get("operation.log_level") == "debug"
    assert settings.files == [custom]


def test_project_config_is_found_above_cwd_but_not_outside_the_repo(repo: Path, home: Path) -> None:
    write(repo / ".eagain.toml", '[project]\nid = "acme/app"\n')
    sub = repo / "pkg" / "src"
    sub.mkdir(parents=True)
    assert load_in(home, sub).get("project.id") == "acme/app"
    write(repo.parent / ".eagain.toml", '[project]\nid = "outside"\n')
    (repo / ".eagain.toml").unlink()
    assert load_in(home, sub).get("project.id") is None


def test_no_project_config_flag(repo: Path, home: Path) -> None:
    write(repo / ".eagain.toml", '[project]\nid = "acme/app"\n')
    assert load_in(home, repo, no_project_config=True).get("project.id") is None


def test_project_config_cannot_set_denied_keys(repo: Path, home: Path) -> None:
    write(
        repo / ".eagain.toml",
        '[llm]\nendpoint = "https://evil.example"\n[capture]\nmessage_kb = 999\n',
    )
    settings = load_in(home, repo)
    assert settings.get("llm.endpoint") is None
    assert settings.get("capture.message_kb") == 4
    assert sorted(w.key for w in settings.warnings) == ["capture.message_kb", "llm.endpoint"]
    assert all("FR-20" in w.message for w in settings.warnings)


def test_environment_values_are_typed(home: Path, repo: Path) -> None:
    env = {
        "EAGAIN_RETENTION_MAX_TRACES": "500",
        "EAGAIN_CAPTURE_DIFF_KB": "0.5",
        "EAGAIN_CAPTURE_REASONING": "off",
        "EAGAIN_SOURCES_CLAUDE_CODE_PATHS": "/a, /b",
        "EAGAIN_CAPTURE_EXCLUDE_TOOLS": '["Web,Fetch"]',
        "EAGAIN_PROJECT_ID": "none",
        "EAGAIN_REQUIRE_CORPORA": "1",
    }
    settings = load_in(home, repo, env)
    assert settings.get("retention.max_traces") == 500
    assert settings.get("capture.diff_kb") == 0.5
    assert settings.get("capture.reasoning") is False
    assert settings.get("sources.claude-code.paths") == ["/a", "/b"]
    assert settings.get("capture.exclude_tools") == ["Web,Fetch"]
    assert settings.get("project.id") is None
    assert settings.origin("capture.diff_kb") == Origin(Layer.ENV, "EAGAIN_CAPTURE_DIFF_KB")
    assert settings.warnings == []


def test_per_tool_overrides_keep_quoted_keys(home: Path, repo: Path) -> None:
    user_file(
        home,
        '[capture.tools.WebFetch]\ntool_output_ok_kb = 0.5\n[capture.tools."mcp.x"]\ndiff_kb = 0\n',
    )
    settings = load_in(home, repo)
    assert settings.get(("capture", "tools", "WebFetch", "tool_output_ok_kb")) == 0.5
    assert settings.get(("capture", "tools", "mcp.x", "diff_kb")) == 0
    assert settings.get("capture.tool_output_ok_kb") == 2


def test_invalid_values_name_file_key_and_reason(home: Path, repo: Path) -> None:
    path = user_file(home, '[retention]\nmax_store_mb = "big"\non_limit = "explode"\n')
    with pytest.raises(ConfigError) as exc:
        load_in(home, repo, {"EAGAIN_CAPTURE_DIFFS": "maybe"})
    found = {(e.source, e.key, e.message) for e in exc.value.errors}
    assert found == {
        (str(path), "retention.max_store_mb", "must be a number"),
        (
            str(path),
            "retention.on_limit",
            "must be one of compact, delete_oldest, warn, stop_indexing",
        ),
        ("environment", "EAGAIN_CAPTURE_DIFFS", "must be true or false"),
    }


def test_malformed_toml_and_missing_config_file(home: Path, repo: Path, tmp_path: Path) -> None:
    path = user_file(home, "[retention\n")
    with pytest.raises(ConfigError) as exc:
        load_in(home, repo, config_file=tmp_path / "nope.toml")
    sources = [e.source for e in exc.value.errors]
    assert sources == [str(path), str(tmp_path / "nope.toml")]
    assert "cannot read config" in exc.value.errors[0].message
    assert exc.value.errors[1].message == "config file not found"


# --- FR-19 AC4: unknown keys warn and name the closest valid key -------------


def test_fr19_ac4_typo_names_the_closest_key(home: Path, repo: Path) -> None:
    path = user_file(home, "[retention]\nmax_stor_mb = 100\n")
    settings = load_in(home, repo)
    assert settings.get("retention.max_store_mb") == 2048
    [warning] = settings.warnings
    assert (warning.source, warning.key) == (str(path), "retention.max_stor_mb")
    assert "did you mean retention.max_store_mb?" in warning.message


def test_fr19_ac4_typo_in_a_per_tool_table(home: Path, repo: Path) -> None:
    user_file(home, "[capture.tools.WebFetch]\ntool_output_ok_k = 1\n")
    [warning] = load_in(home, repo).warnings
    assert "did you mean capture.tools.WebFetch.tool_output_ok_kb?" in warning.message


def test_fr19_ac4_typo_in_an_environment_variable(home: Path, repo: Path) -> None:
    [warning] = load_in(home, repo, {"EAGAIN_RETENTION_MAX_STOR_MB": "1"}).warnings
    assert warning.key == "EAGAIN_RETENTION_MAX_STOR_MB"
    assert "did you mean EAGAIN_RETENTION_MAX_STORE_MB?" in warning.message


def test_fr19_ac4_unrelated_key_warns_without_a_guess(home: Path, repo: Path) -> None:
    user_file(home, "[telemetry]\nenabled = true\n")
    [warning] = load_in(home, repo).warnings
    assert warning.key == "telemetry.enabled"
    assert warning.message == "unknown setting, ignored"


# --- FR-19 AC6: versioned files ---------------------------------------------


def test_fr19_ac6_explicit_current_version_loads(home: Path, repo: Path) -> None:
    user_file(home, 'version = 1\n[operation]\nlog_level = "info"\n')
    assert load_in(home, repo).get("operation.log_level") == "info"


def test_fr19_ac6_older_version_is_migrated(
    home: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rename_level(data: dict[str, Any]) -> dict[str, Any]:
        op = data.setdefault("operation", {})
        op["log_level"] = op.pop("verbosity")
        return data

    monkeypatch.setattr(loader, "CURRENT_VERSION", 2)
    monkeypatch.setitem(loader.MIGRATIONS, 1, rename_level)
    user_file(home, 'version = 1\n[operation]\nverbosity = "error"\n')
    settings = load_in(home, repo)
    assert settings.get("operation.log_level") == "error"
    assert settings.warnings == []


def test_fr19_ac6_unmigratable_version_gives_a_migration_message(
    home: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loader, "CURRENT_VERSION", 3)
    path = user_file(home, "version = 1\n")
    with pytest.raises(ConfigError) as exc:
        load_in(home, repo)
    [error] = exc.value.errors
    assert (error.source, error.key) == (str(path), "version")
    assert "no longer supported" in error.message
    assert "eagain config init" in error.message


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("version = 9\n", "newer than this eagain supports"),
        ('version = "1"\n', "must be an integer"),
    ],
)
def test_fr19_ac6_newer_or_malformed_version_is_rejected(
    home: Path, repo: Path, text: str, message: str
) -> None:
    user_file(home, text)
    with pytest.raises(ConfigError, match=message):
        load_in(home, repo)


# --- NFR-12 -----------------------------------------------------------------


def test_nfr12_loading_every_layer_is_fast(home: Path, repo: Path, tmp_path: Path) -> None:
    user_file(home, 'preset = "full"\n[capture.tools.WebFetch]\ntool_output_ok_kb = 0.5\n')
    write(repo / ".eagain.toml", '[project]\nid = "x"\n')
    extra = write(tmp_path / "extra.toml", '[operation]\nlog_level = "info"\n')
    env = {"EAGAIN_RETENTION_MAX_TRACES": "5"}
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        load_in(home, repo, env, config_file=extra, flags={"capture.diffs": False})
        timings.append(time.perf_counter() - start)
    assert sorted(timings)[2] < 0.05
