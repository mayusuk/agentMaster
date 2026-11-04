"""Spec coverage report (scripts/spec_coverage.py, plan section 5)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import spec_coverage as sc

ROOT = Path(__file__).resolve().parents[1]

SPEC = """# Spec 900

## 6. Functional requirements

### FR-1 First

- **AC1:** One.
- **AC2:** Two.

### FR-3 Third

- **AC1:** Three.

### FR-2 Second, listed after FR-3

- **AC1:** Four.
- **AC10:** Ten.

## 7. Non-functional requirements

- **NFR-1 Speed:** Fast.

## 8. End-to-end

- **AC9:** not under a requirement heading, so not a criterion.
"""

PLAN_TEMPLATE = """# Plan

## 4. Tasks

### M1 Done (FR-1, NFR-1)
{status}
1. Task.

### M2 Later (FR-2 to FR-3)

1. Task.
"""

TESTS = """
def test_fr1_ac1_one() -> None: ...
def test_fr1_ac2() -> None: ...
async def test_nfr1_fast() -> None: ...
def test_fr2_ac10_ten() -> None: ...
def test_fr1_ac20_not_ac2() -> None: ...
"""


def make_repo(tmp_path: Path, *, finished: bool, tests: str = TESTS) -> Path:
    (tmp_path / "specs" / "900-x").mkdir(parents=True)
    (tmp_path / "specs" / "900-x" / "spec.md").write_text(SPEC)
    status = "**Status:** Finished\n" if finished else ""
    (tmp_path / "specs" / "900-x" / "plan.md").write_text(PLAN_TEMPLATE.format(status=status))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(tests)
    return tmp_path


def test_parses_criteria_in_number_order_whatever_the_file_order(tmp_path: Path) -> None:
    report = sc.build_report(make_repo(tmp_path, finished=False))
    assert [r.criterion.id for r in report.rows] == [
        "FR-1 AC1",
        "FR-1 AC2",
        "FR-2 AC1",
        "FR-2 AC10",
        "FR-3 AC1",
        "NFR-1",
    ]


def test_tests_match_by_prefix_without_crossing_numbers(tmp_path: Path) -> None:
    rows = {
        r.criterion.id: r.tests for r in sc.build_report(make_repo(tmp_path, finished=False)).rows
    }
    assert rows["FR-1 AC1"] == ["test_fr1_ac1_one"]
    assert rows["FR-1 AC2"] == ["test_fr1_ac2"]
    assert rows["FR-2 AC1"] == []
    assert rows["FR-2 AC10"] == ["test_fr2_ac10_ten"]
    assert rows["NFR-1"] == ["test_nfr1_fast"]


def test_milestones_ranges_and_unplanned(tmp_path: Path) -> None:
    report = sc.build_report(make_repo(tmp_path, finished=False))
    owners = {r.criterion.id: r.milestone.id if r.milestone else None for r in report.rows}
    assert owners == {
        "FR-1 AC1": "M1",
        "FR-1 AC2": "M1",
        "NFR-1": "M1",
        "FR-2 AC1": "M2",
        "FR-2 AC10": "M2",
        "FR-3 AC1": "M2",
    }
    assert sc.parse_refs("FR-11, FR-18 AC4, NFR-7") == [
        ("FR", 11, None),
        ("FR", 18, 4),
        ("NFR", 7, None),
    ]


def test_gap_in_a_finished_milestone_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, finished=True, tests=TESTS.replace("test_fr1_ac2()", "test_other()"))
    assert sc.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "M1 Done (finished): 2/3 covered" in out
    assert "GAP M1: FR-1 AC2 has no test starting test_fr1_ac2_" in out


def test_gap_in_an_unfinished_milestone_does_not_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, finished=False)  # M2's FR-2 AC1 and FR-3 AC1 are untested
    assert sc.main(["--root", str(root)]) == 0
    assert "0 gap(s) in finished milestones" in capsys.readouterr().out


def test_finished_milestone_with_every_criterion_tested_passes(tmp_path: Path) -> None:
    assert sc.main(["--root", str(make_repo(tmp_path, finished=True))]) == 0


def test_reference_to_an_unknown_requirement_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, finished=False)
    plan = root / "specs" / "900-x" / "plan.md"
    plan.write_text(plan.read_text().replace("(FR-1, NFR-1)", "(FR-1, FR-99)"))
    assert sc.main(["--root", str(root)]) == 2
    assert "M1 refers to FR-99, which no spec defines" in capsys.readouterr().err


def test_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sc.main(["--root", str(make_repo(tmp_path, finished=False)), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["gaps"] == []
    assert data["milestones"][0] == {
        "id": "M1",
        "title": "Done",
        "plan": "specs/900-x/plan.md",
        "finished": False,
    }
    assert {
        "id": "FR-1 AC1",
        "spec": "specs/900-x/spec.md",
        "milestone": "M1",
        "tests": ["test_fr1_ac1_one"],
    } in (data["criteria"])


# --- The real repository ------------------------------------------------------


def test_lists_every_criterion_in_specs_001_to_003() -> None:
    report = sc.build_report(ROOT)
    for spec in sorted(ROOT.glob("specs/*/spec.md")):
        text = spec.read_text()
        rel = str(spec.relative_to(ROOT))
        listed = [r.criterion for r in report.rows if r.criterion.spec == rel]
        # Counted independently of the parser: every AC bullet, plus every NFR bullet.
        expected_acs = len(re.findall(r"(?m)^- \*\*AC\d+:\*\*", text))
        expected_nfrs = len(re.findall(r"(?m)^- \*\*NFR-\d+", text))
        assert sum(c.ac is not None for c in listed) == expected_acs, rel
        assert sum(c.kind == "NFR" for c in listed) == expected_nfrs, rel
    ids = {r.criterion.id for r in report.rows}
    assert {"FR-1 AC1", "FR-17 AC10", "FR-15 AC5", "FR-23 AC2", "NFR-1", "NFR-13"} <= ids
    assert len(ids) == 42 + 56 + 28 + 13


def test_real_repository_reports_existing_tests_and_passes() -> None:
    report = sc.build_report(ROOT)
    tests = {r.criterion.id: r.tests for r in report.rows}
    assert "test_fr7_ac2_exit_codes" in tests["FR-7 AC2"]
    assert any(t.startswith("test_nfr12_") for t in tests["NFR-12"])
    m1 = next(m for m in report.milestones if m.id == "M1")
    assert m1.refs[:2] == [("FR", 1, None), ("FR", 2, None)]
    assert ("FR", 20, None) in m1.refs
    assert sc.main(["--root", str(ROOT)]) in (0, 1)
    assert [r.criterion.id for r in report.gaps()] == [
        r.criterion.id for r in report.rows if not r.tests and r.milestone and r.milestone.finished
    ]
