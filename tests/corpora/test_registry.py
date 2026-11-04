"""The committed registry pins exactly the corpora in plan section 5 (unit tier; needs no data)."""

from __future__ import annotations

import re

from corpus_fetch import load_registry

# Plan section 5, "Corpora": dataset, short revision, license, data file count.
PLAN = {
    "armand0e": ("armand0e/claude-fable-5-claude-code", "7388ef9", "MIT", 63),
    "alinciocan": ("AlinCiocan/fable-5-claude-code-traces", "e33ebbc", "CC-BY-4.0", 18),
    "crispwisp": ("crispwisp/wisp-claude-code-sessions", "c2c90b5", "MIT", 104),
    # The plan first said 984; that count stopped at the tree API's first page.
    "choucsan": ("choucsan/mimo-claude-code-traces-1k", "39cc3fc", "MIT", 1017),
}


def test_registry_matches_the_plan() -> None:
    corpora = {c.id: c for c in load_registry()}
    assert set(corpora) == set(PLAN)
    for cid, (dataset, short_rev, license_, n_files) in PLAN.items():
        c = corpora[cid]
        assert (c.dataset, c.license, len(c.files)) == (dataset, license_, n_files), cid
        assert re.fullmatch(r"[0-9a-f]{40}", c.revision), cid
        assert c.revision.startswith(short_rev), cid


def test_every_file_has_a_full_hash_and_counts() -> None:
    for c in load_registry():
        paths = [f.path for f in c.files]
        assert len(paths) == len(set(paths)), c.id
        assert paths == sorted(paths), c.id
        for f in c.files:
            assert re.fullmatch(r"[0-9a-f]{64}", f.sha256), (c.id, f.path)
            assert f.size > 0, (c.id, f.path)
            assert f.lines > 0, (c.id, f.path)
