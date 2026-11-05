"""`eagain config show`, `validate` and `init` (Spec 003 FR-19 AC2, AC3, AC5)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from eagain.cli import ExitCode, main
from eagain.config.definition import concrete_settings
from eagain.config.render import init_text


@dataclass
class Env:
    home: Path
    repo: Path

    @property
    def user_config(self) -> Path:
        return self.home / ".config" / "eagain" / "config.toml"

    def write_user(self, text: str) -> Path:
        self.user_config.parent.mkdir(parents=True, exist_ok=True)
        self.user_config.write_text(text, encoding="utf-8")
        return self.user_config

    def write_project(self, text: str) -> Path:
        path = self.repo / ".eagain.toml"
        path.write_text(text, encoding="utf-8")
        return path


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    """A clean home and a repository to run in, with no EAGAIN_* variables set."""
    home, repo = tmp_path / "home", tmp_path / "repo"
    home.mkdir()
    (repo / ".git").mkdir(parents=True)
    for var in list(os.environ):
        if var.startswith("EAGAIN_"):
            monkeypatch.delenv(var)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)
    return Env(home, repo)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


# --- FR-19 AC2: config show --------------------------------------------------


def test_fr19_ac2_show_prints_active_values(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    env.write_user("[retention]\nmax_store_mb = 100\n")
    code, out, err = run(capsys, "config", "show")
    assert (code, err) == (ExitCode.OK, "")
    lines = out.splitlines()
    assert "retention.max_store_mb = 100" in lines
    assert "capture.message_kb = 4" in lines
    assert len(lines) == len(list(concrete_settings()))
    assert "#" not in out


def test_fr19_ac2_show_origin_attributes_each_source(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = env.write_user("[retention]\nmax_store_mb = 100\n")
    project = env.write_project("[rules.retry-loop]\nmin_attempts = 5\n")
    other = env.home / "other.toml"
    other.write_text('[operation]\nlog_level = "debug"\n', encoding="utf-8")
    monkeypatch.setenv("EAGAIN_RETENTION_MAX_TRACES", "10")
    code, out, _ = run(capsys, "config", "show", "--origin", "--config", str(other))
    assert code == ExitCode.OK
    lines = out.splitlines()
    assert f"retention.max_store_mb = 100  # user config ({user})" in lines
    assert f"rules.retry-loop.min_attempts = 5  # project config ({project})" in lines
    assert "retention.max_traces = 10  # environment (EAGAIN_RETENTION_MAX_TRACES)" in lines
    assert f'operation.log_level = "debug"  # --config ({other})' in lines
    assert "capture.message_kb = 4  # default" in lines


def test_fr19_ac2_show_never_prints_secret_values(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    env.write_user(
        '[redaction]\npatterns = ["corp-token-abc123"]\nallowlist = ["AKIAFAKEFAKEFAKE"]\n'
        '[llm]\nendpoint = "https://me:hunter2@llm.example.test"\n'
    )
    monkeypatch.setenv("EAGAIN_REDACTION_PATTERNS", "corp-token-abc123,other-secret")
    code, out, err = run(capsys, "config", "show", "--origin")
    assert code == ExitCode.OK
    for secret in ("corp-token-abc123", "other-secret", "AKIAFAKEFAKEFAKE", "hunter2"):
        assert secret not in out + err
    shown = "redaction.patterns = <hidden: 2 values>  # environment (EAGAIN_REDACTION_PATTERNS)"
    assert shown in out


def test_fr19_ac2_untrusted_keys_are_escaped_in_show_and_warnings(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository's .eagain.toml is untrusted (FR-20): its keys cannot write control
    characters or unbalanced quotes to the terminal."""
    env.write_project(
        '[tool_names]\n"\\u001b[31mRED\\"q" = "x"\n[retention]\n"\\u001b[2Jclear\\u009b" = 1\n'
    )
    code, out, err = run(capsys, "config", "show")
    assert code == ExitCode.OK
    for stream in (out, err):
        assert "\x1b" not in stream
        assert "\x9b" not in stream
    assert 'tool_names."\\u001b[31mRED\\"q" = "x"' in out.splitlines()
    assert 'retention."\\u001b[2Jclear\\u009b": unknown setting' in err


def test_fr19_ac2_project_config_can_be_skipped(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    env.write_project("[rules.retry-loop]\nmin_attempts = 5\n")
    _, out, _ = run(capsys, "config", "show", "--no-project-config")
    assert "rules.retry-loop.min_attempts = 3" in out.splitlines()


def test_fr19_ac2_show_reports_warnings_on_stderr(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    user = env.write_user("[retention]\nmax_stor_mb = 1\n")
    code, out, err = run(capsys, "config", "show")
    assert code == ExitCode.OK
    assert f"warning: {user}: retention.max_stor_mb: unknown setting" in err
    assert "retention.max_store_mb" in err
    assert "max_stor_mb" not in out


# --- FR-19 AC3: config validate ----------------------------------------------


def test_fr19_ac3_valid_config_exits_0(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    user = env.write_user("[capture]\nmessage_kb = 1\n")
    code, out, err = run(capsys, "config", "validate")
    assert (code, err) == (ExitCode.OK, "")
    assert out.strip() == f"config is valid ({user})"


def test_fr19_ac3_no_config_is_valid(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "config", "validate")
    assert code == ExitCode.OK
    assert "no config files, using the defaults" in out


@pytest.mark.parametrize(
    ("toml", "key", "reason"),
    [
        ('[capture]\nmessage_kb = "big"\n', "capture.message_kb", "must be a number"),
        ("[capture]\nmessage_kb = -1\n", "capture.message_kb", "must be at least 0"),
        ('[retention]\non_limit = "panic"\n', "retention.on_limit", "must be one of compact"),
        ("[rules.retry-loop]\nmin_attempts = 0\n", "rules.retry-loop.min_attempts", "at least 1"),
        ("[llm]\nconfirm = 1\n", "llm.confirm", "must be true or false"),
        ('version = "1"\n', "version", "must be an integer"),
    ],
)
def test_fr19_ac3_invalid_config_exits_2_naming_file_key_and_reason(
    env: Env, capsys: pytest.CaptureFixture[str], toml: str, key: str, reason: str
) -> None:
    user = env.write_user(toml)
    code, out, err = run(capsys, "config", "validate")
    assert code == ExitCode.INVALID_INPUT
    assert out == ""
    assert f"error: {user}: {key}: " in err
    assert reason in err


def test_fr19_ac3_invalid_config_still_reports_its_warnings(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    user = env.write_user("[capture]\nmessage_kb = -1\nmesage_kb = 1\n")
    code, out, err = run(capsys, "config", "validate")
    assert (code, out) == (ExitCode.INVALID_INPUT, "")
    lines = err.splitlines()
    warning = next(line for line in lines if line.startswith("warning: "))
    assert warning.startswith(f"warning: {user}: capture.mesage_kb: unknown setting")
    assert "capture.message_kb" in warning
    assert f"error: {user}: capture.message_kb: must be at least 0" in lines
    # Warnings come first, so the error is the last thing on screen.
    assert lines.index(warning) < len(lines) - 1


def test_fr19_ac3_every_error_is_reported(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    env.write_user("[capture]\nmessage_kb = -1\ndiff_kb = -1\n")
    _, _, err = run(capsys, "config", "validate")
    assert err.count("error: ") == 2


def test_fr19_ac3_unreadable_toml_exits_2_naming_the_file(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    user = env.write_user("[capture\n")
    code, _, err = run(capsys, "config", "validate")
    assert code == ExitCode.INVALID_INPUT
    assert f"error: {user}: cannot read config" in err


def test_fr19_ac3_invalid_environment_variable_exits_2(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EAGAIN_CAPTURE_MESSAGE_KB", "lots")
    code, _, err = run(capsys, "config", "validate")
    assert code == ExitCode.INVALID_INPUT
    assert "error: environment: EAGAIN_CAPTURE_MESSAGE_KB: must be a number" in err


def test_fr19_ac3_missing_config_file_exits_2(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    missing = env.home / "nope.toml"
    code, _, err = run(capsys, "config", "validate", "--config", str(missing))
    assert code == ExitCode.INVALID_INPUT
    assert f"error: {missing}: config file not found" in err


def test_fr19_ac3_show_also_exits_2_on_invalid_config(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    env.write_user("[capture]\nmessage_kb = -1\n")
    code, out, _ = run(capsys, "config", "show")
    assert (code, out) == (ExitCode.INVALID_INPUT, "")


def test_fr19_ac3_warnings_do_not_fail_validation(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    project = env.write_project('[llm]\nendpoint = "https://attacker.example.test"\n')
    code, _, err = run(capsys, "config", "validate")
    assert code == ExitCode.OK
    assert f"warning: {project}: llm.endpoint: cannot be set by project config" in err


# --- FR-19 AC5: config init ---------------------------------------------------


def test_fr19_ac5_init_writes_the_user_config(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "config", "init")
    assert code == ExitCode.OK
    assert out.strip() == f"wrote {env.user_config}"
    assert env.user_config.read_text(encoding="utf-8") == init_text()
    # The written file is valid and changes nothing.
    code, out, err = run(capsys, "config", "validate")
    assert (code, err) == (ExitCode.OK, "")


def test_fr19_ac5_init_follows_eagain_home(
    env: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EAGAIN_HOME", str(env.home / "custom"))
    assert run(capsys, "config", "init")[0] == ExitCode.OK
    assert (env.home / "custom" / "config.toml").read_text(encoding="utf-8") == init_text()


def test_fr19_ac5_init_never_overwrites_without_force(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    env.write_user("[capture]\nmessage_kb = 1\n")
    code, _, err = run(capsys, "config", "init")
    assert code == ExitCode.RUNTIME_ERROR
    assert "already exists; use --force" in err
    assert env.user_config.read_text(encoding="utf-8") == "[capture]\nmessage_kb = 1\n"
    assert run(capsys, "config", "init", "--force")[0] == ExitCode.OK
    assert env.user_config.read_text(encoding="utf-8") == init_text()


def test_fr19_ac5_init_to_a_path_or_stdout(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    target = env.home / "nested" / "eagain.toml"
    assert run(capsys, "config", "init", "--path", str(target))[0] == ExitCode.OK
    assert target.read_text(encoding="utf-8") == init_text()
    code, out, _ = run(capsys, "config", "init", "--path", "-")
    assert (code, out) == (ExitCode.OK, init_text())
    assert not env.user_config.exists()


def test_init_reports_a_failed_write(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    blocker = env.home / "file"
    blocker.write_text("", encoding="utf-8")
    code, _, err = run(capsys, "config", "init", "--path", str(blocker / "config.toml"))
    assert code == ExitCode.RUNTIME_ERROR
    assert "error: cannot write" in err


def test_config_needs_an_action(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["config"])
    assert exc.value.code == ExitCode.INVALID_INPUT
