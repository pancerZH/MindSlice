"""Evaluation data: corpus slices, overlay cards, queries with graded judgments, and their digests."""

from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from mindslice import Workspace

DATA = Path(__file__).parent / "data"
QUERIES_FILE = DATA / "queries.toml"
DIGESTS_FILE = DATA / "DIGESTS.json"
SPLITS = ("dev", "holdout", "limits", "holdout-2")
LANGS = ("en", "zh")
# (directory under data/, alias, precedence, role). The overlay is @overlay (precedence 100, runtime).
MOUNTS = (("kb-en.slice", "@kb-en", 50, "curated"), ("kb-zh.slice", "@kb-zh", 40, "curated"))
# Corpora a query can run against: "full" mounts both handbooks over a runtime overlay; the tiny
# corpora are a lone overlay of 10 cards (an agent's first week of memories on one project).
CORPORA: dict[str, tuple[str, ...]] = {
    "full": ("kb-en.slice", "kb-zh.slice", "overlay"),
    "tiny-en": ("tiny-en",),
    "tiny-zh": ("tiny-zh",),
}


@dataclass(frozen=True)
class Query:
    id: str
    split: str
    lang: str
    category: str
    text: str
    relevant: dict[str, int]
    corpus: str = "full"


def load_queries(path: Path = QUERIES_FILE) -> list[Query]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Query(q["id"], q["split"], q["lang"], q["category"], q["text"], dict(q["relevant"]), q.get("corpus", "full"))
            for q in data["queries"]]


def build_workspace(root: Path, corpus: str = "full") -> Workspace:
    """A fresh workspace for ``corpus``: the two handbooks plus overlay, or a tiny overlay-only memory."""
    if corpus not in CORPORA:
        raise ValueError(f"unknown corpus {corpus!r}")
    ws = Workspace.init(root)
    if corpus == "full":
        for dirname, alias, precedence, role in MOUNTS:
            target = root / "slices" / dirname
            shutil.copytree(DATA / dirname, target)
            ws.mount(target, alias=alias, precedence=precedence, role=role)
    shutil.copytree(DATA / CORPORA[corpus][-1], ws.table().overlay.root, dirs_exist_ok=True)
    ws.manifest(limit=1)  # any public call syncs the index with the files just copied in
    return ws


# ---------------------------------------------------------------------------
# Digests: any change to the data is visible, split by split
# ---------------------------------------------------------------------------


def _sha(chunks) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def corpus_digest(corpus: str = "full") -> str:
    files = sorted(p for d in CORPORA[corpus] for p in (DATA / d).rglob("*") if p.is_file())
    return _sha(p.relative_to(DATA).as_posix().encode() + b"\0" + p.read_bytes() + b"\0" for p in files)


def _record(q: Query) -> dict:
    record = asdict(q)
    if record["corpus"] == "full":  # queries frozen before corpora existed keep their original digest
        del record["corpus"]
    return record


def split_digest(queries: list[Query], split: str) -> str:
    records = [_record(q) for q in queries if q.split == split]
    return _sha([json.dumps(records, ensure_ascii=False, sort_keys=True).encode()])


def digests(queries: list[Query]) -> dict[str, str]:
    out = {"corpus": corpus_digest("full")}
    out.update({f"corpus-{c}": corpus_digest(c) for c in CORPORA if c != "full"})
    out.update({split: split_digest(queries, split) for split in SPLITS})
    return out


def frozen_digests() -> dict[str, str]:
    return json.loads(DIGESTS_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Integrity: checked before any system is scored
# ---------------------------------------------------------------------------


def problems(queries: list[Query], ws: Workspace) -> list[str]:
    """Structural problems in the judgments (never looks at any system's ranking)."""
    out: list[str] = []
    ids = [q.id for q in queries]
    out += [f"duplicate query id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for q in queries:
        if q.split not in SPLITS or q.lang not in LANGS:
            out.append(f"{q.id}: unknown split {q.split!r} or lang {q.lang!r}")
        if not q.text.strip():
            out.append(f"{q.id}: empty query")
        if 2 not in q.relevant.values():
            out.append(f"{q.id}: no card judged 2 (answers the query)")
        for address, grade in q.relevant.items():
            if grade not in (1, 2):
                out.append(f"{q.id}: grade {grade} for {address} (use 1 or 2)")
            mount, _, path = address.partition("/")
            row = ws.index.card(mount, path)
            if row is None:
                out.append(f"{q.id}: judged card {address} does not exist")
            elif row["is_overview"]:
                out.append(f"{q.id}: judged card {address} is an overview (never returned by search)")
            elif ws.read(address)["address"] != address:
                out.append(f"{q.id}: judged card {address} is superseded; judge its replacement")
    return out
