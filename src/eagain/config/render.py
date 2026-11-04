"""Text rendered from the settings definition: ``config show``, ``config init`` and the
settings reference (Spec 003 FR-19 AC2, AC5 and AC9).

Everything here reads ``SETTINGS``, so the commands, the docs and the defaults cannot
drift apart. These are pure functions; the CLI does the I/O.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from typing import Any

from eagain import __version__
from eagain.config.definition import (
    PRESETS,
    SETTINGS,
    WILDCARD,
    KeyPath,
    Kind,
    ProjectAccess,
    Setting,
    format_key,
    lookup,
)
from eagain.config.loader import CURRENT_VERSION, Settings, env_var

DOC_PATH = "docs/settings.md"
DOC_COMMAND = "uv run python scripts/gen_settings_docs.py"

# Credentials in a URL's userinfo part (``https://user:token@host``).
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@")

# Names for wildcard segments, keyed by the segments before them (``config init`` and docs).
_PLACEHOLDERS: dict[KeyPath, str] = {
    ("capture", "tools"): "<tool>",
    ("capture", "sources"): "<source>",
    ("sources",): "<agent>",
    ("tool_names",): "<source tool>",
}

_KIND_TEXT = {
    Kind.INT: "integer",
    Kind.FLOAT: "number",
    Kind.BOOL: "true or false",
    Kind.STR: "string",
    Kind.ENUM: "string",
    Kind.STR_LIST: "list of strings",
}

_PROJECT_TEXT = {
    ProjectAccess.ALLOW: "yes",
    ProjectAccess.TIGHTEN: "tighten only",
    ProjectAccess.LITERAL: "literal strings only",
    ProjectAccess.DENY: "no",
}


# --- Values -----------------------------------------------------------------


def toml_value(value: Any) -> str:
    """A TOML literal for any value a setting can hold. ``None`` has no TOML form."""
    if value is None:
        raise ValueError("TOML has no null value")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        # JSON string escapes are valid TOML basic-string escapes; TOML also bans raw DEL.
        return json.dumps(value).replace("\x7f", "\\u007f")
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise TypeError(f"no TOML form for {type(value).__name__}")


def mask_url_credentials(text: str) -> str:
    return _URL_USERINFO.sub(r"\1***@", text)


def display_value(setting: Setting | None, value: Any) -> str:
    """What ``config show`` prints. Secret-like values never appear (FR-19 AC2)."""
    if value is None:
        return "none"
    if setting is not None and setting.secret and value not in ("", []):
        if isinstance(value, list):
            return f"<hidden: {len(value)} value{'' if len(value) == 1 else 's'}>"
        return "<hidden>"
    if isinstance(value, str):
        value = mask_url_credentials(value)
    elif isinstance(value, list):
        value = [mask_url_credentials(v) if isinstance(v, str) else v for v in value]
    return toml_value(value)


# --- config show ------------------------------------------------------------


def _active_keys(settings: Settings) -> Iterator[KeyPath]:
    """Definition order; keys set under a wildcard follow their pattern, sorted."""
    for s in SETTINGS:
        if not s.is_pattern:
            if s.key in settings.values:
                yield s.key
            continue
        yield from sorted(k for k in settings.values if lookup(k) is s)


def show_lines(settings: Settings, *, origin: bool = False) -> list[str]:
    lines = []
    for key in _active_keys(settings):
        line = f"{format_key(key)} = {display_value(lookup(key), settings.values[key])}"
        if origin:
            line += f"  # {settings.origins[key]}"
        lines.append(line)
    return lines


# --- config init ------------------------------------------------------------


def example_key(setting: Setting) -> str:
    """The key with wildcard segments replaced by readable placeholders."""
    parts = [
        _PLACEHOLDERS.get(setting.key[:i], "<name>") if seg == WILDCARD else seg
        for i, seg in enumerate(setting.key)
    ]
    return format_key(parts)


def type_text(setting: Setting) -> str:
    text = _KIND_TEXT[setting.kind]
    if setting.choices:
        text = "one of " + ", ".join(setting.choices)
    if setting.minimum is not None:
        text += f", at least {setting.minimum:g}"
    return text


def _sections() -> Iterator[tuple[str, list[Setting]]]:
    groups: dict[str, list[Setting]] = {}
    for s in SETTINGS:
        groups.setdefault(s.key[0] if len(s.key) > 1 else "general", []).append(s)
    yield from groups.items()


def init_text() -> str:
    """A commented config file listing every setting and its default (FR-19 AC5).

    Only ``version`` is active, so a later change to a default still reaches the user.
    """
    out = [
        f"# eagain configuration, written by `eagain config init` (eagain {__version__}).",
        "#",
        "# Every setting is listed with its default, commented out. Uncomment a line to change it.",
        "# Later sources override this file: a project's .eagain.toml (which may set only some",
        "# settings), EAGAIN_* environment variables, then command-line flags.",
        "# `eagain config show --origin` prints each active value and where it came from.",
        "",
        f"version = {CURRENT_VERSION}",
    ]
    for section, settings in _sections():
        out += ["", f"# ---- {section} ----"]
        for s in settings:
            about = f"{s.description}. Type: {type_text(s)}. Applies: {s.applies}."
            out.append("")
            out.append(f"# {about}")
            if s.default is None:
                out += ["# Default: none (not set).", f"# {example_key(s)} ="]
            else:
                out.append(f"# {example_key(s)} = {toml_value(s.default)}")
    return "\n".join(out) + "\n"


# --- Settings reference -----------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _code(value: Any) -> str:
    return "none" if value is None else f"`{_cell(toml_value(value))}`"


def settings_markdown() -> str:
    """The settings reference committed at ``docs/settings.md`` (FR-19 AC9)."""
    out = [
        "# Settings reference",
        "",
        f"<!-- Generated from src/eagain/config/definition.py by `{DOC_COMMAND}`.",
        "     Do not edit by hand: a unit test fails when this file is out of date. -->",
        "",
        "eagain works with no configuration. Every setting below can be changed. Sources are",
        "applied in this order, and later ones win (Spec 003 section 2):",
        "",
        "1. Built-in defaults",
        "2. The preset chosen by `preset`",
        "3. User config: `~/.config/eagain/config.toml`, or `config.toml` in `$EAGAIN_HOME`",
        "4. Project config: `.eagain.toml` at the project root, restricted (Spec 003 FR-20)",
        "5. Environment variables, named in the tables below",
        "6. Command-line flags, including `--config <file>` and `--no-project-config`",
        "",
        "`eagain config show --origin` prints every active value and where it came from.",
        "`eagain config validate` checks types and ranges. `eagain config init` writes a",
        "commented file listing every setting and its default.",
        "",
        "Environment variables take lists as a TOML array or a comma-separated list, and",
        "`none` or an empty value clears an optional setting. Keys with a placeholder such",
        'as `"<tool>"` are tables you fill in, for example',
        "`capture.tools.WebFetch.tool_output_ok_kb`. They have no environment variable.",
        "",
        "**Project config** says what a repository's `.eagain.toml` may do: *yes*, *tighten only*",
        "(a stricter value than the one in effect), *literal strings only* (never regular",
        "expressions), or *no* (ignored with a warning).",
    ]
    for section, settings in _sections():
        out += [
            "",
            f"## {section}",
            "",
            "| Key | Type | Default | Applies | Project config | Environment variable "
            "| Description |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in settings:
            env = "—" if s.is_pattern else f"`{env_var(s.key)}`"
            out.append(
                f"| `{_cell(example_key(s))}` | {_cell(type_text(s))} | {_code(s.default)} "
                f"| {s.applies} | {_PROJECT_TEXT[s.project]} | {env} | {_cell(s.description)} |"
            )
    names = list(PRESETS)
    keys = sorted({k for overrides in PRESETS.values() for k in overrides}, key=format_key)
    out += [
        "",
        "## Presets",
        "",
        "A preset sets capture and retention values together. `balanced` is the default and",
        "uses the defaults above. The `minimal` and `full` values are provisional, because",
        "Spec 003 names the presets but not their values.",
        "",
        "| Key | " + " | ".join(f"`{n}`" for n in names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for key in keys:
        setting = lookup(key)
        default = None if setting is None else setting.default
        cells = [_code(PRESETS[n].get(key, default)) for n in names]
        out.append(f"| `{format_key(key)}` | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
