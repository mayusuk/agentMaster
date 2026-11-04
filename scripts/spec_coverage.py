#!/usr/bin/env python3
"""Spec coverage report (plan section 5, definition of done point 3).

Lists every acceptance criterion in ``specs/*/spec.md``, the tests named after
it, and the milestone that owns it. Exits 1 only when a milestone marked
finished has a criterion with no test, so unfinished work never fails it.

Conventions read:

* Criteria: ``- **ACm:**`` lines under a ``### FR-n Title`` heading, and
  ``- **NFR-n ...:**`` bullets (one criterion each, ID ``NFR-n``).
* Tests: ``def test_frN_acM[_...]`` and ``def test_nfrN[_...]`` in ``tests/**/*.py``.
* Milestones: ``### Mn Title (FR-1, FR-19 to FR-21, FR-18 AC4)`` headings in
  ``specs/*/plan.md``. A milestone is finished when the first non-empty line after
  its heading is ``**Status:** Finished``.

Exit codes: 0 no gaps in finished milestones, 1 gaps, 2 the specs or plans could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REQ_HEADING = re.compile(r"^#{2,4}\s+(N?FR)-(\d+)\b")
AC_LINE = re.compile(r"^\s*[-*]\s+\*\*AC(\d+):\*\*")
NFR_BULLET = re.compile(r"^\s*[-*]\s+\*\*NFR-(\d+)\b")
MILESTONE_HEADING = re.compile(r"^###\s+(M\d+)\s+(.*?)\s*(?:\((.*)\))?\s*$")
REF = re.compile(r"(N?FR)-(\d+)(?:\s+AC(\d+))?(?:\s+to\s+(N?FR)-(\d+))?")
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)
FINISHED = re.compile(r"^\*\*Status:\*\*\s*Finished\b", re.IGNORECASE)


class CoverageError(Exception):
    """The specs or plans are not in the expected shape."""


@dataclass(frozen=True, order=True)
class Criterion:
    kind: str
    """``FR`` or ``NFR``."""
    req: int
    ac: int | None
    spec: str = field(compare=False)

    @property
    def id(self) -> str:
        return f"{self.kind}-{self.req}" + (f" AC{self.ac}" if self.ac is not None else "")

    @property
    def test_prefix(self) -> str:
        base = f"test_{self.kind.lower()}{self.req}"
        return base + (f"_ac{self.ac}" if self.ac is not None else "")

    def covered_by(self, name: str) -> bool:
        return name == self.test_prefix or name.startswith(self.test_prefix + "_")


@dataclass
class Milestone:
    id: str
    title: str
    plan: str
    finished: bool
    refs: list[tuple[str, int, int | None]]
    """(kind, requirement, AC or None for the whole requirement)."""

    def owns(self, c: Criterion) -> bool:
        return any(k == c.kind and r == c.req and (a is None or a == c.ac) for k, r, a in self.refs)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_criteria(text: str, spec: str) -> list[Criterion]:
    out: list[Criterion] = []
    current: tuple[str, int] | None = None
    for line in text.splitlines():
        if line.startswith("#"):
            m = REQ_HEADING.match(line)
            current = (m.group(1), int(m.group(2))) if m else None
            continue
        if (n := NFR_BULLET.match(line)) is not None:
            out.append(Criterion("NFR", int(n.group(1)), None, spec))
        elif current is not None and (a := AC_LINE.match(line)) is not None:
            out.append(Criterion(current[0], current[1], int(a.group(1)), spec))
    return out


def parse_refs(text: str) -> list[tuple[str, int, int | None]]:
    refs: list[tuple[str, int, int | None]] = []
    for m in REF.finditer(text):
        kind, start, ac, end_kind, end = m.groups()
        if end is not None:
            if end_kind != kind or int(end) < int(start):
                raise CoverageError(f"bad range {m.group(0)!r}")
            refs += [(kind, n, None) for n in range(int(start), int(end) + 1)]
        else:
            refs.append((kind, int(start), int(ac) if ac else None))
    return refs


def parse_milestones(text: str, plan: str) -> list[Milestone]:
    lines = text.splitlines()
    out: list[Milestone] = []
    for i, line in enumerate(lines):
        m = MILESTONE_HEADING.match(line)
        if not m:
            continue
        nxt = next((ln for ln in lines[i + 1 :] if ln.strip()), "")
        out.append(
            Milestone(
                m.group(1),
                m.group(2),
                plan,
                bool(FINISHED.match(nxt)),
                parse_refs(m.group(3) or ""),
            )
        )
    return out


def test_names(paths: Iterable[Path]) -> list[str]:
    names: set[str] = set()
    for p in paths:
        names.update(TEST_DEF.findall(p.read_text(encoding="utf-8", errors="replace")))
    return sorted(names)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


@dataclass
class Row:
    criterion: Criterion
    tests: list[str]
    milestone: Milestone | None


@dataclass
class Report:
    rows: list[Row]
    milestones: list[Milestone]

    def gaps(self) -> list[Row]:
        return [
            r for r in self.rows if not r.tests and r.milestone is not None and r.milestone.finished
        ]

    def to_json(self) -> dict[str, object]:
        return {
            "criteria": [
                {
                    "id": r.criterion.id,
                    "spec": r.criterion.spec,
                    "milestone": r.milestone.id if r.milestone else None,
                    "tests": r.tests,
                }
                for r in self.rows
            ],
            "milestones": [
                {"id": m.id, "title": m.title, "plan": m.plan, "finished": m.finished}
                for m in self.milestones
            ],
            "gaps": [r.criterion.id for r in self.gaps()],
        }

    def to_text(self) -> str:
        lines: list[str] = []
        groups: list[tuple[str, list[Row]]] = [
            (
                f"{m.id} {m.title} ({'finished' if m.finished else 'in progress'})",
                [r for r in self.rows if r.milestone is m],
            )
            for m in self.milestones
        ]
        groups.append(("Unplanned", [r for r in self.rows if r.milestone is None]))
        for title, rows in groups:
            if not rows:
                continue
            covered = sum(1 for r in rows if r.tests)
            lines.append(f"{title}: {covered}/{len(rows)} covered")
            for r in rows:
                mark = "ok  " if r.tests else "--  "
                lines.append(f"  {mark}{r.criterion.id:<14} {', '.join(r.tests)}")
        gaps = self.gaps()
        total = sum(1 for r in self.rows if r.tests)
        lines.append("")
        lines.append(
            f"{total}/{len(self.rows)} criteria covered; {len(gaps)} gap(s) in finished milestones"
        )
        for r in gaps:
            owner = r.milestone.id if r.milestone else "?"
            prefix = r.criterion.test_prefix
            lines.append(f"  GAP {owner}: {r.criterion.id} has no test starting {prefix}_")
        return "\n".join(lines)


def build_report(root: Path) -> Report:
    specs = sorted(root.glob("specs/*/spec.md"))
    if not specs:
        raise CoverageError(f"no specs/*/spec.md under {root}")
    criteria: list[Criterion] = []
    for p in specs:
        criteria += parse_criteria(p.read_text(encoding="utf-8"), str(p.relative_to(root)))
    criteria.sort()
    if len(set(criteria)) != len(criteria):
        dupes = sorted({c.id for c in criteria if criteria.count(c) > 1})
        raise CoverageError(f"criteria defined twice: {', '.join(dupes)}")

    milestones: list[Milestone] = []
    for p in sorted(root.glob("specs/*/plan.md")):
        milestones += parse_milestones(p.read_text(encoding="utf-8"), str(p.relative_to(root)))
    known_reqs = {(c.kind, c.req) for c in criteria}
    known_acs = {(c.kind, c.req, c.ac) for c in criteria}
    for m in milestones:
        for kind, req, ac in m.refs:
            if (kind, req) not in known_reqs or (
                ac is not None and (kind, req, ac) not in known_acs
            ):
                ref = f"{kind}-{req}" + (f" AC{ac}" if ac is not None else "")
                raise CoverageError(f"{m.plan}: {m.id} refers to {ref}, which no spec defines")

    names = test_names(sorted(root.glob("tests/**/*.py")))
    rows = []
    for c in criteria:
        owner = next((m for m in milestones if m.owns(c)), None)
        rows.append(Row(c, [n for n in names if c.covered_by(n)], owner))
    return Report(rows, milestones)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.root)
    except CoverageError as exc:
        print(f"spec coverage: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_json(), indent=2) if args.json else report.to_text())
    return 1 if report.gaps() else 0


if __name__ == "__main__":
    sys.exit(main())
