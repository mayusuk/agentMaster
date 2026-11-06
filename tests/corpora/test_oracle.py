"""Unit tests for the oracle, on synthetic transcripts only (no network, no real data)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from oracle import COUNT_KEYS, DENIAL_MARKER, INTERRUPT_MARKER, OTHER_TYPE, expand, main, scan

ORACLE = Path(__file__).with_name("oracle.py")
CANARY = "planted-transcript-text-that-must-never-be-printed"


def write(path: Path, records: list[Any] | list[str]) -> Path:
    """Write records as JSON Lines; plain strings are written verbatim as raw lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def user(content: Any, **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "sessionId": "s1",
        "message": {"role": "user", "content": content},
    } | extra


def tool_result(text: Any, is_error: Any = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": "t", "content": text}
    if is_error is not None:
        block["is_error"] = is_error
    return block


def assistant(**extra: Any) -> dict[str, Any]:
    return {"type": "assistant", "sessionId": "s1", "message": {"role": "assistant"}} | extra


def counts(tmp_path: Path, records: list[Any] | list[str]) -> dict[str, int]:
    return scan([write(tmp_path / "s.jsonl", records)]).counts


# --- Signals ------------------------------------------------------------------


def test_tool_results_and_errors_are_counted_per_block(tmp_path: Path) -> None:
    c = counts(
        tmp_path,
        [
            user([tool_result("ok"), tool_result("boom", is_error=True)]),
            user([tool_result([{"type": "text", "text": "x"}], is_error=False)]),
            # is_error must be literally true; a truthy string is not an error flag.
            user([tool_result("no", is_error="true")]),
            # A tool_result block outside a user record is not a tool result.
            assistant(message={"content": [tool_result("x", is_error=True)]}),
        ],
    )
    assert (c["tool_results"], c["tool_errors"]) == (4, 1)


def test_denials_need_an_error_result_with_the_rejection_sentence(tmp_path: Path) -> None:
    sentence = f"The user {DENIAL_MARKER}. The tool use was rejected."
    c = counts(
        tmp_path,
        [
            user([tool_result(sentence, is_error=True)]),
            user([tool_result([{"type": "text", "text": sentence}], is_error=True)]),
            user([tool_result(sentence, is_error=False)]),  # not an error result
            user([tool_result("permission denied by the filesystem", is_error=True)]),
        ],
    )
    assert (c["permission_denials"], c["tool_errors"]) == (2, 3)


def test_rejected_permission_decisions_are_counted_separately(tmp_path: Path) -> None:
    c = counts(
        tmp_path,
        [
            user("x", permissionDecision={"decision": "accept", "source": "config"}),
            user("x", permissionDecision={"decision": "reject"}),
            user("x", permissionDecision={"decision": None}),
            user("x", permissionDecision={"source": "config"}),  # no decision at all
            user("x", permissionDecision="reject"),  # not the dict shape
        ],
    )
    assert (c["permission_decisions_rejected"], c["permission_denials"]) == (2, 0)


def test_interrupts_are_user_text_markers_counted_once_per_record(tmp_path: Path) -> None:
    c = counts(
        tmp_path,
        [
            user(f"{INTERRUPT_MARKER}]"),
            user([{"type": "text", "text": f"{INTERRUPT_MARKER} for tool use]"}]),
            user(f"{INTERRUPT_MARKER}] {INTERRUPT_MARKER}]"),  # one record, one interrupt
            user([tool_result(f"{INTERRUPT_MARKER}]")]),  # inside a tool result: no
            assistant(message={"content": f"{INTERRUPT_MARKER}]"}),  # not a user record
            user("[Request interrupted by the system]"),
        ],
    )
    assert c["interrupts"] == 3


def test_api_errors_count_system_records_and_flagged_assistant_records(tmp_path: Path) -> None:
    c = counts(
        tmp_path,
        [
            {"type": "system", "subtype": "api_error"},
            {"type": "system", "subtype": "turn_duration"},
            assistant(isApiErrorMessage=True),
            assistant(isApiErrorMessage=False),  # key present but not set
            assistant(isApiErrorMessage="true"),
            user("x", isApiErrorMessage=True),  # only assistant records count
        ],
    )
    assert (c["api_error_records"], c["api_error_messages"]) == (1, 1)


def test_subagent_runs_are_distinct_sidechain_agents_in_any_layout(tmp_path: Path) -> None:
    def side(session: str, agent: Any, sidechain: Any = True) -> dict[str, Any]:
        return {"type": "user", "sessionId": session, "agentId": agent, "isSidechain": sidechain}

    files = [
        # Older layout: top-level agent-*.jsonl next to the session file.
        write(tmp_path / "s1.jsonl", [user("x", isSidechain=False)]),
        write(tmp_path / "agent-a1.jsonl", [side("s1", "a1"), side("s1", "a1")]),
        # Newer layout: <session>/subagents/..., and the same agent ID in another session.
        write(tmp_path / "s2" / "subagents" / "agent-a1.jsonl", [side("s2", "a1")]),
        write(tmp_path / "s2" / "subagents" / "agent-a2.jsonl", [side("s2", "a2")]),
        # Not runs: no agent ID, or not flagged as sidechain.
        write(tmp_path / "x.jsonl", [side("s3", None), side("s3", "a9", sidechain=False)]),
    ]
    c = scan(files).counts
    assert (c["subagent_runs"], c["sessions"]) == (3, 3)


# --- Robustness ---------------------------------------------------------------


def test_malformed_blank_and_non_object_lines_are_counted_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    write(path, [json.dumps(user([tool_result("ok")])), "", "   ", "[1, 2]", '"text"', "{not json"])
    with path.open("ab") as f:
        f.write(b'{"type": "user", "x": "\x80"}\n')  # invalid UTF-8
        f.write('{"type": "user"}\n'.encode("utf-16"))  # not UTF-8, though json could guess it
        # Truncated, with no final newline.
        f.write(b'{"type": "user", "message": {"content": [{"type": "tool_res')
    c = scan([path]).counts
    assert (c["records"], c["blank_lines"], c["malformed_lines"], c["tool_results"]) == (1, 2, 6, 1)


def test_unexpected_shapes_are_ignored(tmp_path: Path) -> None:
    c = counts(
        tmp_path,
        [
            {"type": "user", "message": "not a dict"},
            {"type": "user", "message": {"content": {"type": "tool_result"}}},
            {
                "type": "user",
                "message": {"content": [1, None, "s", tool_result(None, is_error=True)]},
            },
            {"type": None, "sessionId": 7},
            {},
        ],
    )
    assert (c["records"], c["tool_results"], c["tool_errors"], c["sessions"]) == (5, 1, 1, 0)


def test_records_by_type_keeps_only_identifier_names(tmp_path: Path) -> None:
    result = scan(
        [
            write(
                tmp_path / "s.jsonl",
                [user("x"), user("y"), {"type": "queue-operation"}, {"type": CANARY + " !"}, {}],
            )
        ]
    )
    assert dict(result.records_by_type) == {"user": 2, "queue-operation": 1, OTHER_TYPE: 2}


def test_every_count_key_is_always_present(tmp_path: Path) -> None:
    assert list(scan([]).counts) == list(COUNT_KEYS)
    assert set(counts(tmp_path, [])) == set(COUNT_KEYS)


def test_expand_searches_directories_for_jsonl_in_sorted_order(tmp_path: Path) -> None:
    b = write(tmp_path / "d" / "b.jsonl", [])
    a = write(tmp_path / "d" / "sub" / "a.jsonl", [])
    (tmp_path / "d" / "notes.txt").write_text("x", encoding="utf-8")
    loose = write(tmp_path / "loose.json", [])
    assert expand([tmp_path / "d", loose]) == [*sorted([a, b]), loose]


# --- CLI and independence -----------------------------------------------------


def test_cli_prints_counts_and_never_transcript_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path / "p" / "s.jsonl",
        [user(CANARY), user([tool_result(CANARY, is_error=True)]), {"type": CANARY}],
    )
    assert main([str(tmp_path / "p")]) == 0
    out, err = capsys.readouterr()
    assert CANARY not in out + err
    data = json.loads(out)
    assert set(data) == {"counts", "records_by_type"}
    assert (data["counts"]["files"], data["counts"]["tool_errors"]) == (1, 1)


def test_cli_rejects_missing_paths_and_no_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 2
    assert main([str(tmp_path / "missing")]) == 2
    assert capsys.readouterr().out == ""


def test_oracle_imports_nothing_from_eagain() -> None:
    """Plan section 5: the oracle shares no code with eagain, so it imports only the stdlib."""
    tree = ast.parse(ORACLE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports are not allowed in the oracle"
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "__import__", "dynamic imports are not allowed in the oracle"
    assert "eagain" not in imported
    assert "importlib" not in imported
    assert sorted(m for m in imported if m not in sys.stdlib_module_names) == []
