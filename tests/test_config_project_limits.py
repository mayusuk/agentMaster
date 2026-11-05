"""Limits on a repository's untrusted .eagain.toml (Spec 003 FR-20)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eagain.config.definition import SETTINGS, ProjectAccess
from eagain.config.loader import ConfigError, Layer, Origin, Settings, load


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


def project(repo: Path, text: str) -> Path:
    path = repo / ".eagain.toml"
    path.write_text(text, encoding="utf-8")
    return path


def user(home: Path, text: str) -> None:
    path = home / ".config" / "eagain" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(home: Path, repo: Path) -> Settings:
    return load(env={}, home=home, cwd=repo)


def warned(settings: Settings) -> dict[str, str]:
    return {w.key: w.message for w in settings.warnings}


# --- AC1: what a repository may set -------------------------------------------


def test_fr20_ac1_rules_suppressions_tool_names_reports_and_project_id(
    home: Path, repo: Path
) -> None:
    path = project(
        repo,
        """
[rules.retry-loop]
min_attempts = 5
severity = "medium"

[rules.tool-failure]
enabled = false

[suppressions]
rules = ["permission-denied"]
fingerprints = ["abc123"]
projects = ["vendor/x"]
tools = ["Grep"]

[tool_names]
Bash = "shell"

[reports]
formats = ["md"]

[project]
id = "github.com/acme/app"
""",
    )
    settings = run(home, repo)
    assert settings.warnings == []
    expected = {
        "rules.retry-loop.min_attempts": 5,
        "rules.retry-loop.severity": "medium",
        "rules.tool-failure.enabled": False,
        "suppressions.rules": ["permission-denied"],
        "suppressions.fingerprints": ["abc123"],
        "suppressions.projects": ["vendor/x"],
        "suppressions.tools": ["Grep"],
        "reports.formats": ["md"],
        "project.id": "github.com/acme/app",
    }
    for name, value in expected.items():
        assert settings.get(name) == value, name
        assert settings.origin(name) == Origin(Layer.PROJECT, str(path)), name
    assert settings.get(("tool_names", "Bash")) == "shell"


def test_fr20_ac1_project_values_are_still_validated(home: Path, repo: Path) -> None:
    project(repo, '[rules.retry-loop]\nseverity = "catastrophic"\n')
    with pytest.raises(ConfigError, match="must be one of low, medium, high"):
        run(home, repo)


def test_fr20_ac1_every_allowed_setting_is_in_a_permitted_category() -> None:
    permitted = ("rules", "suppressions", "tool_names", "reports", "project")
    for s in SETTINGS:
        if s.project is ProjectAccess.ALLOW:
            assert s.key[0] in permitted, s.name


# --- AC2: capture and retention can only be tightened --------------------------


def test_fr20_ac2_lower_limits_apply_and_higher_ones_are_ignored(home: Path, repo: Path) -> None:
    project(
        repo,
        """
[capture]
message_kb = 1
tool_output_error_kb = 64

[retention]
max_store_mb = 100
max_traces = 1000
""",
    )
    settings = run(home, repo)
    assert settings.get("capture.message_kb") == 1
    assert settings.get("retention.max_store_mb") == 100
    assert settings.get("retention.max_traces") == 1000  # any limit is tighter than none
    assert settings.get("capture.tool_output_error_kb") == 8
    message = warned(settings)["capture.tool_output_error_kb"]
    assert "would loosen 8 to 64" in message
    assert "FR-20 AC2" in message


def test_fr20_ac2_compares_with_the_user_value_in_effect(home: Path, repo: Path) -> None:
    user(home, "[capture]\nmessage_kb = 1\n[retention]\nmax_traces = 50\n")
    project(repo, "[capture]\nmessage_kb = 2\n[retention]\nmax_traces = 10\n")
    settings = run(home, repo)
    assert settings.get("capture.message_kb") == 1
    assert settings.get("retention.max_traces") == 10
    assert list(warned(settings)) == ["capture.message_kb"]


def test_fr20_ac2_cannot_remove_a_limit(home: Path, repo: Path) -> None:
    user(home, "[retention]\nmax_age_days = 30\n")
    # TOML has no null, so a repository cannot write "none"; raising the limit is the only way.
    project(repo, "[retention]\nmax_age_days = 3650\n")
    settings = run(home, repo)
    assert settings.get("retention.max_age_days") == 30
    assert "would loosen 30 to 3650" in warned(settings)["retention.max_age_days"]


def test_fr20_ac2_switches_only_turn_capture_down(home: Path, repo: Path) -> None:
    project(
        repo,
        """
[capture]
reasoning = false
diffs = true

[retention]
keep_rollups = false
auto_prune = true
""",
    )
    settings = run(home, repo)
    assert settings.get("capture.reasoning") is False
    assert settings.get("capture.diffs") is True
    assert settings.get("retention.keep_rollups") is False
    assert settings.warnings == []

    user(home, "[capture]\ndiffs = false\n[retention]\nauto_prune = false\n")
    project(repo, "[capture]\ndiffs = true\n[retention]\nauto_prune = false\n")
    settings = run(home, repo)
    assert settings.get("capture.diffs") is False
    assert list(warned(settings)) == ["capture.diffs"]


def test_fr20_ac2_exclusion_lists_are_only_extended(home: Path, repo: Path) -> None:
    user(home, '[capture]\nexclude_tools = ["WebFetch"]\n')
    project(repo, '[capture]\nexclude_tools = ["Bash"]\nexclude_paths = ["secrets/**"]\n')
    settings = run(home, repo)
    assert settings.get("capture.exclude_tools") == ["WebFetch", "Bash"]
    assert settings.get("capture.exclude_paths") == ["secrets/**"]
    assert settings.warnings == []


def test_fr20_ac2_per_tool_overrides_compare_with_the_base_limit(home: Path, repo: Path) -> None:
    project(
        repo,
        """
[capture.tools.WebFetch]
tool_output_ok_kb = 0.5

[capture.tools.Read]
tool_output_ok_kb = 50
""",
    )
    settings = run(home, repo)
    assert settings.get(("capture", "tools", "WebFetch", "tool_output_ok_kb")) == 0.5
    assert ("capture", "tools", "Read", "tool_output_ok_kb") not in settings.values
    assert "would loosen 2 to 50" in warned(settings)["capture.tools.Read.tool_output_ok_kb"]


def test_fr20_ac2_on_limit_has_no_strictness_order_so_is_denied(home: Path, repo: Path) -> None:
    project(repo, '[retention]\non_limit = "warn"\n')
    settings = run(home, repo)
    assert settings.get("retention.on_limit") == "compact"
    assert "cannot be set by project config" in warned(settings)["retention.on_limit"]


def test_fr20_ac2_environment_and_flags_may_still_loosen(home: Path, repo: Path) -> None:
    project(repo, "[capture]\nmessage_kb = 1\n")
    settings = load(env={"EAGAIN_CAPTURE_MESSAGE_KB": "32"}, home=home, cwd=repo)
    assert settings.get("capture.message_kb") == 32
    assert settings.origin("capture.message_kb") == Origin(Layer.ENV, "EAGAIN_CAPTURE_MESSAGE_KB")


# --- AC3: redaction patterns are literal ---------------------------------------


def test_fr20_ac3_project_patterns_are_escaped_and_added(home: Path, repo: Path) -> None:
    user(home, '[redaction]\npatterns = ["tok_[0-9]+"]\n')
    project(repo, '[redaction]\npatterns = ["(a+)+$", "acme.internal"]\n')
    settings = run(home, repo)
    patterns = settings.get("redaction.patterns")
    assert patterns == ["tok_[0-9]+", re.escape("(a+)+$"), re.escape("acme.internal")]
    # The crafted pattern only ever matches its own text.
    evil = re.compile(patterns[1])
    assert evil.search("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!") is None
    assert evil.search("x (a+)+$ y") is not None
    assert re.compile(patterns[2]).search("acmeXinternal") is None


def test_fr20_ac3_user_patterns_stay_regular_expressions(home: Path, repo: Path) -> None:
    user(home, '[redaction]\npatterns = ["tok_[0-9]+"]\n')
    assert run(home, repo).get("redaction.patterns") == ["tok_[0-9]+"]


# --- AC4: keys a repository can never set --------------------------------------


@pytest.mark.parametrize(
    ("toml", "key"),
    [
        ('[llm]\nendpoint = "https://collector.example"\n', "llm.endpoint"),
        ('[llm]\nprovider = "x"\n', "llm.provider"),
        ('[paths]\nreports = "/tmp/out"\n', "paths.reports"),
        ('[paths]\ndrafts = "/tmp/drafts"\n', "paths.drafts"),
        ('[sources.claude-code]\npaths = ["/"]\n', "sources.claude-code.paths"),
        ('[projects."github.com/a/b"]\nsharing = "all"\n', 'projects."github.com/a/b".sharing'),
        ('[projects."github.com/a/b"]\ngroup = "team"\n', 'projects."github.com/a/b".group'),
        ('[sharing]\ndefault = "all"\n', "sharing.default"),
        ('[groups]\nteam = ["a"]\n', "groups.team"),
        ('[redaction]\nallowlist = ["sk-live-123"]\n', "redaction.allowlist"),
        ('[redaction]\ndisabled = ["api-key"]\n', "redaction.disabled"),
        ('preset = "full"\n', "preset"),
    ],
)
def test_fr20_ac4_denied_keys_are_ignored_with_a_warning(
    home: Path, repo: Path, toml: str, key: str
) -> None:
    path = project(repo, toml)
    settings = run(home, repo)
    [warning] = settings.warnings
    assert (warning.source, warning.key) == (str(path), key)
    assert warning.message == "cannot be set by project config (Spec 003 FR-20 AC4), ignored"
    assert all(o.layer is not Layer.PROJECT for o in settings.origins.values())


def test_fr20_ac4_denied_keys_are_ignored_even_when_malformed(home: Path, repo: Path) -> None:
    project(repo, "[llm]\nconfirm = 3\n")
    settings = run(home, repo)
    assert settings.get("llm.confirm") is True
    assert list(warned(settings)) == ["llm.confirm"]


def test_fr20_ac4_user_config_can_set_what_projects_cannot(home: Path, repo: Path) -> None:
    user(home, '[llm]\nendpoint = "http://localhost:8080"\n[redaction]\nallowlist = ["x"]\n')
    settings = run(home, repo)
    assert settings.get("llm.endpoint") == "http://localhost:8080"
    assert settings.get("redaction.allowlist") == ["x"]
    assert settings.warnings == []
