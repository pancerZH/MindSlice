"""Engine-owned JSONL history and recoverable file mutations (no history database).

All methods run under the workspace lock. A pending journal contains the exact intended bytes;
public history contains metadata only. Event IDs make replay after an interrupted append idempotent.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .card import sha256_bytes
from .errors import HistoryError
from .fsutil import atomic_write_text, fsync_dir, prune_empty_dirs, unlink_if_exists


def event(kind: str, **fields: Any) -> dict[str, Any]:
    return {"schema_version": 1, "event_id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(), "event": kind, **fields}


def change(kind: str, **fields: Any) -> dict[str, Any]:
    return event(kind, change_id=uuid.uuid4().hex, **fields)


def transitions(kind: str, ids: list[str], **fields: Any) -> list[dict[str, Any]]:
    transition_id = uuid.uuid4().hex
    return [event(kind, change_id=id, transition_id=transition_id, **fields) for id in ids]


def file_sha(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def file_action(path: Path, text: str | None, prune_root: Path | None = None) -> dict[str, Any]:
    return {"path": str(path.absolute()), "before_sha256": file_sha(path), "text": text,
            "after_sha256": sha256_bytes(text.encode("utf-8")) if text is not None else None,
            "prune_root": str(prune_root) if prune_root else None}


class ChangeHistory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "changes.jsonl"
        self.journal_path = root / ".pending.json"

    def has_journal(self) -> bool:
        return self.journal_path.exists()

    def _read(self) -> tuple[list[dict[str, Any]], int]:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return [], 0
        events = []
        offset = 0
        for line in data.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break  # an interrupted last append; replay rewrites it from the durable journal
            try:
                item = json.loads(line)
                if not isinstance(item, dict) or not isinstance(item.get("event_id"), str):
                    raise ValueError("missing event_id")
            except (ValueError, UnicodeDecodeError) as exc:
                raise HistoryError(f"invalid history record at byte {offset}: {self.path}", path=str(self.path)) from exc
            events.append(item)
            offset += len(line)
        return events, offset

    def events(self) -> list[dict[str, Any]]:
        return self._read()[0]

    def append(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        existing, complete_bytes = self._read()
        seen = {e["event_id"]: e for e in existing}
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+b") as stream:
            stream.truncate(complete_bytes)
            for item in events:
                old = seen.get(item["event_id"])
                if old is not None:
                    if old != item:
                        raise HistoryError("history event ID collision", event_id=item["event_id"])
                    continue
                stream.write((json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                seen[item["event_id"]] = item
            stream.flush()
            os.fsync(stream.fileno())
        fsync_dir(self.root)

    def transact(self, actions: list[dict[str, Any]], events: list[dict[str, Any]],
                 *, guards: list[dict[str, Any]] | None = None) -> None:
        if self.has_journal():
            raise HistoryError("an unfinished history transaction must be recovered first", path=str(self.journal_path))
        # Validate existing history before changing any content.
        self.events()
        journal = {"version": 1, "actions": actions, "events": events, "guards": guards or []}
        atomic_write_text(self.journal_path, json.dumps(journal, ensure_ascii=False) + "\n")
        self.recover()

    def recover(self) -> bool:
        try:
            journal = json.loads(self.journal_path.read_text(encoding="utf-8"))
            if journal.get("version") != 1 or not isinstance(journal.get("actions"), list) or not isinstance(journal.get("events"), list):
                raise ValueError("invalid journal structure")
        except FileNotFoundError:
            return False
        except (ValueError, UnicodeDecodeError, AttributeError) as exc:
            raise HistoryError("invalid history journal; preserved for inspection", path=str(self.journal_path)) from exc
        self.events()
        conflicts = []
        for guard in journal.get("guards", []):
            if file_sha(Path(guard["path"])) != guard["sha256"]:
                conflicts.append({"path": guard["path"], "reason": "baked output changed or missing"})
        for action in journal["actions"]:
            actual = file_sha(Path(action["path"]))
            if actual not in (action["before_sha256"], action["after_sha256"]):
                conflicts.append({"path": action["path"], "current_sha256": actual})
        if conflicts:
            raise HistoryError("history recovery stopped: files changed outside the transaction; "
                               "files and journal were preserved", conflicts=conflicts, journal=str(self.journal_path))
        for action in journal["actions"]:
            path = Path(action["path"])
            if file_sha(path) != action["after_sha256"]:
                if action["text"] is None:
                    unlink_if_exists(path)
                else:
                    atomic_write_text(path, action["text"])
            if action["text"] is None and action.get("prune_root"):
                prune_empty_dirs(Path(action["prune_root"]), path.parent)
        self.append(journal["events"])
        unlink_if_exists(self.journal_path)  # last: a crash after append must only deduplicate events
        return True

    def details(self) -> dict[str, dict[str, Any]]:
        found = {}
        for item in self.events():
            id = item.get("change_id")
            if id and id not in found and item["event"] in ("proposed", "applied"):
                found[id] = {k: item[k] for k in ("change_id", "timestamp", "op", "reason", "before_sha256", "after_sha256")
                             if k in item}
        return found

    def descriptions(self, ids: list[str], *, records=None) -> list[dict[str, Any]]:
        found = self.details() if records is None else records
        return [found[id] for id in ids if id in found]

    def applied(self) -> dict[str, tuple[str | None, list[str]]]:
        """Active overlay revision chains; external edits break ancestry instead of inheriting stale reasons."""
        active: dict[str, tuple[str | None, list[str]]] = {}
        groups: dict[str, str | None] = {}
        for item in self.events():
            if item["event"] == "applied":
                address = item["address"]
                tip, ids = active.get(address, (None, []))
                group = item.get("transition_id") or item["event_id"]
                if groups.get(address) != group and tip != item.get("before_sha256"):
                    ids = []
                ids = list(ids)
                if item["change_id"] not in ids:
                    ids.append(item["change_id"])
                after = item.get("after_sha256")
                active[address] = (after, ids if after is not None else [])
                groups[address] = group
            elif item["event"] in ("baked", "retired"):
                for address in item.get("retired_overlay_cards", []):
                    active.pop(address, None)
                    groups.pop(address, None)
        return active

    def changes_for(self, address: str, sha: str | None) -> list[dict[str, Any]]:
        tip, ids = self.applied().get(address, (None, []))
        return self.descriptions(ids) if tip == sha and sha is not None else []
