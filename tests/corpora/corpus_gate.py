"""Decide whether the corpus tier runs, skips or fails (plan section 5, "Handling real data").

Locally, a corpus that has not been downloaded skips with the command to fetch it.
With ``EAGAIN_REQUIRE_CORPORA=1`` (CI and ``wf verify``) it fails instead, so the
gate can never be passed by skipping.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from corpus_fetch import Corpus, CorpusError, verify

REQUIRE_ENV = "EAGAIN_REQUIRE_CORPORA"
FETCH_HINT = "run `uv run python tests/corpora/corpus_fetch.py fetch`"


def required(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get(REQUIRE_ENV, "") not in ("", "0")


def ensure_available(corpus: Corpus, cache: Path, env: Mapping[str, str] | None = None) -> Path:
    """The verified local directory for ``corpus``, or skip/fail without showing any content."""
    try:
        verify(corpus, cache)
    except CorpusError as exc:
        message = f"corpus {corpus.id} unavailable: {exc}"
        if required(env):
            pytest.fail(
                f"{message} ({REQUIRE_ENV}=1, so this is a failure, not a skip)", pytrace=False
            )
        pytest.skip(f"{message}; {FETCH_HINT}")
    return corpus.local_dir(cache)
