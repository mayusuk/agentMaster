"""Unit tests for the corpus tooling, on synthetic files only (no network, no real data)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from corpus_fetch import (
    Corpus,
    CorpusError,
    CorpusFile,
    cache_dir,
    fetch,
    load_registry,
    measure,
    primary_checkout,
    render_registry,
    safe_relative,
    verify,
)
from corpus_gate import ensure_available, required
from count_assert import assert_counts, count_mismatches

SECRET = "planted-content-that-must-never-be-printed"  # noqa: S105 (marker text, not a credential)


def make_corpus(tmp_path: Path, files: dict[str, bytes]) -> tuple[Corpus, str]:
    """A corpus served from a file:// 'remote' laid out like Hugging Face resolve URLs."""
    remote = tmp_path / "remote"
    revision = "a" * 40
    entries = []
    for path, data in files.items():
        dest = remote / "datasets" / "org" / "set" / "resolve" / revision / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        sha, size, lines = measure(dest)
        entries.append(CorpusFile(path, sha, size, lines))
    corpus = Corpus("syn", "org/set", revision, "MIT", "test", tuple(entries))
    return corpus, remote.as_uri()


def test_measure_counts_lines_and_a_final_unterminated_line(tmp_path: Path) -> None:
    p = tmp_path / "f.jsonl"
    p.write_bytes(b"{}\n{}\n{}")
    _sha, size, lines = measure(p)
    assert (size, lines) == (8, 3)
    p.write_bytes(b"")
    assert measure(p)[1:] == (0, 0)


def test_fetch_downloads_verifies_and_caches(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"a.jsonl": b"{}\n", "sub/b.jsonl": b"{}\n{}\n"})
    cache = tmp_path / "cache"
    assert fetch(corpus, cache, base) == 9
    verify(corpus, cache)
    assert fetch(corpus, cache, base) == 0  # cached and still valid


def test_hash_mismatch_fails_naming_the_file_but_no_content(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"sessions/x.jsonl": f'{{"t": "{SECRET}"}}\n'.encode()})
    cache = tmp_path / "cache"
    fetch(corpus, cache, base)
    local = corpus.local_dir(cache) / "sessions/x.jsonl"
    local.write_bytes(f'{{"t": "{SECRET}!"}}\n'.encode())
    with pytest.raises(CorpusError) as exc:
        verify(corpus, cache)
    message = str(exc.value)
    assert "syn:sessions/x.jsonl" in message
    assert SECRET not in message


def test_remote_content_that_does_not_match_is_rejected(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"x.jsonl": b"{}\n"})
    remote_file = (
        Path(base.removeprefix("file://"))
        / "datasets/org/set/resolve"
        / corpus.revision
        / "x.jsonl"
    )
    remote_file.write_bytes(f"{SECRET}\n".encode())
    with pytest.raises(CorpusError, match="does not match the registry") as exc:
        fetch(corpus, tmp_path / "cache", base)
    assert SECRET not in str(exc.value)


def test_a_mismatching_cached_file_is_downloaded_again(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"x.jsonl": b"{}\n"})
    cache = tmp_path / "cache"
    fetch(corpus, cache, base)
    (corpus.local_dir(cache) / "x.jsonl").write_bytes(b"corrupted\n")
    assert fetch(corpus, cache, base) == 3
    verify(corpus, cache)


def test_missing_remote_file_is_a_corpus_error(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"x.jsonl": b"{}\n"})
    with pytest.raises(CorpusError, match="could not be downloaded"):
        fetch(corpus, tmp_path / "cache", base + "/elsewhere")


def test_require_flag_fails_rather_than_skips_when_data_is_missing(tmp_path: Path) -> None:
    corpus, _base = make_corpus(tmp_path, {"x.jsonl": b"{}\n"})
    cache = tmp_path / "empty-cache"
    with pytest.raises(pytest.fail.Exception, match="failure, not a skip"):
        ensure_available(corpus, cache, {"EAGAIN_REQUIRE_CORPORA": "1"})
    with pytest.raises(pytest.skip.Exception, match=r"corpus_fetch\.py fetch"):
        ensure_available(corpus, cache, {})
    assert required({"EAGAIN_REQUIRE_CORPORA": "1"})
    assert not required({"EAGAIN_REQUIRE_CORPORA": "0"})
    assert not required({})


def test_available_corpus_returns_its_directory(tmp_path: Path) -> None:
    corpus, base = make_corpus(tmp_path, {"x.jsonl": b"{}\n"})
    cache = tmp_path / "cache"
    fetch(corpus, cache, base)
    assert ensure_available(corpus, cache, {"EAGAIN_REQUIRE_CORPORA": "1"}) == corpus.local_dir(
        cache
    )


def test_count_failures_show_only_ids_and_counts() -> None:
    expected = {"tool_result": 10, "error": 2}
    actual = {"tool_result": 9, "error": 2, "interrupt": 1}
    assert count_mismatches(expected, actual) == [
        "interrupt: expected 0, got 1",
        "tool_result: expected 10, got 9",
    ]
    with pytest.raises(pytest.fail.Exception) as exc:
        assert_counts(expected, actual, "syn records")
    assert str(exc.value) == (
        "syn records: 2 count(s) differ\n"
        "  interrupt: expected 0, got 1\n"
        "  tool_result: expected 10, got 9"
    )
    assert_counts(expected, dict(expected), "same")


def test_count_helpers_refuse_non_count_values_without_echoing_them() -> None:
    with pytest.raises(TypeError) as exc:
        count_mismatches({"x": 1}, {"x": SECRET})  # type: ignore[dict-item]
    assert SECRET not in str(exc.value)
    with pytest.raises(TypeError):
        count_mismatches({"x": True}, {"x": 1})


def test_registry_round_trips(tmp_path: Path) -> None:
    corpus = Corpus(
        "syn", "org/set", "b" * 40, "MIT", "test", (CorpusFile('q"x.jsonl', "c" * 64, 5, 1),)
    )
    path = tmp_path / "registry.toml"
    path.write_text(render_registry([corpus]), encoding="utf-8")
    assert tomllib.loads(path.read_text())["version"] == 1
    assert load_registry(path) == [corpus]


def test_cache_dir_is_shared_with_the_primary_checkout(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
    wt = main / ".worktrees" / "wt"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    assert primary_checkout(wt) == main.resolve()
    assert primary_checkout(main) == main
    assert cache_dir({"EAGAIN_CORPORA_DIR": str(tmp_path / "c")}) == tmp_path / "c"


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "../x.jsonl", "a/../../x", "a\\b.jsonl", "", "a//b"]
)
def test_registry_paths_cannot_escape_the_cache(bad: str) -> None:
    with pytest.raises(CorpusError, match="unsafe path"):
        safe_relative(bad)
    assert safe_relative("sub/dir/x.jsonl") == "sub/dir/x.jsonl"
