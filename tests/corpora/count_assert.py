"""Count-only assertions for tests on real data (plan section 5, "Handling real data").

pytest's assertion rewriting prints the values being compared, which on corpus data
could be transcript text. These helpers accept only ID -> int mappings, and fail with
a message holding IDs and numbers alone, without a traceback that could show locals.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest


def _checked(counts: Mapping[str, int], which: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int):
            # Never echo the offending key or value: either could be content.
            raise TypeError(f"{which} counts must map str IDs to int counts")
        out[key] = value
    return out


def count_mismatches(expected: Mapping[str, int], actual: Mapping[str, int]) -> list[str]:
    exp, act = _checked(expected, "expected"), _checked(actual, "actual")
    return [
        f"{key}: expected {exp.get(key, 0)}, got {act.get(key, 0)}"
        for key in sorted(exp.keys() | act.keys())
        if exp.get(key, 0) != act.get(key, 0)
    ]


def assert_counts(expected: Mapping[str, int], actual: Mapping[str, int], label: str) -> None:
    """Fail with only IDs and counts if the two mappings differ."""
    mismatches = count_mismatches(expected, actual)
    if mismatches:
        shown = mismatches[:20]
        more = f"\n  ... and {len(mismatches) - 20} more" if len(mismatches) > 20 else ""
        pytest.fail(
            f"{label}: {len(mismatches)} count(s) differ\n  " + "\n  ".join(shown) + more,
            pytrace=False,
        )
