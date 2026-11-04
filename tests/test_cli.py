from __future__ import annotations

import socket
import subprocess
import sys

import pytest

from eagain import __version__
from eagain.cli import ExitCode, main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"eagain {__version__}"


def test_no_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == ExitCode.OK
    assert "usage: eagain" in capsys.readouterr().out


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "eagain", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == f"eagain {__version__}"


def test_fr7_ac2_exit_codes() -> None:
    assert [int(c) for c in ExitCode] == [0, 1, 2, 3]


def test_network_is_blocked_by_default() -> None:
    with pytest.raises(RuntimeError, match="network access attempted"):
        socket.create_connection(("example.com", 443))
