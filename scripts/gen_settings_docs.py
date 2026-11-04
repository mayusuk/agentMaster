#!/usr/bin/env python3
"""Write the settings reference from the one settings definition (Spec 003 FR-19 AC9).

    uv run python scripts/gen_settings_docs.py           # rewrite docs/settings.md
    uv run python scripts/gen_settings_docs.py --check   # exit 1 if it is out of date

A unit test runs the same comparison, so CI fails when the committed file drifts.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from eagain.config.render import DOC_COMMAND, DOC_PATH, settings_markdown

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = args.root / DOC_PATH
    text = settings_markdown()
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if args.check:
        if current == text:
            return 0
        print(f"{DOC_PATH} is out of date; run `{DOC_COMMAND}`", file=sys.stderr)
        return 1
    if current != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
