"""Corpus tier: the pinned public corpora are present, intact and as registered (plan section 5).

Assertions compare counts only. Nothing from a corpus file is ever printed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from corpus_fetch import DATA_SUFFIX, Corpus, cache_dir, load_registry, measure
from corpus_gate import ensure_available
from count_assert import assert_counts

pytestmark = pytest.mark.corpus

CORPORA = load_registry()


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.id)
def test_corpus_files_match_the_registry(corpus: Corpus) -> None:
    root = ensure_available(corpus, cache_dir())  # verifies every SHA-256 and size
    on_disk = sorted(p.relative_to(root).as_posix() for p in root.rglob(f"*{DATA_SUFFIX}"))
    assert_counts(
        {"files": len(corpus.files)}, {"files": len(on_disk)}, f"{corpus.id} data files on disk"
    )
    expected = {f.path: f.lines for f in corpus.files}
    actual = {f.path: measure(Path(root) / f.path)[2] for f in corpus.files}
    assert_counts(expected, actual, f"{corpus.id} lines per file")
