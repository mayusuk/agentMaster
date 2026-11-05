"""Command-line entry point.

Exit codes follow Spec 001 FR-7 AC2.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from enum import IntEnum
from pathlib import Path

from eagain import __version__
from eagain.config.loader import ConfigError, Diagnostic, Settings, load, user_config_path
from eagain.config.render import init_text, show_lines


class ExitCode(IntEnum):
    OK = 0
    RUNTIME_ERROR = 1
    INVALID_INPUT = 2
    FAIL_ON_MATCHED = 3


Handler = Callable[[argparse.Namespace], int]


def _config_sources() -> argparse.ArgumentParser:
    """Options for every command that loads settings (Spec 003 section 2)."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="read this config file after the user and project files",
    )
    parent.add_argument(
        "--no-project-config",
        action="store_true",
        help="ignore the project's .eagain.toml",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eagain",
        description="Find what your coding agents keep getting wrong.",
    )
    parser.add_argument("--version", action="version", version=f"eagain {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    sources = _config_sources()

    config = commands.add_parser("config", help="show, check or create configuration")
    actions = config.add_subparsers(dest="action", metavar="<action>", required=True)

    show = actions.add_parser(
        "show", parents=[sources], help="print active settings; secret values are hidden"
    )
    show.add_argument("--origin", action="store_true", help="say where each value came from")
    show.set_defaults(handler=_config_show)

    validate = actions.add_parser(
        "validate", parents=[sources], help="check config types and ranges; exit 2 if invalid"
    )
    validate.set_defaults(handler=_config_validate)

    init = actions.add_parser(
        "init", help="write a commented config file listing every setting and its default"
    )
    init.add_argument(
        "--path",
        metavar="FILE",
        help="where to write it (default: the user config file); - prints it instead",
    )
    init.add_argument("--force", action="store_true", help="overwrite an existing file")
    init.set_defaults(handler=_config_init)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return ExitCode.OK
    return int(handler(args))


# --- config -----------------------------------------------------------------


def _report(level: str, diagnostics: Sequence[Diagnostic]) -> None:
    for d in diagnostics:
        print(f"{level}: {d}", file=sys.stderr)


def _load(args: argparse.Namespace) -> Settings | ExitCode:
    """Settings, or the exit code after reporting why they are invalid (FR-19 AC3)."""
    try:
        settings = load(config_file=args.config, no_project_config=args.no_project_config)
    except ConfigError as exc:
        _report("warning", exc.warnings)
        _report("error", exc.errors)
        return ExitCode.INVALID_INPUT
    _report("warning", settings.warnings)
    return settings


def _config_show(args: argparse.Namespace) -> int:
    settings = _load(args)
    if isinstance(settings, ExitCode):
        return settings
    for line in show_lines(settings, origin=args.origin):
        print(line)
    return ExitCode.OK


def _config_validate(args: argparse.Namespace) -> int:
    settings = _load(args)
    if isinstance(settings, ExitCode):
        return settings
    files = ", ".join(str(f) for f in settings.files) or "no config files, using the defaults"
    print(f"config is valid ({files})")
    return ExitCode.OK


def _config_init(args: argparse.Namespace) -> int:
    text = init_text()
    if args.path == "-":
        sys.stdout.write(text)
        return ExitCode.OK
    target = Path(args.path) if args.path else user_config_path(os.environ, Path.home())
    if target.exists() and not args.force:
        print(f"error: {target} already exists; use --force to overwrite it", file=sys.stderr)
        return ExitCode.RUNTIME_ERROR
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {target}: {exc}", file=sys.stderr)
        return ExitCode.RUNTIME_ERROR
    print(f"wrote {target}")
    return ExitCode.OK
