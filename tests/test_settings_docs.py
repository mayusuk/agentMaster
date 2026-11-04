"""Generated settings reference (Spec 003 FR-19 AC9)."""

from __future__ import annotations

from pathlib import Path

import gen_settings_docs

from eagain.config.definition import PRESETS, SETTINGS, format_key
from eagain.config.loader import env_var
from eagain.config.render import (
    DOC_COMMAND,
    DOC_PATH,
    example_key,
    settings_markdown,
    toml_value,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fr19_ac9_committed_settings_doc_is_up_to_date() -> None:
    committed = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    # Compare booleans so a failure prints the fix, not two whole documents.
    up_to_date = committed == settings_markdown()
    assert up_to_date, f"{DOC_PATH} is out of date; run `{DOC_COMMAND}` and commit it"


def test_fr19_ac9_doc_lists_every_setting_from_the_definition() -> None:
    doc = settings_markdown()
    rows = [line for line in doc.splitlines() if line.startswith("| `")]
    keys = [row.split("`")[1] for row in rows]
    setting_rows = keys[: len(SETTINGS)]
    assert setting_rows == [example_key(s) for s in SETTINGS]
    for s in SETTINGS:
        if not s.is_pattern:
            assert f"`{env_var(s.key)}`" in doc, s.name
    preset_keys = {format_key(k) for overrides in PRESETS.values() for k in overrides}
    assert sorted(keys[len(SETTINGS) :]) == sorted(preset_keys)


def test_fr19_ac9_doc_shows_each_default_from_the_definition() -> None:
    rows = {
        row.split("`")[1]: row for row in settings_markdown().splitlines() if row.startswith("| `")
    }
    for s in SETTINGS:
        default = "none" if s.default is None else f"`{toml_value(s.default)}`"
        cells = rows[example_key(s)].split(" | ")
        assert cells[2] == default.replace("|", "\\|"), s.name


def test_generator_check_and_write(tmp_path: Path) -> None:
    assert gen_settings_docs.main(["--check", "--root", str(tmp_path)]) == 1
    assert gen_settings_docs.main(["--root", str(tmp_path)]) == 0
    assert (tmp_path / DOC_PATH).read_text(encoding="utf-8") == settings_markdown()
    assert gen_settings_docs.main(["--check", "--root", str(tmp_path)]) == 0


def test_generator_check_passes_on_the_repository() -> None:
    assert gen_settings_docs.main(["--check"]) == 0
