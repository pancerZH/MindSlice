"""write() semantics, freshness detection, manifest/search bounds, validate, pack, diff/apply, locking."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import tomllib
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path

from mindslice import (
    AlreadyExistsError,
    ApplyConflictError,
    FrontmatterError,
    LineageCycleError,
    LockTimeoutError,
    MountError,
    NotFoundError,
    PreconditionFailedError,
    ReadOnlyMountError,
    Workspace,
    WorkspaceNotFoundError,
)
from mindslice.locking import WorkspaceLock

from .helpers import WorkspaceTestCase, bump_mtime, card_text


class WriteTests(WorkspaceTestCase):
    def test_create_layout_and_idempotency(self):
        res = self.ws.write("user-preferences/tooling", summary="The user prefers uv.", content="- Use `uv run`.",
                            tags=["tooling"], aliases=["uv"])
        self.assertTrue(res["changed"])
        text = self.overlay_file("user-preferences/tooling").read_text()
        self.assertTrue(text.startswith('+++\ntitle = "Tooling"\naliases = ["uv"]\ntags = ["tooling"]\n'))
        self.assertIn("\n+++\n\nThe user prefers uv.\n\n- Use `uv run`.\n", text)
        again = self.ws.write("user-preferences/tooling", summary="The user prefers uv.", content="- Use `uv run`.",
                              tags=["tooling"], aliases=["uv"])
        self.assertFalse(again["changed"])
        self.assertEqual(again["sha256"], res["sha256"])
        with self.assertRaises(AlreadyExistsError):
            self.ws.write("user-preferences/tooling", summary="Different.")

    def test_replace_with_if_match_and_field_patching(self):
        first = self.ws.write("notes/a", title="A", summary="First.", content="- one", tags=["x"])
        with self.assertRaises(PreconditionFailedError):
            self.ws.write("notes/a", op="replace", summary="Nope.", if_match="0" * 64)
        res = self.ws.write("notes/a", op="replace", summary="Second.", if_match=first["sha256"])
        card = self.ws.read("notes/a")
        self.assertEqual(card["summary"], "Second.")
        self.assertEqual(card["body"], "- one\n")
        self.assertEqual(card["tags"], ["x"])
        self.assertEqual(card["sha256"], res["sha256"])

    def test_replace_preserves_hand_written_frontmatter(self):
        self.put_overlay("notes/h", '+++\ntitle = "Hand"   # a human comment\ntags = ["k"]\n+++\n\nSummary.\n\n- a\n')
        self.ws.write("notes/h", op="replace", content="- b")
        text = self.overlay_file("notes/h").read_text()
        self.assertIn("# a human comment", text)
        self.assertTrue(text.endswith("\n+++\n\nSummary.\n\n- b\n"))

    def test_append_dedupes_and_unions_lists(self):
        self.ws.write("notes/b", summary="B.", content="- one", tags=["a"])
        res = self.ws.write("notes/b", op="append", content="- one\n- two", tags=["b"])
        self.assertEqual((res["added_statements"], res["duplicate_statements"]), (1, 1))
        retry = self.ws.write("notes/b", op="append", content="- one\n- two", tags=["b"])
        self.assertFalse(retry["changed"])
        card = self.ws.read("notes/b")
        self.assertEqual(card["body"], "- one\n- two\n")
        self.assertEqual(card["tags"], ["a", "b"])
        with self.assertRaises(NotFoundError):
            self.ws.write("notes/missing", op="append", content="- x")

    def test_delete_is_idempotent(self):
        self.ws.write("notes/c", summary="C.")
        self.assertTrue(self.ws.write("notes/c", op="delete")["changed"])
        self.assertFalse(self.overlay_file("notes/c").exists())
        self.assertFalse((self.root / "overlay/notes").exists())  # empty dirs pruned
        self.assertFalse(self.ws.write("notes/c", op="delete")["changed"])
        with self.assertRaises(NotFoundError):
            self.ws.read("notes/c")

    def test_base_slices_are_read_only(self):
        self.project({"api/auth": card_text("Auth", "Auth.")})
        with self.assertRaises(ReadOnlyMountError):
            self.ws.write("@project/api/auth", op="replace", summary="hijack")
        self.assertEqual(self.ws.write("@overlay/api/auth", summary="ok")["address"], "@overlay/api/auth")

    def test_cycles_rejected(self):
        self.ws.write("a", summary="A.")
        self.ws.write("b", summary="B.", supersedes=["a"])
        with self.assertRaises(LineageCycleError):
            self.ws.write("a", op="replace", extends=["b"])
        with self.assertRaises(LineageCycleError):
            self.ws.write("self", summary="S.", extends=["self"])
        # A cycle that only exists once staged changes are combined with live state is also caught:
        # staged c -> live b -> live a, then staging a -> c closes the loop.
        self.ws.write("c", summary="C.", supersedes=["b"], stage=True)
        with self.assertRaises(LineageCycleError):
            self.ws.write("a", op="replace", extends=["c"], stage=True)

    def test_invalid_ids_and_values(self):
        for bad in ("../escape", ".hidden/x", "a/[x]", ""):
            with self.assertRaises(ValueError, msg=bad):
                self.ws.write(bad, summary="x")
        with self.assertRaises(FrontmatterError):
            self.ws.write("x", summary="x", tags=[1, 2])

    def test_unresolved_lineage_warns(self):
        res = self.ws.write("x", summary="x", extends=["@project/nope"])
        self.assertTrue(res["warnings"])


class FreshnessTests(WorkspaceTestCase):
    def test_external_edits_create_rename_delete(self):
        root = self.project({"api/auth": card_text("Auth", "Original wording.")})
        self.assertEqual(self.ws.search("original")["total_matches"], 1)
        file = root / "api/auth.md"
        file.write_text(card_text("Auth", "Rewritten by a human editor."), encoding="utf-8")
        bump_mtime(file)
        self.assertEqual(self.ws.search("original")["total_matches"], 0)
        self.assertEqual(self.ws.search("rewritten")["total_matches"], 1)
        file.rename(root / "api/login.md")
        self.assertEqual(self.addresses(self.ws.search("rewritten")), ["@project/api/login"])
        (root / "api/login.md").unlink()
        self.assertEqual(self.ws.search("rewritten")["total_matches"], 0)

    def test_rebuild_catches_same_mtime_and_size_edits(self):
        file = self.put_overlay("x", card_text("X", "alpha words here."))
        self.assertEqual(self.ws.search("alpha")["total_matches"], 1)
        st = file.stat()
        file.write_text(card_text("X", "gamma words here."), encoding="utf-8")  # same size
        import os

        os.utime(file, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual(self.ws.search("gamma")["total_matches"], 0)  # invisible to the cheap check
        res = self.ws.validate(rebuild_index=True)
        self.assertEqual(res["rebuilt_index"]["added"], 1)
        self.assertEqual(self.ws.search("gamma")["total_matches"], 1)

    def test_index_is_disposable_and_telemetry_survives_rebuild(self):
        self.ws.write("x", summary="Durable fact about otters.")
        self.ws.read("x")
        self.ws.read("x")
        self.ws.validate(rebuild_index=True)
        self.assertEqual(self.ws.read("x")["read_count"], 3)
        self.ws.close()
        for p in (self.root / ".cache").glob("index.sqlite*"):
            p.unlink()
        self.ws = Workspace(self.root)
        res = self.ws.read("x")
        self.assertEqual(res["summary"], "Durable fact about otters.")
        self.assertEqual(res["read_count"], 1)  # telemetry is ephemeral by design

    def test_corrupt_index_is_rebuilt(self):
        self.ws.write("x", summary="Fact about lynxes.")
        self.ws.close()
        (self.root / ".cache/index.sqlite").write_bytes(b"not a database at all" * 100)
        for suffix in ("-wal", "-shm"):
            p = self.root / f".cache/index.sqlite{suffix}"
            if p.exists():
                p.unlink()
        self.ws = Workspace(self.root)
        self.assertEqual(self.ws.search("lynxes")["total_matches"], 1)

    def test_hand_edited_mounts_toml(self):
        root = self.make_slice("kb", {"a": card_text("A", "Penguin facts.")}, alias="@kb")
        text = (self.root / "mounts.toml").read_text()
        text += f'\n[[mounts]]\npath = {json.dumps(str(root))}\nalias = "@kb"\nprecedence = 5\nrole = "baseline"\n'
        (self.root / "mounts.toml").write_text(text)
        self.assertEqual(self.addresses(self.ws.search("penguin")), ["@kb/a"])


class ManifestSearchTests(WorkspaceTestCase):
    def test_manifest_bounds(self):
        cards = {f"topic{i}/card": card_text(f"T{i}", f"Topic {i}.") for i in range(12)}
        cards["root-card"] = card_text("Root", "Root level.")
        self.mount_slice("big", cards, "@big", 10, "baseline", description="x" * 200,
                         overview="# Big\n\nAn overview of the big slice.\n", dependencies=["@persona"])
        res = self.ws.manifest(limit=1, offset=1, max_folders_per_mount=10, include_overview=True)
        self.assertEqual(res["total_mounts"], 2)
        self.assertFalse(res["truncated"])
        m = res["mounts"][0]
        self.assertEqual(m["alias"], "@big")
        self.assertEqual((m["card_count"], m["root_cards"], m["total_folders"]), (13, 1, 12))
        self.assertEqual(len(m["folders"]), 10)
        self.assertTrue(m["folders_truncated"])
        self.assertLessEqual(len(m["description"]), 160)
        self.assertTrue(m["description_truncated"])
        self.assertIn("overview of the big slice", m["overview"])
        self.assertEqual(m["missing_dependencies"], ["@persona"])
        first = self.ws.manifest(limit=1)
        self.assertTrue(first["truncated"])
        self.assertEqual(first["next_offset"], 1)

    def test_search_pagination_tags_and_neighbors(self):
        cards = {f"c{i}": card_text(f"Card {i}", f"Shared keyword walrus number {i}.", tags=["even" if i % 2 == 0 else "odd"])
                 for i in range(6)}
        cards["hub"] = card_text("Hub", "Hub card.", [f"see [[c{i}]]" for i in range(5)] + ["walrus"])
        self.mount_slice("kb", cards, "@kb", 10, "baseline")
        page1 = self.ws.search("walrus", k=4)
        self.assertEqual(page1["total_matches"], 7)
        self.assertTrue(page1["truncated"])
        page2 = self.ws.search("walrus", k=4, offset=page1["next_offset"])
        self.assertIsNone(page2["next_offset"])
        self.assertEqual(len(set(self.addresses(page1)) | set(self.addresses(page2))), 7)
        even = self.ws.search("walrus", tags=["even"])
        self.assertEqual(even["total_matches"], 3)
        hub = next(r for r in self.ws.search("hub")["results"] if r["address"] == "@kb/hub")
        self.assertEqual(hub["total_neighbors"], 5)
        self.assertEqual(len(hub["neighbors"]), 3)
        self.assertTrue(hub["neighbors_truncated"])
        c0 = next(r for r in self.ws.search("walrus number 0")["results"] if r["address"] == "@kb/c0")
        self.assertEqual(c0["neighbors"][0]["direction"], "in")
        self.assertEqual(self.ws.search("walr*")["total_matches"], 7)
        self.assertEqual(self.ws.search("", tags=["odd"])["total_matches"], 3)
        self.assertEqual(self.ws.search("!!!")["total_matches"], 0)
        with self.assertRaises(NotFoundError):
            self.ws.search("walrus", source="@nope")

    def test_summary_cap_and_overview_excluded(self):
        long = "word " * 100
        self.mount_slice("kb", {"long": card_text("Long", long.strip())}, "@kb", 10, "baseline",
                         overview="# KB\n\nword overview.\n")
        res = self.ws.search("word")
        self.assertEqual(self.addresses(res), ["@kb/long"])
        self.assertLessEqual(len(res["results"][0]["summary"]), 240)
        self.assertTrue(res["results"][0]["summary_truncated"])
        overview = self.ws.read("@kb/overview")
        self.assertEqual(overview["title"], "KB")
        self.assertIn("word overview", overview["body"])

    def test_read_by_alias_and_backlink_pagination(self):
        cards = {"target": card_text("Target", "The target.", aliases=["bullseye"])}
        cards.update({f"src{i}": card_text(f"S{i}", f"Source {i}.", ["link [[bullseye]]"]) for i in range(4)})
        self.mount_slice("kb", cards, "@kb", 10, "baseline")
        res = self.ws.read("@kb/bullseye", max_backlinks=3)
        self.assertEqual(res["address"], "@kb/target")
        self.assertEqual(res["total_backlinks"], 4)
        self.assertEqual(len(res["backlinks"]), 3)
        self.assertEqual(res["backlinks_next_offset"], 3)
        self.assertEqual(self.ws.read("bullseye")["address"], "@kb/target")


class ValidateTests(WorkspaceTestCase):
    def test_lints(self):
        long_body = [f"statement {i}" for i in range(60)]
        root = self.make_slice("bad", {
            "no-summary": "+++\ntitle = \"x\"\n+++\n\n- only bullets\n",
            "broken": card_text("Broken", "Has bad links.", ["see [[nowhere]]"], extends=["missing"]),
            "long": card_text("Long", "Long card.", long_body),
            "cyc-a": card_text("A", "A.", extends=["cyc-b"]),
            "cyc-b": card_text("B", "B.", supersedes=["cyc-a"]),
            "bad-toml": "+++\ntitle = \n+++\n\nx\n",
            "ext": card_text("Ext", "Uses an undeclared external slice.", extends=["@persona/tone"]),
        }, alias="@bad")
        res = self.ws.validate(root)
        codes = {(i["code"], i.get("address")) for i in res["errors"] + res["warnings"]}
        self.assertFalse(res["ok"])
        self.assertIn(("missing_summary", "@bad/no-summary"), codes)
        self.assertIn(("broken_wikilink", "@bad/broken"), codes)
        self.assertIn(("broken_lineage", "@bad/broken"), codes)
        self.assertIn(("card_too_long", "@bad/long"), codes)
        self.assertIn(("invalid_frontmatter", "@bad/bad-toml"), codes)
        self.assertIn(("undeclared_dependency", "@bad/ext"), codes)
        self.assertTrue(any(c == "lineage_cycle" for c, _ in codes))

    def test_workspace_validation(self):
        self.ws.write("ok", summary="Fine.")
        self.ws.write("ext", summary="Points outward.", extends=["@persona/tone"])
        self.ws.write("staged", summary="Staged.", stage=True)
        self.put_overlay("staged", card_text("Staged", "Created behind our back."))
        res = self.ws.validate()
        self.assertTrue(res["ok"], res["errors"])
        codes = {i["code"] for i in res["warnings"]}
        self.assertIn("unmounted_dependency", codes)
        self.assertIn("staging_conflict", codes)


class PackTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": card_text("Auth", "Auth.")})
        self.ws.write("team/a", summary="Team A.", content="- links [[@project/api/auth]] and [[team/b]]",
                      extends=["@project/api/auth"], tags=["team"])
        self.ws.write("team/b", summary="Team B.", tags=["team", "export"])
        self.ws.write("other", summary="Not exported.")

    def test_external_refs_become_dependencies(self):
        res = self.ws.pack(self.tmp / "team.slice", prefix="team/")
        self.assertEqual(res["dependencies"], ["@project"])
        sm = tomllib.loads((self.tmp / "team.slice/slice.toml").read_text())
        self.assertEqual(sm["dependencies"], ["@project"])
        self.assertEqual(sm["alias"], "@team")
        self.assertTrue(res["validation"]["ok"], res["validation"])

    def test_tag_filter(self):
        res = self.ws.pack(self.tmp / "export.slice", tags=["export"])
        self.assertEqual(res["cards"], ["team/b"])

    def test_archives_are_deterministic(self):
        def digest(p):
            return hashlib.sha256(p.read_bytes()).hexdigest()

        # The archive's root folder derives from the file name, so compare same-named outputs.
        for name in ("a.zip", "a.tar.gz"):
            self.ws.pack(self.tmp / name, prefix="team/")
            self.ws.pack(self.tmp / "again" / name, prefix="team/")
            self.assertEqual(digest(self.tmp / name), digest(self.tmp / "again" / name), name)
        with zipfile.ZipFile(self.tmp / "a.zip") as zf:
            self.assertIn("a.slice/team/a.md", zf.namelist())
            self.assertIn("a.slice/slice.toml", zf.namelist())
        with tarfile.open(self.tmp / "a.tar.gz") as tf:
            self.assertIn("a.slice/team/b.md", tf.getnames())

    def test_refuses_to_overwrite(self):
        (self.tmp / "out.slice").mkdir()
        (self.tmp / "out.slice/keep.txt").write_text("x")
        with self.assertRaises(AlreadyExistsError):
            self.ws.pack(self.tmp / "out.slice", prefix="team/")

    def test_nothing_selected(self):
        with self.assertRaises(NotFoundError):
            self.ws.pack(self.tmp / "none.slice", prefix="nope/")


class StagingTests(WorkspaceTestCase):
    def test_full_cycle(self):
        self.ws.write("keep", summary="Keep me.", content="- k")
        self.ws.write("gone", summary="Delete me.")
        self.ws.write("keep", op="append", content="- staged addition", stage=True)
        self.ws.write("gone", op="delete", stage=True)
        self.ws.write("brand/new", summary="Brand new.", stage=True)
        diff = self.ws.diff()
        self.assertEqual(diff["summary"], {"total": 3, "create": 1, "modify": 1, "delete": 1, "conflicts": 0})
        self.assertIn("+- staged addition", diff["patch"])
        self.assertEqual(self.ws.manifest()["staging"], {"pending": 3})
        res = self.ws.apply()
        self.assertEqual(res["created"], ["@overlay/brand/new"])
        self.assertEqual(res["modified"], ["@overlay/keep"])
        self.assertEqual(res["deleted"], ["@overlay/gone"])
        self.assertIn("staged addition", self.ws.read("keep")["body"])
        self.assertEqual(list((self.root / "staging").iterdir()), [])
        self.assertEqual(self.ws.apply()["applied"], 0)

    def test_staged_edits_preserve_base_and_create_then_delete_vanishes(self):
        self.ws.write("x", summary="X.", content="- a")
        base = self.ws.read("x")["sha256"]
        self.ws.write("x", op="append", content="- b", stage=True)
        staged_sha = self.ws.diff()["items"][0]["staged_sha256"]
        self.ws.write("x", op="replace", summary="X2.", stage=True, if_match=staged_sha)
        entry = self.ws.diff()["items"][0]
        self.assertEqual(entry["base_sha256"], base)
        self.assertEqual(entry["history"], ["append", "replace"])
        self.ws.write("only-staged", summary="tmp", stage=True)
        self.ws.write("only-staged", op="delete", stage=True)
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["x"])
        self.assertEqual(self.ws.discard()["discarded"], 1)
        self.assertEqual(self.ws.diff()["items"], [])

    def test_orphan_staged_files_require_absence(self):
        (self.root / "staging/drafts").mkdir(parents=True)
        (self.root / "staging/drafts/rate-limit.md").write_text(card_text("Rate limit", "Draft from a human."))
        item = self.ws.diff()["items"][0]
        self.assertTrue(item["orphan"])
        self.assertEqual(item["change"], "create")
        self.ws.apply()
        self.assertEqual(self.ws.read("drafts/rate-limit")["summary"], "Draft from a human.")

    def test_apply_rejects_invalid_staged_card(self):
        (self.root / "staging/bad.md").write_text("+++\ntitle = \n+++\n")
        with self.assertRaises(Exception) as ctx:
            self.ws.apply()
        self.assertEqual(ctx.exception.details["conflicts"][0]["reason"], "invalid_card")

    def test_apply_rejects_cycle_closed_by_a_live_edit(self):
        a = self.put_overlay("a", card_text("A", "Card A."))
        b = self.put_overlay("b", card_text("B", "Card B."))
        self.ws.write("a", op="replace", extends=["b"], stage=True)  # acyclic when staged
        original = a.read_bytes()
        b.write_text(card_text("B", "Card B.", supersedes=["a"]), encoding="utf-8")  # unstaged edit closes a <-> b
        bump_mtime(b)
        with self.assertRaises(ApplyConflictError) as ctx:
            self.ws.apply()  # a's base_sha256 still matches, so only the combined lineage check can object
        self.assertEqual(ctx.exception.details["conflicts"], [
            {"address": "@overlay/a", "reason": "lineage_cycle", "cycle": ["@overlay/a", "@overlay/b", "@overlay/a"]}])
        self.assertEqual(a.read_bytes(), original)
        self.assertFalse(self.ws.staging.journal_path.exists())
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["a"])

    def test_overlay_diff_classification(self):
        self.project({"api/auth": card_text("Auth", "Auth."), "api/old": card_text("Old", "Old.")})
        self.ws.write("api/auth", summary="Shadow copy.")
        self.ws.write("api/ext", summary="Ext.", extends=["@project/api/auth"])
        self.ws.write("api/new", summary="New.", supersedes=["@project/api/old"])
        self.ws.write("fresh", summary="Fresh.")
        kinds = {i["id"]: i["kind"] for i in self.ws.diff("overlay")["items"]}
        self.assertEqual(kinds, {"api/auth": "shadow", "api/ext": "extends", "api/new": "supersedes", "fresh": "new"})


class MountTests(WorkspaceTestCase):
    def test_mount_unmount(self):
        root = self.make_slice("persona", {"tone": card_text("Tone", "Be concise.")}, alias="@persona")
        res = self.ws.mount(root, precedence=10)
        self.assertEqual((res["alias"], res["path"], res["cards"]), ("@persona", "./slices/persona.slice", 1))
        mounts = tomllib.loads((self.root / "mounts.toml").read_text())
        self.assertEqual(mounts["mounts"][0]["alias"], "@persona")
        with self.assertRaises(MountError):
            self.ws.mount(root, alias="@other")
        with self.assertRaises(MountError):
            self.ws.unmount("@overlay")
        self.assertEqual(self.ws.unmount("persona")["removed_cards"], 1)
        self.assertEqual(self.ws.search("concise")["total_matches"], 0)
        with self.assertRaises(NotFoundError):
            self.ws.unmount("@persona")

    def test_workspace_discovery(self):
        (self.root / "overlay/deep/er").mkdir(parents=True)
        with Workspace.discover(self.root / "overlay/deep/er") as found:
            self.assertEqual(found.root, self.root)
        with self.assertRaises(WorkspaceNotFoundError):
            Workspace(self.tmp / "nowhere")


class RobustnessTests(WorkspaceTestCase):
    def test_directory_symlink_loop_is_scanned_once(self):
        import os

        self.ws.write("loop/card", summary="Card about capybaras.")
        try:
            os.symlink(self.root / "overlay/loop", self.root / "overlay/loop/again", target_is_directory=True)
        except OSError as exc:
            if sys.platform == "win32" and exc.winerror == 1314:
                self.skipTest("directory symlinks require Windows Developer Mode or symlink privilege")
            raise
        res = self.ws.search("capybaras")
        self.assertEqual(res["total_matches"], 1)

    def test_corrupt_journal_is_quarantined_without_touching_staging(self):
        self.ws.write("x", summary="Staged.", stage=True)
        self.ws.staging.journal_path.write_bytes(b"{not json")
        self.ws.search("anything")
        self.assertFalse(self.ws.staging.journal_path.exists())
        self.assertIn("corrupt_journal", self.ws.last_recovery)
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["x"])  # staging intact

    def test_readme_python_example(self):
        ws = self.ws
        ws.write("user-preferences/tooling", summary="The user prefers uv over pip.",
                 content=["Use `uv run` for scripts.", "Use `uv add` for dependencies."], tags=["tooling"])
        hits = ws.search("uv dependencies", k=5)
        card = ws.read(hits["results"][0]["address"])
        res = ws.write("user-preferences/tooling", op="append", content="- Pin Python with `uv python pin`.",
                       if_match=card["sha256"])
        self.assertEqual(res["added_statements"], 1)
        self.assertEqual(ws.read("user-preferences/tooling")["body"].count("\n- "), 2)


# WindowsCompatibilityTests covers CRLF hashes and actual process-exit recovery;
# WindowsTests covers native paths, msvcrt contention and open-file sharing errors.
# ConcurrencyTests in test_interfaces.py exercises simultaneous readers/writers.
# Process recovery does not establish power-loss durability: fsync_dir is best
# effort on Windows, where directory flushes may be unavailable.
class WindowsCompatibilityTests(WorkspaceTestCase):
    def test_crlf_hash_and_if_match_use_raw_bytes(self):
        file = self.put_overlay("crlf", "")
        raw = card_text("CRLF", "Editor content.", ["one"]).replace("\n", "\r\n").encode("utf-8")
        file.write_bytes(raw)
        card = self.ws.read("crlf")
        self.assertEqual(card["body"], "- one\n")
        self.assertEqual(card["sha256"], hashlib.sha256(raw).hexdigest())
        with self.assertRaises(PreconditionFailedError):
            self.ws.write("crlf", op="append", content="- two",
                          if_match=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
        self.assertEqual(file.read_bytes(), raw)
        result = self.ws.write("crlf", op="append", content="- two", if_match=card["sha256"])
        self.assertEqual(result["sha256"], hashlib.sha256(file.read_bytes()).hexdigest())
        self.assertNotIn(b"\r", file.read_bytes())
        self.assertEqual(self.ws.read("crlf")["body"], "- one\n- two\n")

    def test_crlf_staging_preconditions_and_editor_conversion_conflict(self):
        self.ws.write("crlf", summary="Original.")
        file = self.overlay_file("crlf")
        file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))
        base = self.ws.read("crlf")["sha256"]
        self.ws.write("crlf", op="replace", summary="Staged.", stage=True, if_match=base)
        staged = self.ws.staging.file("crlf")
        staged.write_bytes(staged.read_bytes().replace(b"\n", b"\r\n"))
        staged_sha = hashlib.sha256(staged.read_bytes()).hexdigest()
        self.ws.write("crlf", op="append", content="- staged edit", stage=True, if_match=staged_sha)
        [item] = self.ws.diff()["items"]
        self.assertEqual(item["base_sha256"], base)
        self.assertEqual(item["staged_sha256"], hashlib.sha256(staged.read_bytes()).hexdigest())
        self.assertEqual(self.ws.apply()["modified"], ["@overlay/crlf"])
        self.assertEqual(self.ws.read("crlf")["body"], "- staged edit\n")
        self.ws.write("crlf", op="replace", summary="Another draft.", stage=True)
        file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))
        saved = file.read_bytes()
        with self.assertRaises(ApplyConflictError):
            self.ws.apply()
        self.assertEqual(file.read_bytes(), saved)
        self.assertTrue(self.ws.diff()["items"][0]["conflict"])

    def test_apply_recovers_after_process_exits_mid_batch(self):
        self.ws.write("b-modified", summary="Original.")
        self.ws.write("c-deleted", summary="Delete me.")
        self.ws.write("a-created", summary="Recovered capybara.", stage=True)
        self.ws.write("b-modified", op="replace", summary="Recovered wombat.", stage=True)
        self.ws.write("c-deleted", op="delete", stage=True)
        self.ws.close()
        worker = """
import os, sys
from mindslice import Workspace, staging
move = staging.durable_move
def crash_after_move(src, dst):
    move(src, dst)
    os._exit(77)
staging.durable_move = crash_after_move
with Workspace(sys.argv[1]) as ws:
    ws.apply()
"""
        proc = subprocess.run([sys.executable, "-c", worker, str(self.root)],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 77, proc.stderr)
        self.assertTrue(self.ws.staging.journal_path.exists())
        self.assertTrue(self.overlay_file("a-created").exists())
        self.assertTrue(self.ws.staging.file("b-modified").exists())
        self.ws = Workspace(self.root)
        self.assertEqual(self.ws.search("recovered")["total_matches"], 2)
        self.assertTrue(self.ws.last_recovery["recovered"])
        self.assertEqual(self.ws.read("b-modified")["summary"], "Recovered wombat.")
        with self.assertRaises(NotFoundError):
            self.ws.read("c-deleted")
        self.assertFalse(self.ws.staging.journal_path.exists())
        self.assertEqual(self.ws.diff()["items"], [])
        self.ws.close()
        self.ws = Workspace(self.root)
        self.assertEqual(self.ws.search("recovered")["total_matches"], 2)
        self.assertIsNone(self.ws.last_recovery)


@unittest.skipUnless(sys.platform == "win32", "requires native Windows paths, locks and file sharing")
class WindowsTests(WorkspaceTestCase):
    @contextmanager
    def held_by_process(self, path, mode="file"):
        """Wait for an actual child-owned handle/lock, with bounded startup/cleanup."""
        ready = self.tmp / "holder-ready"
        ready.unlink(missing_ok=True)
        worker = """
import sys
from pathlib import Path
from mindslice.locking import WorkspaceLock
path, mode, ready = sys.argv[1:]
lock = WorkspaceLock(Path(path), timeout=2)
try:
    with open(path, 'rb') if mode == 'file' else lock.hold(mode):
        Path(ready).write_bytes(b'ready')
        sys.stdin.buffer.read()
finally:
    lock.close()
"""
        proc = subprocess.Popen([sys.executable, "-c", worker, str(path), mode, str(ready)],
                                cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists():
                if proc.poll() is not None:
                    self.fail(f"holder exited before acquiring handle: {proc.communicate()!r}")
                if time.monotonic() >= deadline:
                    self.fail("holder did not acquire handle within 10 seconds")
                time.sleep(0.01)
            yield proc
        finally:
            try:
                _, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=10)
                raise
            ready.unlink(missing_ok=True)
        self.assertEqual(proc.returncode, 0, err)

    def test_readers_serialize_and_nested_upgrade_keeps_lock(self):
        self.ws.search("warm up")
        self.ws.lock.timeout = 0.1
        for mode in ("shared", "exclusive"):
            with self.subTest(mode=mode):
                with self.held_by_process(self.ws.lock.path, mode):
                    with self.assertRaises(LockTimeoutError):
                        self.ws.search("anything")
                    with self.assertRaises(LockTimeoutError):
                        self.ws.write("blocked", summary="Must not be written.")
                self.assertEqual(self.ws.search("anything")["total_matches"], 0)
                self.assertFalse(self.overlay_file("blocked").exists())
        other = WorkspaceLock(self.ws.lock.path, timeout=0.1)
        self.addCleanup(other.close)
        with self.ws.lock.shared():
            with self.ws.lock.shared():
                with self.ws.lock.exclusive():
                    self.assertEqual(self.ws.lock.mode, "exclusive")
                    with self.assertRaises(LockTimeoutError):
                        with other.shared():
                            pass
                self.assertEqual(self.ws.lock.mode, "shared")
                with self.assertRaises(LockTimeoutError):
                    with other.exclusive():
                        pass
        with other.exclusive():
            pass

    def test_mount_paths_with_drive_letters_backslashes_spaces_and_unicode(self):
        inside = self.make_slice("team notes \u4e2d\u6587", {"a": card_text("A", "Inside capybara.")})
        outside = self.tmp / "external notes \u4e2d\u6587.slice"
        outside.mkdir()
        (outside / "b.md").write_text(card_text("B", "Outside wombat."), encoding="utf-8")
        self.assertTrue(outside.drive)
        self.assertIn("\\", str(outside))
        self.ws.mount(str(inside), alias="@inside")
        self.ws.mount(str(outside), alias="@outside")
        mounts_file = self.root / "mounts.toml"
        data = tomllib.loads(mounts_file.read_text(encoding="utf-8"))
        paths = {m["alias"]: m["path"] for m in data["mounts"]}
        self.assertEqual(paths["@inside"], "./slices/team notes \u4e2d\u6587.slice")
        self.assertEqual(paths["@outside"], str(outside))
        self.ws.close()
        self.ws = Workspace(self.root)
        self.assertEqual(self.addresses(self.ws.search("capybara")), ["@inside/a"])
        self.assertEqual(self.addresses(self.ws.search("wombat")), ["@outside/b"])
        # A hand-edited TOML literal string accepts native backslashes unchanged.
        text = mounts_file.read_text(encoding="utf-8")
        text += f"\n[[mounts]]\npath = '{inside}'\nalias = '@literal'\nprecedence = 5\n"
        mounts_file.write_text(text, encoding="utf-8")
        self.assertEqual(self.ws.read("@literal/a")["summary"], "Inside capybara.")

    def test_open_overlay_blocks_replace_and_delete_without_data_loss(self):
        self.ws.write("held", summary="Original.")
        file = self.overlay_file("held")
        original = file.read_bytes()
        with self.held_by_process(file):
            for op in ("replace", "delete"):
                with self.subTest(op=op), self.assertRaises(PermissionError):
                    self.ws.write("held", op=op, summary="Replacement.")
                self.assertEqual(file.read_bytes(), original)
                self.assertEqual(list(file.parent.glob(".held.md.*.tmp")), [])
        self.ws.write("held", op="replace", summary="Replacement.")
        self.assertEqual(self.ws.read("held")["summary"], "Replacement.")
        self.ws.write("held", op="delete")
        self.assertFalse(file.exists())

    def test_open_overlay_keeps_apply_journal_until_recovery(self):
        for op in ("replace", "delete"):
            with self.subTest(op=op):
                self.ws.write(op, summary="Original.")
                self.ws.write(op, op=op, summary="Recovered.", stage=True)
                file = self.overlay_file(op)
                original = file.read_bytes()
                with self.held_by_process(file):
                    with self.assertRaises(PermissionError):
                        self.ws.apply()
                    self.assertEqual(file.read_bytes(), original)
                    self.assertTrue(self.ws.staging.journal_path.exists())
                    self.assertTrue(self.ws.staging.manifest_path.exists())
                    if op == "replace":
                        self.assertTrue(self.ws.staging.file(op).exists())
                self.ws.close()
                self.ws = Workspace(self.root)
                self.ws.search("recovered")
                self.assertTrue(self.ws.last_recovery["recovered"])
                self.assertFalse(self.ws.staging.journal_path.exists())
                self.assertEqual(self.ws.diff()["items"], [])
                if op == "replace":
                    self.assertEqual(self.ws.read(op)["summary"], "Recovered.")
                else:
                    self.assertFalse(file.exists())

    def test_pack_with_open_source_and_existing_open_output(self):
        self.ws.write("held", summary="Exportable capybara.")
        with self.held_by_process(self.overlay_file("held")):
            for name in ("held.slice", "held.zip", "held.tar.gz"):
                with self.subTest(name=name):
                    output = self.tmp / name
                    self.assertTrue(self.ws.pack(output)["validation"]["ok"])
                    held = output / "held.md" if output.is_dir() else output
                    original = held.read_bytes()
                    with self.held_by_process(held):
                        with self.assertRaises(AlreadyExistsError):
                            self.ws.pack(output)
                        self.assertEqual(held.read_bytes(), original)
                    self.assertEqual(list(output.parent.glob(f".{name}.*")), [])


class LockTests(WorkspaceTestCase):
    def test_exclusive_lock_blocks_other_holders(self):
        other = WorkspaceLock(self.root / ".cache/workspace.lock", timeout=0.2)
        with other.exclusive():
            self.ws.lock.timeout = 0.2
            with self.assertRaises(LockTimeoutError):
                self.ws.search("anything")
        other.close()

    @unittest.skipIf(sys.platform == "win32", "msvcrt adapter has no shared mode; readers serialize on Windows")
    def test_shared_locks_coexist_and_reenter(self):
        self.ws.search("warm up")  # first query builds the index (needs LOCK_EX)
        other = WorkspaceLock(self.root / ".cache/workspace.lock", timeout=0.2)
        self.ws.lock.timeout = 0.2
        with other.shared():
            self.assertEqual(self.ws.search("anything")["total_matches"], 0)
            with self.ws.lock.shared():
                with self.ws.lock.shared():
                    pass
        other.close()


if __name__ == "__main__":
    unittest.main()
