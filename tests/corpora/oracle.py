"""Independent oracle for Claude Code transcripts (plan section 5, point 2; signals from section 6).

Counts raw source signals so that the importer can later be checked against numbers it
had no part in producing. It deliberately shares no code with ``eagain`` or the test
helpers: standard library only, so it can also run on its own against
``~/.claude/projects``::

    python tests/corpora/oracle.py PATH [PATH ...]

Each PATH is a ``.jsonl`` file, or a directory searched recursively for them. The output
is JSON holding counts and record type names only (names that are not short
identifiers are counted as ``<other>``). Transcript text is untrusted: it is
parsed and matched, never printed, stored or executed.

Signal definitions (work plan #13, Decisions D1 to D6):

- ``tool_results``: ``tool_result`` blocks in user record content.
- ``tool_errors``: those with ``is_error: true``, denials included.
- ``permission_denials``: error results whose content holds Claude Code's rejection sentence.
- ``permission_decisions_rejected``: ``permissionDecision.decision`` present and not ``accept``.
- ``interrupts``: user records whose text holds the interrupt marker, once per record.
- ``api_error_records``: ``system`` records with subtype ``api_error``.
- ``api_error_messages``: assistant records with ``isApiErrorMessage: true``.
- ``subagent_runs``: distinct ``(sessionId, agentId)`` pairs on ``isSidechain`` records.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

DENIAL_MARKER = "doesn't want to proceed with this tool use"
INTERRUPT_MARKER = "[Request interrupted by user"
ACCEPT = "accept"
# Record type names reach the output, and the input is untrusted, so only short
# identifier-like names are kept; anything else is counted under OTHER_TYPE.
TYPE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,39}")
OTHER_TYPE = "<other>"

COUNT_KEYS = (
    "files",
    "records",
    "blank_lines",
    "malformed_lines",
    "sessions",
    "tool_results",
    "tool_errors",
    "interrupts",
    "permission_denials",
    "permission_decisions_rejected",
    "api_error_records",
    "api_error_messages",
    "subagent_runs",
)


@dataclass
class Result:
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNT_KEYS, 0))
    records_by_type: Counter[str] = field(default_factory=Counter)

    def to_json(self) -> dict[str, object]:
        by_type = dict(sorted(self.records_by_type.items()))
        return {"counts": dict(self.counts), "records_by_type": by_type}


def _text_of(content: object) -> str:
    """Text in a message or tool result ``content``: a string, or a list of text blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"]
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        )
    return ""


def _blocks(record: dict[str, object]) -> list[dict[str, object]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


class _Scanner:
    def __init__(self) -> None:
        self.result = Result()
        self.sessions: set[str] = set()
        self.subagents: set[tuple[str, str]] = set()

    def record(self, r: dict[str, object]) -> None:
        c = self.result.counts
        rtype = r.get("type")
        ok = isinstance(rtype, str) and TYPE_NAME.fullmatch(rtype)
        self.result.records_by_type[rtype if ok and isinstance(rtype, str) else OTHER_TYPE] += 1
        c["records"] += 1

        session = r.get("sessionId")
        if isinstance(session, str) and session:
            self.sessions.add(session)
        agent = r.get("agentId")
        if r.get("isSidechain") is True and isinstance(agent, str) and agent:
            self.subagents.add((session if isinstance(session, str) else "", agent))

        decision = r.get("permissionDecision")
        if isinstance(decision, dict) and "decision" in decision and decision["decision"] != ACCEPT:
            c["permission_decisions_rejected"] += 1

        if rtype == "user":
            message = r.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if INTERRUPT_MARKER in _text_of(content):
                c["interrupts"] += 1
            for block in _blocks(r):
                if block.get("type") != "tool_result":
                    continue
                c["tool_results"] += 1
                if block.get("is_error") is True:
                    c["tool_errors"] += 1
                    if DENIAL_MARKER in _text_of(block.get("content")):
                        c["permission_denials"] += 1
        elif rtype == "assistant":
            if r.get("isApiErrorMessage") is True:
                c["api_error_messages"] += 1
        elif rtype == "system" and r.get("subtype") == "api_error":
            c["api_error_records"] += 1

    def file(self, path: Path) -> None:
        c = self.result.counts
        c["files"] += 1
        with path.open("rb") as f:
            for raw in f:
                if not raw.strip():
                    c["blank_lines"] += 1
                    continue
                try:
                    # Decode explicitly: json.loads on bytes would guess UTF-16 or UTF-32.
                    r = json.loads(raw.decode("utf-8"))
                except ValueError:  # UnicodeDecodeError and JSONDecodeError
                    c["malformed_lines"] += 1
                    continue
                if isinstance(r, dict):
                    self.record(r)
                else:
                    c["malformed_lines"] += 1

    def finish(self) -> Result:
        self.result.counts["sessions"] = len(self.sessions)
        self.result.counts["subagent_runs"] = len(self.subagents)
        return self.result


def scan(paths: Iterable[Path]) -> Result:
    """Count the signals across ``paths``, which must be files."""
    scanner = _Scanner()
    for path in paths:
        scanner.file(path)
    return scanner.finish()


def expand(paths: Iterable[Path]) -> list[Path]:
    """Files as given, and directories searched recursively for ``*.jsonl``, in sorted order."""
    out: list[Path] = []
    for p in paths:
        out.extend(sorted(p.rglob("*.jsonl")) if p.is_dir() else [p])
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or any(a.startswith("-") for a in args):
        print("usage: oracle.py PATH [PATH ...]", file=sys.stderr)
        return 2
    paths = [Path(a).expanduser() for a in args]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"oracle: no such path: {', '.join(missing)}", file=sys.stderr)
        return 2
    json.dump(scan(expand(paths)).to_json(), sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
