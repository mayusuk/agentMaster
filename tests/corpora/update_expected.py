"""Regenerate ``tests/corpora/<corpus>.expected.json`` from the oracle (plan section 5, point 2).

    python tests/corpora/update_expected.py            # every corpus in the registry
    python tests/corpora/update_expected.py armand0e   # just these

Every corpus is verified against the registry first, and only the files the registry
lists are scanned, so stray files in the shared cache cannot change the counts. The
files hold the corpus ID, its pinned revision and counts, never content. Hand-check
any change before committing it, and explain it in the pull request.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from corpus_fetch import HERE, Corpus, CorpusError, cache_dir, load_registry, verify
from oracle import scan


def expected_path(corpus_id: str) -> Path:
    return HERE / f"{corpus_id}.expected.json"


def oracle_counts(corpus: Corpus, cache: Path) -> dict[str, int]:
    root = corpus.local_dir(cache)
    return scan(root / f.path for f in corpus.files).counts


def render(corpus: Corpus, counts: dict[str, int]) -> str:
    data = {"corpus": corpus.id, "revision": corpus.revision, "counts": counts}
    return json.dumps(data, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    wanted = set(sys.argv[1:] if argv is None else argv)
    corpora = [c for c in load_registry() if not wanted or c.id in wanted]
    unknown = wanted - {c.id for c in corpora}
    if unknown:
        print(f"unknown corpus: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    cache = cache_dir()
    for corpus in corpora:
        try:
            verify(corpus, cache)
        except CorpusError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        path = expected_path(corpus.id)
        path.write_text(render(corpus, oracle_counts(corpus, cache)), encoding="utf-8")
        print(f"{corpus.id}: wrote {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
