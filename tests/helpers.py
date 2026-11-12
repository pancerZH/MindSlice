from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Iterable

from mindslice import Workspace
from mindslice.model import tomlfmt


def card_text(
    title: str,
    summary: str = "",
    bullets: Iterable[str] = (),
    *,
    tags: Iterable[str] = (),
    aliases: Iterable[str] = (),
    extends: Iterable[str] = (),
    supersedes: Iterable[str] = (),
) -> str:
    fm = tomlfmt.dumps_flat(
        {
            "title": title,
            "aliases": list(aliases),
            "tags": list(tags),
            "extends": list(extends),
            "supersedes": list(supersedes),
        }
    )
    parts = [f"+++\n{fm}+++\n"]
    if summary:
        parts.append(f"\n{summary}\n")
    bullets = list(bullets)
    if bullets:
        parts.append("\n" + "\n".join(f"- {b}" for b in bullets) + "\n")
    return "".join(parts)


def add_filler(ws: Workspace, n: int = 8) -> None:
    """Unrelated cards so BM25 sees a corpus with positive IDF (tiny corpora clamp it to ~0)."""
    for i in range(n):
        ws.write(f"filler/{i}", title=f"Filler {i}", summary=f"Unrelated gardening note number {i}.")


def bump_mtime(path: Path, delta_ns: int = 1_000_000_000) -> None:
    """Simulate an editor save that lands on a later clock tick."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + delta_ns))


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mindslice-test-"))
        self.root = self.tmp / "ws"
        self.ws = Workspace.init(self.root, lock_timeout=5.0)

    def tearDown(self) -> None:
        self.ws.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixtures ----------------------------------------------------------
    def make_slice(self, name: str, cards: dict[str, str], *, alias: str | None = None, description: str = "",
                   dependencies: Iterable[str] = (), overview: str | None = None) -> Path:
        root = self.root / "slices" / f"{name}.slice"
        root.mkdir(parents=True, exist_ok=True)
        manifest = {"name": name, "version": "1.0.0", "description": description or f"{name} slice",
                    "dependencies": list(dependencies)}
        if alias:
            manifest["alias"] = alias
        (root / "slice.toml").write_text(tomlfmt.dumps_document(top=manifest), encoding="utf-8")
        if overview is not None:
            (root / "overview.md").write_text(overview, encoding="utf-8")
        for path, text in cards.items():
            file = root / f"{path}.md"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding="utf-8")
        return root

    def mount_slice(self, name: str, cards: dict[str, str], alias: str, precedence: int, role: str, **kw) -> Path:
        root = self.make_slice(name, cards, alias=alias, **kw)
        self.ws.mount(root, alias=alias, precedence=precedence, role=role)
        return root

    def overlay_file(self, path: str) -> Path:
        return self.root / "overlay" / f"{path}.md"

    def put_overlay(self, path: str, text: str) -> Path:
        file = self.overlay_file(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        return file

    def project(self, cards: dict[str, str]) -> Path:
        """Mount ``@project`` (precedence=50, role=curated) - the design doc's reference setup."""
        return self.mount_slice("project-kb", cards, "@project", 50, "curated")

    # -- assertions --------------------------------------------------------
    def addresses(self, result: dict) -> list[str]:
        return [r["address"] for r in result["results"]]
