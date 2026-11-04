"""Command-line entry point.

Exit codes follow Spec 001 FR-7 AC2.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from enum import IntEnum

from eagain import __version__


class ExitCode(IntEnum):
    OK = 0
    RUNTIME_ERROR = 1
    INVALID_INPUT = 2
    FAIL_ON_MATCHED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eagain",
        description="Find what your coding agents keep getting wrong.",
    )
    parser.add_argument("--version", action="version", version=f"eagain {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return ExitCode.OK
