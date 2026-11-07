"""The external datasets: pinned revisions, SHA-256 digests, licenses, and a verifying downloader.

Nothing here is committed to the repository: the files are fetched into a data directory outside it
(``$MINDSLICE_EVAL_DATA``, default ``~/.cache/mindslice/evals``), one new directory per dataset, and
checked against the digests below before anything reads them. They are only ever parsed as JSON or
Parquet, never imported or executed.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DATA_ENV = "MINDSLICE_EVAL_DATA"
USER_AGENT = "mindslice-evals/0.1"


@dataclass(frozen=True)
class Source:
    key: str
    directory: str
    file: str
    url: str
    sha256: str
    size: int
    license: str
    homepage: str
    rows_sha256: str | None = None  # Parquet only: digest of the decoded rows (computed once with pyarrow)


SOURCES: dict[str, Source] = {
    s.key: s
    for s in (
        Source(
            "locomo", "locomo", "locomo10.json",
            "https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json",
            "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4", 2_805_274,
            "CC BY-NC 4.0", "https://github.com/snap-research/locomo",
        ),
        Source(
            "longmemeval-s", "longmemeval", "longmemeval_s_cleaned.json",
            "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_s_cleaned.json",
            "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442", 277_383_467,
            "MIT", "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned",
        ),
        Source(
            "meme-filler32k", "meme", "meme_filler32k.json",
            "https://huggingface.co/datasets/meme-benchmark/MEME/resolve/e14c4e685772014deb96f91dc7eddfbeb21d90d8/meme_filler32k.json",
            "a88d28374a002b3e5b1683fb7201d06a1ce739d2ebf94c971c37bb65cf6ebdd3", 20_177_963,
            "CC BY 4.0", "https://huggingface.co/datasets/meme-benchmark/MEME",
        ),
        Source(
            "meme-nofiller", "meme", "meme_nofiller.json",
            "https://huggingface.co/datasets/meme-benchmark/MEME/resolve/e14c4e685772014deb96f91dc7eddfbeb21d90d8/meme_nofiller.json",
            "1687d028cc1638986df9f58f0c3f072f614cf13d72a791541b4439fddf701636", 4_600_403,
            "CC BY 4.0", "https://huggingface.co/datasets/meme-benchmark/MEME",
        ),
        Source(
            "mab-cr", "memoryagentbench", "Conflict_Resolution-00000-of-00001.parquet",
            "https://huggingface.co/datasets/ai-hyz/MemoryAgentBench/resolve/7ea066982b140a19337e17e60d45d4076e042faf/data/Conflict_Resolution-00000-of-00001.parquet",
            "24d5c3f09ce0ce15625cb9f8a98f44f0d864ca6c94d7b4ad04eb697ca3a5ff45", 1_491_588,
            "MIT", "https://huggingface.co/datasets/ai-hyz/MemoryAgentBench",
            rows_sha256="fe79015f38ea8c298c457532889402583c9f239f425db5326d6916e7a9f24446",
        ),
    )
}
# Columns whose decoded rows ``rows_sha256`` covers (in this order, as JSON with sorted keys).
MAB_COLUMNS = ("context", "questions", "answers", "metadata.source", "metadata.qa_pair_ids")


def data_dir(override: str | os.PathLike[str] | None = None) -> Path:
    root = override or os.environ.get(DATA_ENV) or Path.home() / ".cache" / "mindslice" / "evals"
    return Path(root).expanduser()


def path_of(key: str, root: Path | None = None) -> Path:
    s = SOURCES[key]
    return (root or data_dir()) / s.directory / s.file


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rows_digest(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def problems(root: Path | None = None, keys: tuple[str, ...] | None = None) -> list[str]:
    """Missing or altered files (and, for Parquet, rows this reader decodes differently from pyarrow)."""
    out = []
    for key in keys or tuple(SOURCES):
        s, p = SOURCES[key], path_of(key, root)
        if not p.is_file():
            out.append(f"{key}: missing {p} (run `python -m evals.external fetch`)")
            continue
        digest = sha256_file(p)
        if digest != s.sha256:
            out.append(f"{key}: {p} has sha256 {digest[:12]}…, expected {s.sha256[:12]}…")
            continue
        if s.rows_sha256:
            from .parquet import ParquetFile

            got = rows_digest(ParquetFile(p).rows(list(MAB_COLUMNS)))
            if got != s.rows_sha256:
                out.append(f"{key}: decoded rows digest {got[:12]}…, expected {s.rows_sha256[:12]}… (Parquet reader bug?)")
    return out


def fetch(root: Path | None = None, keys: tuple[str, ...] | None = None, log=print) -> list[str]:
    """Download missing files into their own directories, verifying each digest before keeping it."""
    root = root or data_dir()
    failures = []
    for key in keys or tuple(SOURCES):
        s, target = SOURCES[key], path_of(key, root)
        if target.is_file() and sha256_file(target) == s.sha256:
            log(f"{key}: present ({target})")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        log(f"{key}: downloading {s.size / 1e6:.1f} MB from {s.url}")
        request = urllib.request.Request(s.url, headers={"User-Agent": USER_AGENT})
        h = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
            for chunk in iter(lambda: response.read(1 << 20), b""):
                h.update(chunk)
                out.write(chunk)
        if h.hexdigest() != s.sha256:
            partial.unlink()
            failures.append(f"{key}: downloaded file has sha256 {h.hexdigest()[:12]}…, expected {s.sha256[:12]}…; discarded")
            continue
        os.replace(partial, target)
        log(f"{key}: ok")
    return failures
