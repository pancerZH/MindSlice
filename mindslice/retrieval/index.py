"""Disposable SQLite acceleration cache (``.cache/index.sqlite``).

Everything except telemetry is reconstructible from the Markdown on disk:

* ``cards``       one row per card file (stat, sha256, parsed metadata, preview)
* ``cards_fts``   FTS5 table over ``title, aliases, tags, summary, body``
* ``links``       raw lineage / wikilink references plus their current resolution
* ``mounts``      snapshot of the mount table the index was built against
* ``telemetry``   best-effort ``read_count`` / ``last_read_at`` (survives rebuilds,
                  but is lost if the cache file is deleted)
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..model.addressing import MountCatalog, resolve_ref
from ..model.card import PARSER_VERSION, parse_card, preview_text, sha256_bytes
from ..storage.config import OVERVIEW_PATH, Mount, MountTable
from ..storage.fsutil import iter_markdown
from .lexical import QueryPlan, analyze_query, analyzer_signature, fold, index_text

SCHEMA_VERSION = "2"  # table layout ("2": cards.load); text-analysis and parsing changes are tracked by index_signature()
BM25_WEIGHTS = (10.0, 5.0, 3.0, 2.0, 1.0)  # title, aliases, tags, summary, body
TOKENIZER = "porter unicode61 remove_diacritics 2"
LINK_KINDS = ("extends", "supersedes", "wikilink")

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mounts(
    alias TEXT PRIMARY KEY, root TEXT NOT NULL, precedence INTEGER NOT NULL,
    role TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards(
    id INTEGER PRIMARY KEY,
    mount TEXT NOT NULL, path TEXT NOT NULL,
    title TEXT NOT NULL, aliases TEXT NOT NULL, tags TEXT NOT NULL,
    extends TEXT NOT NULL, supersedes TEXT NOT NULL,
    summary TEXT NOT NULL, preview TEXT NOT NULL,
    sha256 TEXT NOT NULL, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL,
    lines INTEGER NOT NULL, is_overview INTEGER NOT NULL, has_frontmatter INTEGER NOT NULL,
    load TEXT NOT NULL DEFAULT 'as-needed',
    errors TEXT NOT NULL, warnings TEXT NOT NULL,
    UNIQUE(mount, path)
);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    title, aliases, tags, summary, body, tokenize = '{TOKENIZER}'
);
CREATE TABLE IF NOT EXISTS card_aliases(mount TEXT NOT NULL, path TEXT NOT NULL, alias TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS card_aliases_idx ON card_aliases(mount, alias);
CREATE TABLE IF NOT EXISTS card_tags(mount TEXT NOT NULL, path TEXT NOT NULL, tag TEXT NOT NULL);
DROP TABLE IF EXISTS card_words;  -- left by analyzer "2" caches (did_you_mean, since removed)
CREATE INDEX IF NOT EXISTS card_tags_idx ON card_tags(mount, path);
CREATE TABLE IF NOT EXISTS links(
    id INTEGER PRIMARY KEY,
    src_mount TEXT NOT NULL, src_path TEXT NOT NULL, kind TEXT NOT NULL, ord INTEGER NOT NULL,
    raw TEXT NOT NULL, dst_mount TEXT, dst_path TEXT, resolved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS links_src_idx ON links(src_mount, src_path);
CREATE INDEX IF NOT EXISTS links_dst_idx ON links(kind, dst_mount, dst_path);
CREATE TABLE IF NOT EXISTS telemetry(
    mount TEXT NOT NULL, path TEXT NOT NULL, read_count INTEGER NOT NULL DEFAULT 0,
    last_read_at REAL, PRIMARY KEY(mount, path)
);
"""

_DERIVED_TABLES = ("cards", "cards_fts", "card_aliases", "card_tags", "links", "mounts")


@dataclass
class SyncStats:
    added: int = 0
    updated: int = 0
    removed: int = 0
    touched: int = 0  # stat changed but content identical
    mounts_changed: bool = False
    changed_cards: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.mounts_changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "touched": self.touched,
            "mounts_changed": self.mounts_changed,
        }


@dataclass
class DiskState:
    files: dict[tuple[str, str], tuple[int, int, Path]]  # (mount, path) -> (mtime_ns, size, abs path)


@dataclass
class Hit:
    """One search match: the card row plus its ranking signals."""

    row: sqlite3.Row
    score: float  # -bm25(...) > 0 (0.0 for filter-only listings)
    coverage: float  # IDF-weighted share of the query matched, in [0, 1] (reported, not used to order)
    phrases: int  # unspaced query runs (3+ units) matched verbatim (reported, not used to order)

    def rank_key(self) -> tuple:
        """BM25 score, then mount precedence, then address (deterministic)."""
        r = self.row
        return (-self.score, -r["precedence"], r["mount"], r["path"])


FRONTMATTER_CODES = {None: 0, "toml": 1, "yaml": 2}  # cards.has_frontmatter


def index_signature() -> str:
    """What derived index content depends on besides the files: text analysis and card parsing.

    A different value re-indexes every card (telemetry is kept).
    """
    return f"{analyzer_signature()}|parser-{PARSER_VERSION}"


def mount_signature(table: MountTable) -> str:
    return json.dumps(
        [[m.alias, str(m.root), m.precedence, m.role, m.kind] for m in table.all()], sort_keys=True
    )


class Index:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = self._connect()

    # ------------------------------------------------------------------
    # connection / schema
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = None
        try:
            conn = self._open()
            version = self._schema_version(conn)
            if version not in (None, SCHEMA_VERSION):
                conn.close()
                self._delete_db()
                conn = self._open()
        except sqlite3.DatabaseError:
            if conn is not None:
                conn.close()
            self._delete_db()
            conn = self._open()
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
        conn.commit()
        return conn

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("SELECT 1").fetchone()  # surfaces 'file is not a database'
        except BaseException:
            # Windows cannot unlink a corrupt database while this handle is open.
            conn.close()
            raise
        return conn

    @staticmethod
    def _schema_version(conn: sqlite3.Connection) -> str | None:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        if row is None:
            return None
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return row[0] if row else None

    def _delete_db(self) -> None:
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.unlink(str(self.db_path) + suffix)
            except FileNotFoundError:
                pass

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def _meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))

    # ------------------------------------------------------------------
    # disk scanning & freshness
    # ------------------------------------------------------------------
    @staticmethod
    def scan(table: MountTable, exclude: Sequence[Path] = ()) -> DiskState:
        files: dict[tuple[str, str], tuple[int, int, Path]] = {}
        mounts = table.all()
        for m in mounts:
            nested = tuple(o.root for o in mounts if o.alias != m.alias and m.root in o.root.parents)
            for rel, st in iter_markdown(m.root, exclude=tuple(exclude) + nested):
                files[(m.alias, rel)] = (st.st_mtime_ns, st.st_size, m.root / (rel + ".md"))
        return DiskState(files)

    def indexed_stats(self) -> dict[tuple[str, str], tuple[int, int, str]]:
        rows = self.conn.execute("SELECT mount, path, mtime_ns, size, sha256 FROM cards")
        return {(r[0], r[1]): (r[2], r[3], r[4]) for r in rows}

    def is_stale(self, table: MountTable, exclude: Sequence[Path] = ()) -> bool:
        if self._meta("analyzer") != index_signature():
            return True
        if self._meta("mounts_signature") != mount_signature(table):
            return True
        disk = self.scan(table, exclude).files
        indexed = self.indexed_stats()
        if disk.keys() != indexed.keys():
            return True
        return any(indexed[k][:2] != (v[0], v[1]) for k, v in disk.items())

    # ------------------------------------------------------------------
    # sync
    # ------------------------------------------------------------------
    def sync(self, table: MountTable, exclude: Sequence[Path] = (), verify: bool = False) -> SyncStats:
        """Incrementally bring the index in line with disk in one transaction.

        With ``verify=True`` every file is re-hashed (catching edits that preserved
        both mtime and size).
        """
        stats = SyncStats()
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            analyzer = index_signature()
            if self._meta("analyzer") != analyzer:
                # Text analysis or card parsing changed (MindSlice upgrade or a new Unicode
                # database): every card must be re-analyzed. Telemetry is kept.
                self._reset_derived()
                self._set_meta("analyzer", analyzer)
            signature = mount_signature(table)
            if self._meta("mounts_signature") != signature:
                stats.mounts_changed = True
                current = {m.alias: m for m in table.all()}
                for row in conn.execute("SELECT alias, root FROM mounts").fetchall():
                    m = current.get(row["alias"])
                    if m is None or str(m.root) != row["root"]:
                        stats.removed += self._delete_mount_rows(row["alias"])
                conn.execute("DELETE FROM mounts")
                conn.executemany(
                    "INSERT INTO mounts(alias, root, precedence, role, kind) VALUES(?, ?, ?, ?, ?)",
                    [(m.alias, str(m.root), m.precedence, m.role, m.kind) for m in table.all()],
                )
                self._set_meta("mounts_signature", signature)

            disk = self.scan(table, exclude).files
            indexed = self.indexed_stats()
            for key in indexed.keys() - disk.keys():
                self._delete_card(*key)
                stats.removed += 1
                stats.changed_cards.append(key)
            for key, (mtime_ns, size, abspath) in disk.items():
                prev = indexed.get(key)
                if prev is not None and not verify and prev[:2] == (mtime_ns, size):
                    continue
                try:
                    data = abspath.read_bytes()
                except OSError:
                    continue
                digest = sha256_bytes(data)
                if prev is not None and prev[2] == digest:
                    conn.execute(
                        "UPDATE cards SET mtime_ns=?, size=? WHERE mount=? AND path=?",
                        (mtime_ns, size, key[0], key[1]),
                    )
                    stats.touched += 1
                    continue
                self._upsert_card(key[0], key[1], data, digest, mtime_ns, size)
                stats.changed_cards.append(key)
                if prev is None:
                    stats.added += 1
                else:
                    stats.updated += 1
            if stats.changed:
                self._resolve_all_links()
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return stats

    def rebuild(self, table: MountTable, exclude: Sequence[Path] = ()) -> SyncStats:
        """Drop all reconstructible state and re-index from disk with full sha256 verification."""
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._reset_derived()
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return self.sync(table, exclude, verify=True)

    def _reset_derived(self) -> None:
        """Drop everything reconstructible from disk (telemetry and schema version survive)."""
        for name in _DERIVED_TABLES:
            self.conn.execute(f"DELETE FROM {name}")
        self.conn.execute("DELETE FROM meta WHERE key <> 'schema_version'")

    def _delete_mount_rows(self, alias: str) -> int:
        ids = [r[0] for r in self.conn.execute("SELECT id FROM cards WHERE mount=?", (alias,))]
        self.conn.executemany("DELETE FROM cards_fts WHERE rowid=?", [(i,) for i in ids])
        for tbl in ("cards", "card_aliases", "card_tags"):
            self.conn.execute(f"DELETE FROM {tbl} WHERE mount=?", (alias,))
        self.conn.execute("DELETE FROM links WHERE src_mount=?", (alias,))
        return len(ids)

    def _delete_card(self, mount: str, path: str) -> None:
        row = self.conn.execute("SELECT id FROM cards WHERE mount=? AND path=?", (mount, path)).fetchone()
        if row is not None:
            self.conn.execute("DELETE FROM cards_fts WHERE rowid=?", (row[0],))
        self.conn.execute("DELETE FROM cards WHERE mount=? AND path=?", (mount, path))
        self.conn.execute("DELETE FROM card_aliases WHERE mount=? AND path=?", (mount, path))
        self.conn.execute("DELETE FROM card_tags WHERE mount=? AND path=?", (mount, path))
        self.conn.execute("DELETE FROM links WHERE src_mount=? AND src_path=?", (mount, path))

    def _upsert_card(self, mount: str, path: str, data: bytes, digest: str, mtime_ns: int, size: int) -> None:
        self._delete_card(mount, path)
        text = data.decode("utf-8", errors="replace")
        parsed = parse_card(text)
        title = parsed.display_title(path)
        summary, body = parsed.index_parts()  # plain Markdown: the lead paragraph is the summary
        preview, _ = preview_text(summary, body, limit=10_000)
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        cur = self.conn.execute(
            """INSERT INTO cards(mount, path, title, aliases, tags, extends, supersedes, summary, preview,
                   sha256, mtime_ns, size, lines, is_overview, has_frontmatter, load, errors, warnings)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mount,
                path,
                title,
                json.dumps(parsed.aliases, ensure_ascii=False),
                json.dumps(parsed.tags, ensure_ascii=False),
                json.dumps(parsed.extends, ensure_ascii=False),
                json.dumps(parsed.supersedes, ensure_ascii=False),
                summary,
                preview,
                digest,
                mtime_ns,
                size,
                lines,
                1 if path == OVERVIEW_PATH else 0,
                FRONTMATTER_CODES.get(parsed.frontmatter_format, 0),
                parsed.load,
                json.dumps(parsed.errors, ensure_ascii=False),
                json.dumps(parsed.warnings, ensure_ascii=False),
            ),
        )
        card_id = cur.lastrowid
        alias_text = " ".join(parsed.aliases + [path.replace("/", " ")])
        fields = (title, alias_text, " ".join(parsed.tags), summary, body)
        self.conn.execute(
            "INSERT INTO cards_fts(rowid, title, aliases, tags, summary, body) VALUES(?, ?, ?, ?, ?, ?)",
            (card_id, *(index_text(t) for t in fields)),
        )
        self.conn.executemany(
            "INSERT INTO card_aliases(mount, path, alias) VALUES(?, ?, ?)",
            [(mount, path, k) for k in dict.fromkeys(fold(a) for a in parsed.aliases) if k],
        )
        self.conn.executemany(
            "INSERT INTO card_tags(mount, path, tag) VALUES(?, ?, ?)",
            [(mount, path, k) for k in dict.fromkeys(fold(t) for t in parsed.tags) if k],
        )
        refs: list[tuple[str, int, str]] = []
        for kind, values in (("extends", parsed.extends), ("supersedes", parsed.supersedes)):
            refs += [(kind, i, v) for i, v in enumerate(values)]
        refs += [("wikilink", i, v) for i, v in enumerate(parsed.wikilink_targets())]
        self.conn.executemany(
            "INSERT INTO links(src_mount, src_path, kind, ord, raw) VALUES(?, ?, ?, ?, ?)",
            [(mount, path, kind, i, raw) for kind, i, raw in refs],
        )

    def catalogs(self) -> dict[str, MountCatalog]:
        cats: dict[str, MountCatalog] = {}
        for row in self.conn.execute("SELECT alias FROM mounts"):
            cats[row[0]] = MountCatalog()
        for row in self.conn.execute("SELECT mount, path, aliases FROM cards ORDER BY mount, path"):
            cats.setdefault(row[0], MountCatalog()).add(row[1], json.loads(row[2]))
        return cats

    def _resolve_all_links(self) -> None:
        cats = self.catalogs()
        updates = []
        for row in self.conn.execute("SELECT id, src_mount, raw FROM links").fetchall():
            res = resolve_ref(row["raw"], row["src_mount"], cats)
            updates.append((res.mount, res.path, 1 if res.resolved else 0, row["id"]))
        self.conn.executemany("UPDATE links SET dst_mount=?, dst_path=?, resolved=? WHERE id=?", updates)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def mount_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM mounts ORDER BY precedence DESC, alias").fetchall()

    def card(self, mount: str, path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT c.*, m.precedence, m.role FROM cards c JOIN mounts m ON m.alias = c.mount
               WHERE c.mount=? AND c.path=?""",
            (mount, path),
        ).fetchone()

    def cards_at_path(self, path: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT c.*, m.precedence, m.role FROM cards c JOIN mounts m ON m.alias = c.mount
               WHERE c.path=? ORDER BY m.precedence DESC, c.mount""",
            (path,),
        ).fetchall()

    def cards_with_alias(self, alias: str, mount: str | None = None) -> list[sqlite3.Row]:
        sql = """SELECT c.*, m.precedence, m.role FROM card_aliases a
                 JOIN cards c ON c.mount = a.mount AND c.path = a.path
                 JOIN mounts m ON m.alias = c.mount WHERE a.alias=?"""
        args: list[Any] = [fold(alias)]
        if mount is not None:
            sql += " AND a.mount=?"
            args.append(mount)
        sql += " ORDER BY m.precedence DESC, c.mount, c.path"
        return self.conn.execute(sql, args).fetchall()

    def always_cards(self) -> list[sqlite3.Row]:
        """Cards with ``load = "always"``, base layers first (precedence ascending), then mount, path."""
        return self.conn.execute(
            """SELECT c.*, m.precedence, m.role FROM cards c JOIN mounts m ON m.alias = c.mount
               WHERE c.load = 'always' ORDER BY m.precedence, c.mount, c.path"""
        ).fetchall()

    def all_cards(self, mount: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT c.*, m.precedence, m.role FROM cards c JOIN mounts m ON m.alias = c.mount"
        args: tuple[Any, ...] = ()
        if mount is not None:
            sql += " WHERE c.mount=?"
            args = (mount,)
        return self.conn.execute(sql + " ORDER BY m.precedence DESC, c.mount, c.path", args).fetchall()

    def search(
        self, query: str, sources: Iterable[str] | None = None, tags: Iterable[str] | None = None
    ) -> list[Hit]:
        """All matches (overviews excluded), best first: ``score = -bm25(...)``, then precedence.

        Each hit also carries ``coverage``: the IDF-weighted share of the query it matches (an
        unspaced run earns the weighted share of its bigrams, or full credit when matched
        verbatim). It is reported for callers and does not order results: on the retrieval
        evaluation, coverage-first ordering lost to BM25 order (evals/retrieval/PLAN.md).
        An empty query with ``tags`` lists that facet (score and coverage 0).
        """
        plan = analyze_query(query)
        where, args = self._scope(sources, tags)
        if plan.units:
            weights = ", ".join(str(w) for w in BM25_WEIGHTS)
            sql = f"""SELECT c.*, m.precedence, m.role, -bm25(cards_fts, {weights}) AS score
                      FROM cards_fts JOIN cards c ON c.id = cards_fts.rowid
                      JOIN mounts m ON m.alias = c.mount"""
            where.insert(0, "cards_fts MATCH ?")
            args.insert(0, plan.match_expression)  # its placeholder comes first, before the scope clauses
        elif (query or "").strip():
            return []  # punctuation-only query: nothing searchable
        else:
            sql = """SELECT c.*, m.precedence, m.role, 0.0 AS score FROM cards c
                     JOIN mounts m ON m.alias = c.mount"""
        sql += " WHERE " + " AND ".join(where)
        rows = self.conn.execute(sql, args).fetchall()
        hits = self._rank(plan, rows)
        hits.sort(key=Hit.rank_key)
        return hits

    @staticmethod
    def _scope(sources: Iterable[str] | None, tags: Iterable[str] | None) -> tuple[list[str], list[Any]]:
        """WHERE clauses (over ``cards c``) and their arguments: the searchable cards in scope."""
        where: list[str] = ["c.is_overview = 0"]
        args: list[Any] = []
        source_list = list(sources or [])
        if source_list:
            where.append(f"c.mount IN ({', '.join('?' * len(source_list))})")
            args += source_list
        tag_list = sorted({fold(t) for t in (tags or []) if fold(t)})
        if tag_list:
            where.append(
                f"""(SELECT COUNT(DISTINCT t.tag) FROM card_tags t WHERE t.mount = c.mount AND t.path = c.path
                    AND t.tag IN ({', '.join('?' * len(tag_list))})) = ?"""
            )
            args += tag_list + [len(tag_list)]
        return where, args

    def unmatched_terms(self, query: str, hits: Sequence[Hit]) -> list[str]:
        """Query words (an unspaced run counts as one) that no card in scope contains.

        ``hits`` must be ``search()``'s result for the same query and scope: a word is unmatched
        when none of its terms occurs in any hit. It is a plain fact about the corpus, with no
        heuristics, in every script; it changes and reorders nothing. (Spelling suggestions were
        tried and removed: evals/retrieval/PLAN.md, "Decision: no did_you_mean".)
        """
        plan = analyze_query(query)
        ids = {h.row["id"] for h in hits}
        if not ids:
            return [u.text for u in plan.units]
        if len(plan.units) == 1:
            return []
        return [u.text for u in plan.units if not any(self._matching_ids(t) & ids for t in u.terms)]

    def _matching_ids(self, expression: str) -> set[int]:
        return {r[0] for r in self.conn.execute("SELECT rowid FROM cards_fts WHERE cards_fts MATCH ?", (expression,))}

    def _rank(self, plan: QueryPlan, rows: list[sqlite3.Row]) -> list[Hit]:
        if not plan.units:
            return [Hit(r, 0.0, 0.0, 0) for r in rows]
        if len(plan.units) == 1 and len(plan.units[0].terms) == 1:
            return [Hit(r, float(r["score"]), 1.0, 0) for r in rows]  # every match matches everything
        term_ids = {t: self._matching_ids(t) for t in plan.terms}
        phrase_ids = {p: self._matching_ids(p) for p in plan.phrases}
        n_cards = self.conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        # Smoothed BM25 IDF (always positive, also in tiny corpora where FTS5 clamps its own to ~0).
        idf = {t: math.log(1 + (n_cards - len(ids) + 0.5) / (len(ids) + 0.5)) for t, ids in term_ids.items()}
        unit_weight = [sum(idf[t] for t in u.terms) / len(u.terms) for u in plan.units]
        total = sum(unit_weight)
        hits = []
        for r in rows:
            rid = r["id"]
            credit = 0.0
            phrases = 0
            for unit, weight in zip(plan.units, unit_weight):
                if unit.phrase and rid in phrase_ids[unit.phrase]:
                    credit += weight
                    phrases += 1
                    continue
                matched = sum(idf[t] for t in unit.terms if rid in term_ids[t])
                credit += weight * matched / sum(idf[t] for t in unit.terms)
            hits.append(Hit(r, float(r["score"]), credit / total if total else 0.0, phrases))
        return hits

    def card_has_tags(self, mount: str, path: str, tags: Iterable[str]) -> bool:
        wanted = {fold(t) for t in tags if fold(t)}
        if not wanted:
            return True
        have = {r[0] for r in self.conn.execute("SELECT tag FROM card_tags WHERE mount=? AND path=?", (mount, path))}
        return wanted <= have

    def inbound(self, kind: str, mount: str, path: str, recency: bool = False) -> list[sqlite3.Row]:
        """Cards whose ``kind`` reference resolves to ``(mount, path)``.

        Ordered by precedence, then address (deterministic). ``recency=True`` orders by
        precedence then newest first (the design's order for ``extensions``).
        """
        order = "m.precedence DESC, c.mtime_ns DESC," if recency else "m.precedence DESC,"
        return self.conn.execute(
            """SELECT DISTINCT l.src_mount, l.src_path, c.mtime_ns, m.precedence, m.role
               FROM links l JOIN cards c ON c.mount = l.src_mount AND c.path = l.src_path
               JOIN mounts m ON m.alias = l.src_mount
               WHERE l.kind=? AND l.dst_mount=? AND l.dst_path=? AND l.resolved=1
                 AND NOT (l.src_mount = l.dst_mount AND l.src_path = l.dst_path)
               ORDER BY """ + order + " l.src_mount, l.src_path",
            (kind, mount, path),
        ).fetchall()

    def dangling_inbound(self, kind: str, mount: str, path: str) -> list[sqlite3.Row]:
        """Cards whose ``kind`` reference names ``(mount, path)`` by path but no longer resolves (a deleted target)."""
        return self.conn.execute(
            """SELECT DISTINCT l.src_mount, l.src_path, c.mtime_ns, m.precedence, m.role
               FROM links l JOIN cards c ON c.mount = l.src_mount AND c.path = l.src_path
               JOIN mounts m ON m.alias = l.src_mount
               WHERE l.kind=? AND l.dst_mount=? AND l.dst_path=? AND l.resolved=0
               ORDER BY m.precedence DESC, l.src_mount, l.src_path""",
            (kind, mount, path),
        ).fetchall()

    def outbound(self, mount: str, path: str, kind: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT kind, ord, raw, dst_mount, dst_path, resolved FROM links WHERE src_mount=? AND src_path=?"
        args: list[Any] = [mount, path]
        if kind is not None:
            sql += " AND kind=?"
            args.append(kind)
        return self.conn.execute(sql + " ORDER BY kind, ord", args).fetchall()

    def lineage_edges(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT src_mount, src_path, kind, raw, dst_mount, dst_path, resolved FROM links
               WHERE kind IN ('extends', 'supersedes')"""
        ).fetchall()

    def folder_counts(self, mount: str) -> tuple[list[tuple[str, int]], int, int]:
        """``([(folder, card_count)...], root_card_count, total_cards)`` for one mount (overview excluded)."""
        folders: dict[str, int] = {}
        root = 0
        total = 0
        for row in self.conn.execute("SELECT path FROM cards WHERE mount=? AND is_overview=0", (mount,)):
            total += 1
            head, sep, _ = row[0].partition("/")
            if sep:
                folders[head] = folders.get(head, 0) + 1
            else:
                root += 1
        ordered = sorted(folders.items(), key=lambda kv: (-kv[1], kv[0]))
        return ordered, root, total

    # ------------------------------------------------------------------
    # telemetry (best effort)
    # ------------------------------------------------------------------
    def bump_read(self, mount: str, path: str) -> tuple[int, float] | None:
        now = time.time()
        try:
            self.conn.execute(
                """INSERT INTO telemetry(mount, path, read_count, last_read_at) VALUES(?, ?, 1, ?)
                   ON CONFLICT(mount, path) DO UPDATE SET read_count = read_count + 1, last_read_at = excluded.last_read_at""",
                (mount, path, now),
            )
            row = self.conn.execute(
                "SELECT read_count, last_read_at FROM telemetry WHERE mount=? AND path=?", (mount, path)
            ).fetchone()
            return (row[0], row[1]) if row else None
        except sqlite3.Error:
            return None
