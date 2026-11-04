"""Download and verify the pinned public corpora (plan section 5).

Standard library only. Corpus files are untrusted data: they are hashed and
counted here, never parsed or executed, and their content is never printed.

    python tests/corpora/corpus_fetch.py fetch                 # download and verify every corpus
    python tests/corpora/corpus_fetch.py pin <dataset> <revision> --id ID --license L --role R

The cache is ``.corpora/`` in the primary checkout (shared by all worktrees),
or ``$EAGAIN_CORPORA_DIR``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.toml"
BASE_URL = "https://huggingface.co"
DATA_SUFFIX = ".jsonl"
CHUNK = 1 << 20


class CorpusError(Exception):
    """A corpus file is missing or does not match the registry. Never carries content."""


@dataclass(frozen=True)
class CorpusFile:
    path: str
    sha256: str
    size: int
    lines: int


@dataclass(frozen=True)
class Corpus:
    id: str
    dataset: str
    revision: str
    license: str
    role: str
    files: tuple[CorpusFile, ...]

    def local_dir(self, cache: Path) -> Path:
        return cache / self.id / self.revision

    def url(self, path: str, base_url: str = BASE_URL) -> str:
        quoted = urllib.parse.quote(path)
        return f"{base_url}/datasets/{self.dataset}/resolve/{self.revision}/{quoted}"


def safe_relative(path: str) -> str:
    """Registry paths must stay inside the cache: relative, no ``..``, no backslashes."""
    parts = path.split("/")
    if not path or path.startswith("/") or "\\" in path or any(p in ("", ".", "..") for p in parts):
        raise CorpusError(f"unsafe path in registry: {path!r}")
    return path


def load_registry(path: Path = REGISTRY) -> list[Corpus]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    corpora = []
    for c in data.get("corpus", []):
        files = tuple(
            CorpusFile(safe_relative(f["path"]), f["sha256"], f["size"], f["lines"])
            for f in c["files"]
        )
        corpora.append(Corpus(c["id"], c["dataset"], c["revision"], c["license"], c["role"], files))
    return corpora


def repo_root(start: Path = HERE) -> Path:
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    raise CorpusError(f"no git repository above {start}")


def primary_checkout(root: Path) -> Path:
    """The main checkout for a worktree, read from ``.git`` and ``commondir`` (no git run)."""
    git = root / ".git"
    if git.is_dir():
        return root
    m = re.match(r"gitdir:\s*(.+)", git.read_text(encoding="utf-8").strip())
    if not m:
        return root
    gitdir = (root / m.group(1)).resolve()
    commondir = gitdir / "commondir"
    if not commondir.is_file():
        return root
    common = (gitdir / commondir.read_text(encoding="utf-8").strip()).resolve()
    return common.parent


def cache_dir(env: dict[str, str] | None = None) -> Path:
    env = dict(os.environ) if env is None else env
    if env.get("EAGAIN_CORPORA_DIR"):
        return Path(env["EAGAIN_CORPORA_DIR"]).expanduser()
    return primary_checkout(repo_root()) / ".corpora"


def measure(path: Path) -> tuple[str, int, int]:
    """SHA-256, size in bytes and line count. A final line without a newline still counts."""
    digest = hashlib.sha256()
    size = lines = 0
    last = b"\n"
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
            lines += chunk.count(b"\n")
            last = chunk[-1:]
    if size and last != b"\n":
        lines += 1
    return digest.hexdigest(), size, lines


def verify_file(corpus: Corpus, f: CorpusFile, cache: Path) -> None:
    local = corpus.local_dir(cache) / f.path
    where = f"{corpus.id}:{f.path}"
    if not local.is_file():
        raise CorpusError(f"{where} is missing; run `python tests/corpora/corpus_fetch.py fetch`")
    sha, size, _lines = measure(local)
    if sha != f.sha256 or size != f.size:
        raise CorpusError(f"{where} does not match the registry (sha256 or size differs)")


def verify(corpus: Corpus, cache: Path) -> None:
    for f in corpus.files:
        verify_file(corpus, f, cache)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".part-")
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            while chunk := resp.read(CHUNK):
                out.write(chunk)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def fetch(corpus: Corpus, cache: Path, base_url: str = BASE_URL) -> int:
    """Download missing or mismatching files and verify them. Returns bytes downloaded."""
    fetched = 0
    for f in corpus.files:
        local = corpus.local_dir(cache) / f.path
        if local.is_file():
            try:
                verify_file(corpus, f, cache)
                continue
            except CorpusError:
                local.unlink()
        try:
            _download(corpus.url(f.path, base_url), local)
        except OSError as exc:
            raise CorpusError(f"{corpus.id}:{f.path} could not be downloaded: {exc}") from None
        verify_file(corpus, f, cache)
        fetched += f.size
    return fetched


# --- Pinning ----------------------------------------------------------------


def list_data_files(dataset: str, revision: str, base_url: str = BASE_URL) -> Iterator[str]:
    """Data file paths at a revision, from the Hugging Face tree API (paginated by Link header)."""
    url: str | None = f"{base_url}/api/datasets/{dataset}/tree/{revision}?recursive=true"
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            items: list[dict[str, Any]] = json.load(resp)
            link = resp.headers.get("Link", "")
        for item in items:
            if item.get("type") == "file" and item["path"].endswith(DATA_SUFFIX):
                yield item["path"]
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None


def resolve_revision(dataset: str, revision: str, base_url: str = BASE_URL) -> str:
    url = f"{base_url}/api/datasets/{dataset}/revision/{revision}"
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        sha = json.load(resp)["sha"]
    return str(sha)


def pin(
    dataset: str,
    revision: str,
    *,
    id_: str,
    license_: str,
    role: str,
    cache: Path,
    base_url: str = BASE_URL,
) -> Corpus:
    full = resolve_revision(dataset, revision, base_url)
    paths = sorted(list_data_files(dataset, full, base_url))
    probe = Corpus(id_, dataset, full, license_, role, ())
    files = []
    for p in paths:
        local = probe.local_dir(cache) / p
        if not local.is_file():
            _download(probe.url(p, base_url), local)
        sha, size, lines = measure(local)
        files.append(CorpusFile(p, sha, size, lines))
    return Corpus(id_, dataset, full, license_, role, tuple(files))


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_registry(corpora: Sequence[Corpus]) -> str:
    out = [
        "# Pinned public corpora for the corpus test tier (plan section 5).",
        "# Generated by `python tests/corpora/corpus_fetch.py pin`; do not edit by hand.",
        "# Holds revisions, hashes and counts only. Corpus content is never committed.",
        "",
        "version = 1",
    ]
    for c in corpora:
        out += [
            "",
            "[[corpus]]",
            f"id = {_toml_str(c.id)}",
            f"dataset = {_toml_str(c.dataset)}",
            f"revision = {_toml_str(c.revision)}",
            f"license = {_toml_str(c.license)}",
            f"role = {_toml_str(c.role)}",
            "files = [",
        ]
        out += [
            f"  {{ path = {_toml_str(f.path)}, sha256 = {_toml_str(f.sha256)}, "
            f"size = {f.size}, lines = {f.lines} }},"
            for f in c.files
        ]
        out.append("]")
    return "\n".join(out) + "\n"


def _upsert(corpora: list[Corpus], new: Corpus) -> list[Corpus]:
    kept = [c for c in corpora if c.id != new.id]
    return (
        [*kept, new]
        if len(kept) == len(corpora)
        else [new if c.id == new.id else c for c in corpora]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download and verify every corpus in the registry")
    f.add_argument("--only", action="append", help="corpus id (repeatable)")
    p = sub.add_parser("pin", help="add or refresh one corpus in the registry")
    p.add_argument("dataset")
    p.add_argument("revision")
    p.add_argument("--id", required=True)
    p.add_argument("--license", required=True)
    p.add_argument("--role", required=True)
    args = parser.parse_args(argv)
    cache = cache_dir()
    try:
        if args.cmd == "fetch":
            total = 0
            start = time.monotonic()
            for corpus in load_registry():
                if args.only and corpus.id not in args.only:
                    continue
                got = fetch(corpus, cache)
                total += got
                print(
                    f"{corpus.id}: {len(corpus.files)} files verified, "
                    f"{got / 1e6:.1f} MB downloaded"
                )
            print(
                f"done: {total / 1e6:.1f} MB downloaded "
                f"in {time.monotonic() - start:.0f}s into {cache}"
            )
        else:
            corpus = pin(
                args.dataset,
                args.revision,
                id_=args.id,
                license_=args.license,
                role=args.role,
                cache=cache,
            )
            existing = load_registry() if REGISTRY.exists() else []
            REGISTRY.write_text(render_registry(_upsert(existing, corpus)), encoding="utf-8")
            size = sum(x.size for x in corpus.files)
            print(
                f"{corpus.id}: pinned {len(corpus.files)} files, "
                f"{size / 1e6:.1f} MB at {corpus.revision}"
            )
    except CorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
