"""Load settings from every source, in the order of Spec 003 section 2.

Later sources win: defaults, preset, user config, project config, environment
variables, then command-line flags (``--config <file>`` first, explicit flags last).
Every value keeps its origin, so ``config show --origin`` can say where it came from.

A repository's ``.eagain.toml`` is untrusted (Spec 003 FR-20). It may set
settings marked ``allow``; it may only tighten capture and retention, compared
with the value already in effect; its redaction patterns are added as literal
strings; and everything else is ignored with a warning.
"""

from __future__ import annotations

import difflib
import os
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from eagain.config.definition import (
    PRESETS,
    SETTINGS,
    WILDCARD,
    KeyPath,
    Kind,
    ProjectAccess,
    Setting,
    Tighter,
    concrete_settings,
    format_key,
    lookup,
    parse_key,
)

CURRENT_VERSION = 1
"""Config file format version this release writes and reads."""

MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}
"""``MIGRATIONS[n]`` turns a version ``n`` file's table into version ``n + 1`` (FR-19 AC6)."""

PROJECT_FILE = ".eagain.toml"
ENV_PREFIX = "EAGAIN_"
RESERVED_ENV = frozenset({"EAGAIN_HOME", "EAGAIN_REQUIRE_CORPORA"})
"""``EAGAIN_*`` variables that are not settings."""

PROJECT_DENIED_NAMESPACES = frozenset(
    {"llm", "paths", "sources", "projects", "sharing", "groups", "preset"}
)
"""Top-level sections a repository may never set, including keys later releases add
(Spec 002's ``projects.<id>.sharing`` and ``.group``, ``paths.drafts``): FR-20 AC4."""

_SKIP = object()


class Layer(StrEnum):
    DEFAULT = "default"
    PRESET = "preset"
    USER = "user config"
    PROJECT = "project config"
    ENV = "environment"
    CONFIG_FILE = "--config"
    FLAG = "flag"


@dataclass(frozen=True)
class Origin:
    layer: Layer
    source: str = ""
    """File path, environment variable or preset name."""

    def __str__(self) -> str:
        return f"{self.layer} ({self.source})" if self.source else str(self.layer)


@dataclass(frozen=True)
class Diagnostic:
    source: str
    key: str
    message: str

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}{self.key + ': ' if self.key else ''}{self.message}"


class ConfigError(Exception):
    """Invalid configuration. Each diagnostic names the file, the key and the reason."""

    def __init__(self, errors: list[Diagnostic], warnings: list[Diagnostic]) -> None:
        super().__init__("\n".join(str(e) for e in errors))
        self.errors = errors
        self.warnings = warnings


@dataclass
class Settings:
    values: dict[KeyPath, Any]
    origins: dict[KeyPath, Origin]
    warnings: list[Diagnostic] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    """Config files that were read, in precedence order."""

    def get(self, name: str | KeyPath) -> Any:
        return self.values[parse_key(name) if isinstance(name, str) else name]

    def origin(self, name: str | KeyPath) -> Origin:
        return self.origins[parse_key(name) if isinstance(name, str) else name]


@dataclass
class _Source:
    layer: Layer
    name: str
    values: dict[KeyPath, Any]


@dataclass
class _Collector:
    errors: list[Diagnostic] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)

    def error(self, source: str, key: str, message: str) -> None:
        self.errors.append(Diagnostic(source, key, message))

    def warn(self, source: str, key: str, message: str) -> None:
        self.warnings.append(Diagnostic(source, key, message))


def load(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    cwd: Path | None = None,
    config_file: Path | None = None,
    no_project_config: bool = False,
    flags: Mapping[str | KeyPath, Any] | None = None,
) -> Settings:
    """Merge every configuration source. Raises ``ConfigError`` if any value is invalid."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    cwd = Path.cwd() if cwd is None else cwd
    out = _Collector()
    sources: list[_Source] = []
    files: list[Path] = []

    user = user_config_path(env, home)
    if user.is_file():
        sources.append(_read_file(user, Layer.USER, out))
        files.append(user)
    if not no_project_config and (project := find_project_config(cwd)) is not None:
        sources.append(_read_file(project, Layer.PROJECT, out))
        files.append(project)
    sources.append(_read_env(env, out))
    if config_file is not None:
        if config_file.is_file():
            sources.append(_read_file(config_file, Layer.CONFIG_FILE, out))
            files.append(config_file)
        else:
            out.error(str(config_file), "", "config file not found")
    sources.append(
        _Source(
            Layer.FLAG,
            "",
            {parse_key(k) if isinstance(k, str) else k: v for k, v in (flags or {}).items()},
        )
    )

    accepted = [_accept(src, out) for src in sources]

    values: dict[KeyPath, Any] = {}
    origins: dict[KeyPath, Origin] = {}
    for s in concrete_settings():
        values[s.key] = _copy(s.default)
        origins[s.key] = Origin(Layer.DEFAULT)

    preset = values[("preset",)]
    for src in accepted:
        if ("preset",) in src.values:
            preset = src.values[("preset",)]
    for key, value in PRESETS.get(preset, {}).items():
        values[key] = _copy(value)
        origins[key] = Origin(Layer.PRESET, preset)

    for src in accepted:
        for key, value in src.values.items():
            if src.layer is Layer.PROJECT:
                value = _project_value(key, value, values, src.name, out)
                if value is _SKIP:
                    continue
            values[key] = value
            origins[key] = Origin(src.layer, src.name)

    if out.errors:
        raise ConfigError(out.errors, out.warnings)
    return Settings(values, origins, out.warnings, files)


def user_config_path(env: Mapping[str, str], home: Path) -> Path:
    if env.get("EAGAIN_HOME"):
        return Path(env["EAGAIN_HOME"]).expanduser() / "config.toml"
    return home / ".config" / "eagain" / "config.toml"


def find_project_config(cwd: Path) -> Path | None:
    """The nearest ``.eagain.toml`` at or above ``cwd``, without leaving the repository."""
    for d in (cwd, *cwd.parents):
        if (d / PROJECT_FILE).is_file():
            return d / PROJECT_FILE
        if (d / ".git").exists():
            return None
    return None


def _read_file(path: Path, layer: Layer, out: _Collector) -> _Source:
    name = str(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        out.error(name, "", f"cannot read config: {exc}")
        return _Source(layer, name, {})
    migrated = _migrate(data, name, out)
    return _Source(layer, name, {} if migrated is None else _flatten(migrated))


def _migrate(data: dict[str, Any], name: str, out: _Collector) -> dict[str, Any] | None:
    version = data.pop("version", CURRENT_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        out.error(name, "version", "must be an integer")
        return None
    if version > CURRENT_VERSION:
        out.error(
            name,
            "version",
            f"config version {version} is newer than this eagain supports ({CURRENT_VERSION}); "
            "upgrade eagain or lower the version",
        )
        return None
    while version < CURRENT_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            out.error(
                name,
                "version",
                f"config version {version} is no longer supported; "
                f"rewrite the file for version {CURRENT_VERSION} (see `eagain config init`)",
            )
            return None
        data = step(data)
        version += 1
    return data


def _flatten(table: Mapping[str, Any], prefix: KeyPath = ()) -> dict[KeyPath, Any]:
    flat: dict[KeyPath, Any] = {}
    for k, v in table.items():
        if isinstance(v, dict):
            flat.update(_flatten(v, (*prefix, k)))
        else:
            flat[(*prefix, k)] = v
    return flat


def env_var(key: KeyPath) -> str:
    """``("sources", "claude-code", "paths")`` -> ``EAGAIN_SOURCES_CLAUDE_CODE_PATHS``."""
    return ENV_PREFIX + "_".join(seg.upper().replace("-", "_") for seg in key)


def _env_names() -> dict[str, Setting]:
    return {env_var(s.key): s for s in concrete_settings()}


def _read_env(env: Mapping[str, str], out: _Collector) -> _Source:
    names = _env_names()
    values: dict[KeyPath, Any] = {}
    for var in sorted(env):
        if not var.startswith(ENV_PREFIX) or var in RESERVED_ENV:
            continue
        setting = names.get(var)
        if setting is None:
            close = difflib.get_close_matches(var, names, n=1)
            hint = f"; did you mean {close[0]}?" if close else ""
            out.warn("environment", var, f"unknown variable, ignored{hint}")
            continue
        try:
            values[setting.key] = _parse_env_value(env[var], setting)
        except ValueError as exc:
            out.error("environment", var, str(exc))
    return _Source(Layer.ENV, "", values)


def _parse_env_value(raw: str, setting: Setting) -> Any:
    text = raw.strip()
    if setting.optional and text.lower() in ("", "none"):
        return None
    if setting.kind is Kind.BOOL:
        lowered = text.lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValueError("must be true or false")
    if setting.kind is Kind.INT:
        try:
            return int(text)
        except ValueError:
            raise ValueError("must be an integer") from None
    if setting.kind is Kind.FLOAT:
        try:
            return float(text)
        except ValueError:
            raise ValueError("must be a number") from None
    if setting.kind is Kind.STR_LIST:
        if text.startswith("["):
            try:
                return tomllib.loads(f"v = {text}")["v"]
            except tomllib.TOMLDecodeError:
                raise ValueError("must be a TOML array or a comma-separated list") from None
        return [part.strip() for part in text.split(",") if part.strip()]
    return raw


def _accept(src: _Source, out: _Collector) -> _Source:
    """Keep known, valid, permitted values; report the rest."""
    kept: dict[KeyPath, Any] = {}
    where = src.name or str(src.layer)
    for key, value in src.values.items():
        name = format_key(key)
        setting = lookup(key)
        if src.layer is Layer.PROJECT and (
            key[0] in PROJECT_DENIED_NAMESPACES
            or (setting is not None and setting.project is ProjectAccess.DENY)
        ):
            out.warn(where, name, "cannot be set by project config (Spec 003 FR-20 AC4), ignored")
            continue
        if setting is None:
            hint = _suggest(key)
            out.warn(
                where, name, f"unknown setting, ignored{f'; did you mean {hint}?' if hint else ''}"
            )
            continue
        problem = setting.check(value)
        if problem is not None:
            out.error(where, name, problem)
            continue
        kept[key] = value
    return _Source(src.layer, src.name, kept)


def _project_value(
    key: KeyPath, value: Any, values: Mapping[KeyPath, Any], where: str, out: _Collector
) -> Any:
    """The value a project setting may contribute, or ``_SKIP`` if it would weaken anything."""
    setting = lookup(key)
    if setting is None:  # _accept already dropped unknown keys
        return _SKIP
    if setting.project is ProjectAccess.ALLOW:
        return value
    inherited = _inherited(key, values)
    if setting.project is ProjectAccess.LITERAL:
        # FR-20 AC3: a crafted regular expression could stall redaction, so match literally.
        return _union(inherited, [re.escape(v) for v in value])
    if setting.tighter is Tighter.SUPERSET:
        return _union(inherited, value)
    if _is_tighter(setting.tighter, value, inherited):
        return value
    out.warn(
        where,
        format_key(key),
        f"would loosen {_show(inherited)} to {_show(value)}; project config can only tighten "
        "capture and retention (Spec 003 FR-20 AC2), ignored",
    )
    return _SKIP


def _inherited(key: KeyPath, values: Mapping[KeyPath, Any]) -> Any:
    """The value in effect before project config. Per-tool and per-source capture
    overrides fall back to the base limit they override."""
    current = values.get(key)
    if current is None and len(key) == 4 and key[0] == "capture" and key[1] in ("tools", "sources"):
        return values.get(("capture", key[3]))
    return current


def _is_tighter(direction: Tighter | None, value: Any, inherited: Any) -> bool:
    if direction is Tighter.LOWER:
        if value is None:
            return inherited is None
        return inherited is None or value <= inherited
    if direction is Tighter.FALSE:
        return value is False or value == inherited
    if direction is Tighter.TRUE:
        return value is True or value == inherited
    return False


def _union(inherited: Any, extra: list[str]) -> list[str]:
    base = list(inherited or [])
    return base + [v for v in extra if v not in base]


def _show(value: Any) -> str:
    return "none" if value is None else repr(value)


def _suggest(key: KeyPath) -> str | None:
    """Closest valid key, with wildcard segments filled in from ``key`` (FR-19 AC4)."""
    candidates = []
    for s in SETTINGS:
        if s.is_pattern and len(s.key) == len(key):
            candidates.append(
                format_key(
                    tuple(k if p == WILDCARD else p for p, k in zip(s.key, key, strict=True))
                )
            )
        elif not s.is_pattern:
            candidates.append(s.name)
    close = difflib.get_close_matches(format_key(key), candidates, n=1, cutoff=0.75)
    return close[0] if close else None


def _copy(value: Any) -> Any:
    return list(value) if isinstance(value, list) else value
