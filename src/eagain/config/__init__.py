"""Configuration: one settings definition and a loader for every source (Spec 003)."""

from eagain.config.definition import PRESETS, SETTINGS, Setting
from eagain.config.loader import ConfigError, Diagnostic, Layer, Origin, Settings, load

__all__ = [
    "PRESETS",
    "SETTINGS",
    "ConfigError",
    "Diagnostic",
    "Layer",
    "Origin",
    "Setting",
    "Settings",
    "load",
]
