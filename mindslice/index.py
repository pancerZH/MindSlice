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
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .addressing import MountCatalog, resolve_ref
from .card import parse_card, preview_text, sha256_bytes
from .config import OVERVIEW_PATH, Mount, MountTable
from .fsutil import iter_markdown

SCHEMA_VERSION = "1"
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
    errors TEXT NOT NULL, warnings TEXT NOT NULL,
    UNIQUE(mount, path)
);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    title, aliases, tags, summary, body, tokenize = '{TOKENIZER}'
);
CREATE TABLE IF NOT EXISTS card_aliases(mount TEXT NOT NULL, path TEXT NOT NULL, alias TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS card_aliases_idx ON card_aliases(mount, alias);
CREATE TABLE IF NOT EXISTS card_tags(mount TEXT NOT NULL, path TEXT NOT NULL, tag TEXT NOT NULL);
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

_DATA_TABLES = ("cards", "cards_fts", "card_aliases", "card_tags", "links", "mounts", "meta")


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


def fts_match_expression(query: str) -> str:
    """Turn free text into a safe FTS5 expression: quoted terms OR'ed together (``term*`` = prefix)."""
    terms: list[str] = []
    for m in re.finditer(r"\w+(\*)?", query or "", re.UNICODE):
        term = m.group(0).rstrip("*").replace('"', "")
        if not term:
            continue
        token = f'"{term}"' + ("*" if m.group(1) else "")
        if token not in terms:
            terms.append(token)
    return " OR ".join(terms)


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
        try:
            conn = self._open()
            version = self._schema_version(conn)
            if version not in (None, SCHEMA_VERSION):
                conn.close()
                self._delete_db()
                conn = self._open()
        except sqlite3.DatabaseError:
            self._delete_db()
            conn = self._open()
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
        conn.commit()
        return conn

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("SELECT 1").fetchone()  # surfaces 'file is not a database'
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
            for name in _DATA_TABLES:
                conn.execute(f"DELETE FROM {name}")
            conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return self.sync(table, exclude, verify=True)

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
        preview, _ = preview_text(parsed.summary, parsed.body, limit=10_000)
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        cur = self.conn.execute(
            """INSERT INTO cards(mount, path, title, aliases, tags, extends, supersedes, summary, preview,
                   sha256, mtime_ns, size, lines, is_overview, has_frontmatter, errors, warnings)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mount,
                path,
                title,
                json.dumps(parsed.aliases, ensure_ascii=False),
                json.dumps(parsed.tags, ensure_ascii=False),
                json.dumps(parsed.extends, ensure_ascii=False),
                json.dumps(parsed.supersedes, ensure_ascii=False),
                parsed.summary,
                preview,
                digest,
                mtime_ns,
                size,
                lines,
                1 if path == OVERVIEW_PATH else 0,
                1 if parsed.has_frontmatter else 0,
                json.dumps(parsed.errors, ensure_ascii=False),
                json.dumps(parsed.warnings, ensure_ascii=False),
            ),
        )
        card_id = cur.lastrowid
        alias_text = " ".join(parsed.aliases + [path.replace("/", " ")])
        self.conn.execute(
            "INSERT INTO cards_fts(rowid, title, aliases, tags, summary, body) VALUES(?, ?, ?, ?, ?, ?)",
            (card_id, title, alias_text, " ".join(parsed.tags), parsed.summary, parsed.body),
        )
        self.conn.executemany(
            "INSERT INTO card_aliases(mount, path, alias) VALUES(?, ?, ?)",
            [(mount, path, a.strip().lower()) for a in parsed.aliases if a.strip()],
        )
        self.conn.executemany(
            "INSERT INTO card_tags(mount, path, tag) VALUES(?, ?, ?)",
            [(mount, path, t.strip().lower()) for t in dict.fromkeys(parsed.tags) if t.strip()],
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
        args: list[Any] = [alias.strip().lower()]
        if mount is not None:
            sql += " AND a.mount=?"
            args.append(mount)
        sql += " ORDER BY m.precedence DESC, c.mount, c.path"
        return self.conn.execute(sql, args).fetchall()

    def all_cards(self, mount: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT c.*, m.precedence, m.role FROM cards c JOIN mounts m ON m.alias = c.mount"
        args: tuple[Any, ...] = ()
        if mount is not None:
            sql += " WHERE c.mount=?"
            args = (mount,)
        return self.conn.execute(sql + " ORDER BY m.precedence DESC, c.mount, c.path", args).fetchall()

    def search(
        self, query: str, sources: Iterable[str] | None = None, tags: Iterable[str] | None = None
    ) -> list[sqlite3.Row]:
        """All FTS matches (excluding overviews) with ``score = -bm25(...) > 0``, best first."""
        expr = fts_match_expression(query)
        where: list[str] = ["c.is_overview = 0"]
        args: list[Any] = []
        if expr:
            weights = ", ".join(str(w) for w in BM25_WEIGHTS)
            sql = f"""SELECT c.*, m.precedence, m.role, -bm25(cards_fts, {weights}) AS score
                      FROM cards_fts JOIN cards c ON c.id = cards_fts.rowid
                      JOIN mounts m ON m.alias = c.mount"""
            where.insert(0, "cards_fts MATCH ?")
            args.append(expr)
        elif (query or "").strip():
            return []
        else:
            sql = """SELECT c.*, m.precedence, m.role, 0.0 AS score FROM cards c
                     JOIN mounts m ON m.alias = c.mount"""
        source_list = list(sources or [])
        if source_list:
            where.append(f"c.mount IN ({', '.join('?' * len(source_list))})")
            args += source_list
        tag_list = sorted({t.strip().lower() for t in (tags or []) if t.strip()})
        if tag_list:
            where.append(
                f"""(SELECT COUNT(DISTINCT t.tag) FROM card_tags t WHERE t.mount = c.mount AND t.path = c.path
                    AND t.tag IN ({', '.join('?' * len(tag_list))})) = ?"""
            )
            args += tag_list + [len(tag_list)]
        sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY score DESC, m.precedence DESC, c.mtime_ns DESC, c.mount, c.path"
        return self.conn.execute(sql, args).fetchall()

    def card_has_tags(self, mount: str, path: str, tags: Iterable[str]) -> bool:
        wanted = {t.strip().lower() for t in tags if t.strip()}
        if not wanted:
            return True
        have = {r[0] for r in self.conn.execute("SELECT tag FROM card_tags WHERE mount=? AND path=?", (mount, path))}
        return wanted <= have

    def inbound(self, kind: str, mount: str, path: str) -> list[sqlite3.Row]:
        """Cards whose ``kind`` reference resolves to ``(mount, path)``."""
        return self.conn.execute(
            """SELECT DISTINCT l.src_mount, l.src_path, c.mtime_ns, m.precedence, m.role
               FROM links l JOIN cards c ON c.mount = l.src_mount AND c.path = l.src_path
               JOIN mounts m ON m.alias = l.src_mount
               WHERE l.kind=? AND l.dst_mount=? AND l.dst_path=? AND l.resolved=1
                 AND NOT (l.src_mount = l.dst_mount AND l.src_path = l.dst_path)
               ORDER BY m.precedence DESC, c.mtime_ns DESC, l.src_mount, l.src_path""",
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
