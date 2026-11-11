"""``bake()`` creates or updates a slice, mounts it, and retires overlay copies."""

from __future__ import annotations

import json

from mindslice import AlreadyExistsError, BakeConflictError, MountError, NotFoundError, UnresolvedExportDependencyError
from mindslice.errors import InvalidArgumentsError
from mindslice.card import parse_card
from mindslice.config import load_slice_manifest

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


def snapshot(root):
    return {str(f.relative_to(root)): f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()}


class BakeTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.persona = self.mount_slice("persona", {
            "tone": card_text("Tone", "Mira is concise.", ["Answer briefly."]),
            "glossary": card_text("Glossary", "Terms the team uses."),
        }, "@persona", 10, "baseline")
        self.ws.mount(self.make_slice("kb", {"api/auth": card_text("Auth", "Tokens last 15 minutes.")}, alias="@kb"),
                      alias="@kb", precedence=50)

        self.original = snapshot(self.persona)

    @property
    def baked(self):
        """The folder currently mounted as @persona (read from mounts.toml: the CLI runs as another Workspace)."""
        return self.ws._reload_table().get("@persona").root

    def slice_card(self, path: str):
        return parse_card((self.baked / f"{path}.md").read_text())

    def test_new_version_takes_over_the_mount_and_the_old_folder_is_untouched(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=False)
        res = self.ws.bake("@persona")
        new = self.root / "slices" / "persona-2.slice"  # slices/persona.slice is the old folder
        self.assertEqual((res["output"], res["previous_path"]), (str(new), str(self.persona)))
        self.assertEqual(self.baked, new)
        mount = self.ws.table().get("@persona")
        self.assertEqual((mount.path, mount.precedence, mount.role), ("./slices/persona-2.slice", 10, "baseline"))
        self.assertEqual(snapshot(self.persona), self.original)
        self.assertEqual(sorted(p for p in snapshot(new) if p != "slice.toml"), ["emoji.md", "glossary.md", "tone.md"])
        self.assertEqual((res["version"], load_slice_manifest(new).version), ("1.0.1", "1.0.1"))
        self.assertEqual([m["alias"] for m in self.ws.manifest()["mounts"]], ["@overlay", "@kb", "@persona"])
        # A second bake makes the next version, next to the first.
        self.ws.write("stickers", summary="And stickers.", extends=["@persona/tone"], stage=False)
        self.assertEqual(self.ws.bake("@persona")["output"], str(self.root / "slices" / "persona-3.slice"))
        self.assertTrue((new / "emoji.md").exists() and not (new / "stickers.md").exists())

    def test_default_selection_moves_the_cards_that_build_on_the_slice(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=False)
        self.ws.write("v2/glossary", summary="New terms.", supersedes=["@persona/glossary"], stage=False)
        self.ws.write("notes/unrelated", summary="Nothing to do with the persona.")
        res = self.ws.bake("@persona")
        self.assertEqual(res["created"], ["@persona/emoji", "@persona/v2/glossary"])
        self.assertEqual(res["retired_overlay_cards"], ["@overlay/emoji", "@overlay/v2/glossary"])
        self.assertTrue(res["validation"]["ok"], res["validation"])
        self.assertEqual(self.slice_card("emoji").extends, ["tone"])  # @persona/tone -> slice-relative
        self.assertEqual(self.slice_card("v2/glossary").supersedes, ["glossary"])
        self.assertFalse(self.overlay_file("emoji").exists())
        self.assertTrue(self.overlay_file("notes/unrelated").exists())
        read = self.ws.read("@persona/tone")
        self.assertEqual([e["address"] for e in read["extensions"]], ["@persona/emoji"])
        self.assertEqual(self.ws.read("@persona/glossary")["address"], "@persona/v2/glossary")

    def test_same_path_replacement_overwrites_and_drops_the_self_reference(self):
        self.ws.write("tone", summary="Mira is warm.", content="- Answer warmly.", supersedes=["@persona/tone"], stage=False)
        res = self.ws.bake("@persona")
        self.assertEqual((res["created"], res["replaced"]), ([], ["@persona/tone"]))
        card = self.slice_card("tone")
        self.assertEqual((card.summary, card.supersedes), ("Mira is warm.", []))
        self.assertEqual(self.ws.read("tone")["address"], "@persona/tone")
        self.assertTrue(res["validation"]["ok"], res["validation"])

    def test_same_path_extension_must_be_merged_first(self):
        self.ws.write("tone", summary="Also: emoji.", extends=["@persona/tone"], stage=False)
        before = (self.persona / "tone.md").read_text()
        with self.assertRaises(BakeConflictError) as ctx:
            self.ws.bake("@persona")
        self.assertIn("merge the two", ctx.exception.details["conflicts"][0]["reason"])
        self.assertEqual((self.persona / "tone.md").read_text(), before)
        self.assertEqual(self.baked, self.persona)
        self.assertFalse((self.root / "slices" / "persona-2.slice").exists())
        self.assertTrue(self.overlay_file("tone").exists())

    def test_staged_cards_block_the_bake(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=True)
        self.ws.write("emoji2", summary="Also stickers.", extends=["@persona/tone"], stage=False)
        self.ws.apply()
        self.ws.write("emoji", op="append", content="- Sparingly.", stage=True)
        with self.assertRaises(BakeConflictError):
            self.ws.bake("@persona")

    def test_prefix_dependencies_and_rewritten_references(self):
        self.ws.write("persona/style", summary="Uses the [[persona/words]] list; see [[@kb/api/auth]].",
                      extends=["@persona/tone"], stage=False)
        self.ws.write("persona/words", summary="Favourite words.", stage=False)
        self.ws.write("diary", summary="Talked about [[persona/style]] today.", stage=False)
        with self.assertRaises(UnresolvedExportDependencyError):
            self.ws.bake("@persona", prefix="persona/style")
        res = self.ws.bake("@persona", prefix="persona/style", include_deps=True)
        self.assertEqual(res["included_dependencies"], ["persona/words"])
        self.assertEqual(res["dependencies_added"], ["@kb"])
        self.assertEqual(load_slice_manifest(self.baked).dependencies, ["@kb"])
        body = (self.baked / "persona/style.md").read_text()
        self.assertIn("[[persona/words]]", body)
        self.assertIn("[[@kb/api/auth]]", body)
        self.assertIn("[[@persona/persona/style]]", self.overlay_file("diary").read_text())
        self.assertEqual(res["rebased_references"][0]["to"], "@persona/persona/style")

    def test_dry_run_and_errors(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=False)
        res = self.ws.bake("@persona", dry_run=True)
        self.assertEqual((res["created"], res["output"]), (["@persona/emoji"], str(self.root / "slices" / "persona-2.slice")))
        self.assertFalse((self.root / "slices" / "persona-2.slice").exists())
        self.assertEqual(self.baked, self.persona)
        self.assertTrue(self.overlay_file("emoji").exists())
        with self.assertRaises(MountError):
            self.ws.bake("@persona", output_path=self.persona / "inside.slice")
        (self.tmp / "taken").mkdir()
        (self.tmp / "taken" / "x.md").write_text("x")
        with self.assertRaises(AlreadyExistsError):
            self.ws.bake("@persona", output_path=self.tmp / "taken")
        with self.assertRaises(NotFoundError):
            self.ws.bake("@kb")  # nothing builds on @kb
        with self.assertRaisesRegex(InvalidArgumentsError, "--prefix is required"):
            self.ws.bake("@nope")

    def test_always_loaded_card_keeps_loading_from_the_slice(self):
        self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        self.ws.bake("@persona", prefix="prefs/")
        self.assertEqual([c["address"] for c in self.ws.boot()["cards"]], ["@persona/prefs/lang"])

    def test_linked_baseline_file_is_not_modified_by_replacement(self):
        target = self.tmp / "shared.md"
        target.write_text(card_text("Shared", "Original external file."))
        linked = self.persona / "shared.md"
        try:
            linked.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.ws.write("shared", summary="Replacement note.")
        self.ws.bake("@persona")
        self.assertEqual(self.slice_card("shared").summary, "Replacement note.")
        self.assertIn("Original external file.", target.read_text())
        self.assertTrue(linked.is_symlink())


    def test_cli(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=False)
        code, out, _ = run_cli("-w", str(self.root), "bake", "@persona", "--dry-run")
        self.assertEqual((code, json.loads(out)["created"]), (0, ["@persona/emoji"]))
        out_dir = self.tmp / "elsewhere" / "persona-next.slice"
        code, out, _ = run_cli("-w", str(self.root), "bake", "@persona", "--output", str(out_dir))
        res = json.loads(out)
        self.assertEqual((res["output"], res["retired_overlay_cards"]), (str(out_dir), ["@overlay/emoji"]))
        self.assertEqual(self.baked, out_dir)


class BakeCreationTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write("python/style", summary="Use [[python/tools]].", tags=["python"])
        self.ws.write("python/tools", summary="Use ruff.", tags=["python", "tools"])
        self.ws.write("other", summary="Unrelated note.")

    def test_new_alias_requires_prefix_even_with_tags_output_or_dry_run(self):
        for options in ({}, {"tags": ["python"]}, {"output_path": self.tmp / "new.slice"}, {"dry_run": True}):
            with self.subTest(options=options), self.assertRaisesRegex(InvalidArgumentsError, "--prefix is required"):
                self.ws.bake("@python", **options)
        self.assertIsNone(self.ws.table().get("@python"))
        self.assertTrue(self.overlay_file("python/style").exists())
        code, _, err = run_cli("-w", str(self.root), "bake", "@python", "--tag", "python")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["code"], "invalid_arguments")
        self.assertIn("--prefix", json.loads(err)["message"])

    def test_new_slice_is_mounted_and_overlay_references_are_rebased(self):
        self.ws.write("diary", summary="Read [[python/style]].")
        res = self.ws.bake("python", prefix="python/")
        output = self.root / "slices/python.slice"
        self.assertEqual((res["alias"], res["output"], res["previous_path"]), ("@python", str(output), None))
        self.assertEqual(res["cards"], ["python/style", "python/tools"])
        self.assertEqual(res["retired_overlay_cards"], ["@overlay/python/style", "@overlay/python/tools"])
        self.assertTrue(res["validation"]["ok"])
        self.assertEqual(self.ws.read("@python/python/style")["links"],
                         [{"ref": "python/tools", "address": "@python/python/tools"}])
        self.assertIn("[[@python/python/style]]", self.overlay_file("diary").read_text())
        self.assertTrue(self.overlay_file("other").exists())
        mount = self.ws.table().get("@python")
        self.assertEqual((mount.root, mount.precedence, mount.role), (output, 50, "baseline"))
        manifest = load_slice_manifest(output)
        self.assertEqual((manifest.alias, manifest.version), ("@python", "0.1.0"))
        # The newly created slice uses the same update path as any other mount.
        self.ws.write("python/tools", summary="Use ruff and mypy.")
        updated = self.ws.bake("@python")
        self.assertEqual(updated["version"], "0.1.1")
        self.assertEqual(updated["replaced"], ["@python/python/tools"])
        self.assertEqual(self.ws.read("@python/python/tools")["summary"], "Use ruff and mypy.")
        self.assertIn("Use ruff.", (output / "python/tools.md").read_text())

    def test_empty_prefix_explicitly_selects_all_cards(self):
        res = self.ws.bake("@all", prefix="")
        self.assertEqual(res["cards"], ["other", "python/style", "python/tools"])

    def test_prefix_and_tags_intersect(self):
        res = self.ws.bake("@tools", prefix="python/", tags=["tools"])
        self.assertEqual(res["cards"], ["python/tools"])
        self.assertTrue(self.overlay_file("python/style").exists())
        self.assertIn("[[@tools/python/tools]]", self.overlay_file("python/style").read_text())

    def test_new_slice_dry_run_does_not_write_or_mount(self):
        output = self.tmp / "new-parent/python.slice"
        before = snapshot(self.root / "overlay")
        mounts = (self.root / "mounts.toml").read_bytes()
        res = self.ws.bake("@python", output, prefix="python/", dry_run=True)
        self.assertEqual(res["created"], ["@python/python/style", "@python/python/tools"])
        self.assertEqual(snapshot(self.root / "overlay"), before)
        self.assertEqual((self.root / "mounts.toml").read_bytes(), mounts)
        self.assertFalse(output.parent.exists())

    def test_staged_new_slice_cards_are_rejected(self):
        self.ws.write("python/tools", op="append", content="- New advice.", stage=True)
        with self.assertRaises(BakeConflictError):
            self.ws.bake("@python", prefix="python/")
        self.assertIsNone(self.ws.table().get("@python"))
        self.assertFalse((self.root / "slices/python.slice").exists())
        self.assertTrue(self.overlay_file("python/tools").exists())

    def test_cli_create_custom_directory_and_metadata(self):
        output = self.tmp / "custom.slice"
        code, out, err = run_cli("-w", str(self.root), "bake", "@python", "--prefix", "python/", "--output", str(output),
                                "--name", "Python notes", "--description", "Team Python notes", "--slice-version", "2.0.0")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["output"], str(output))
        self.assertEqual(self.ws._reload_table().get("@python").root, output)
        manifest = load_slice_manifest(output)
        self.assertEqual((manifest.name, manifest.description, manifest.version),
                         ("Python notes", "Team Python notes", "2.0.0"))

    def test_pack_is_no_longer_a_public_operation(self):
        from mindslice.cli import build_parser

        self.assertFalse(hasattr(self.ws, "pack"))
        self.assertNotIn("pack", build_parser()._subparsers._group_actions[0].choices)

    def test_reserved_or_internal_destinations_are_rejected(self):
        with self.assertRaises(MountError):
            self.ws.bake("@overlay", prefix="python/")
        for output in (self.root / "staging/new.slice", self.root / ".cache/new.slice", self.root / "overlay/new.slice"):
            with self.subTest(output=output), self.assertRaises(MountError):
                self.ws.bake("@python", output, prefix="python/")
            self.assertFalse(output.exists())

    def test_build_failure_preserves_overlay_and_mounts(self):
        from unittest.mock import patch

        output = self.tmp / "new.slice"
        before = snapshot(self.root / "overlay")
        mounts = (self.root / "mounts.toml").read_bytes()
        with patch("mindslice.bake.dump_slice_manifest", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(OSError, "write failed"):
                self.ws.bake("@python", output, prefix="python/")
        self.assertFalse(output.exists())
        self.assertEqual(list(output.parent.glob(".new.slice.*")), [])
        self.assertEqual(snapshot(self.root / "overlay"), before)
        self.assertEqual((self.root / "mounts.toml").read_bytes(), mounts)


class BakeArchiveTests(WorkspaceTestCase):
    def test_archive_formats_include_the_mounted_snapshot_and_are_deterministic(self):
        import tarfile
        import zipfile
        from pathlib import Path
        from mindslice.archive import write_archive

        for suffix, fmt in (("zip", "zip"), ("tar.gz", "tar.gz"), ("tgz", "tar.gz")):
            with self.subTest(suffix=suffix):
                alias = "@" + suffix.replace(".", "-")
                self.ws.write("topic/note", summary="Portable note.")
                output = self.tmp / suffix / f"notes.{suffix}"
                result = self.ws.bake(alias, output, prefix="topic/")
                self.assertEqual(result["format"], fmt)
                self.assertEqual(result["output"], str(output))
                self.assertEqual(self.ws.table().get(alias).root, Path(result["path"]))
                self.assertEqual(self.ws.read(f"{alias}/topic/note")["summary"], "Portable note.")
                again = self.tmp / suffix / "again" / output.name
                write_archive(Path(result["path"]), again, fmt)
                self.assertEqual(output.read_bytes(), again.read_bytes())
                if fmt == "zip":
                    with zipfile.ZipFile(output) as archive:
                        note = archive.read("notes.slice/topic/note.md")
                else:
                    with tarfile.open(output) as archive:
                        note = archive.extractfile("notes.slice/topic/note.md").read()
                self.assertEqual(note, (Path(result["path"]) / "topic/note.md").read_bytes())

    def test_archive_update_switches_mount_and_preserves_old_slice(self):
        import zipfile
        from pathlib import Path

        old = self.mount_slice("base", {"note": card_text("Note", "Baseline.")}, "@base", 70, "curated")
        (old / "asset.bin").write_bytes(b"\x00\xff")
        (old / ".git").mkdir()
        (old / ".git/config").write_text("private git configuration")
        original = snapshot(old)
        self.ws.write("extra", summary="More advice.", extends=["@base/note"])
        output = self.tmp / "base.zip"
        plan = self.ws.bake("@base", output, dry_run=True)
        self.assertFalse(output.exists())
        self.assertFalse(Path(plan["path"]).exists())
        result = self.ws.bake("@base", output)
        self.assertEqual(snapshot(old), original)
        mount = self.ws.table().get("@base")
        self.assertEqual((mount.root, mount.precedence, mount.role), (Path(result["path"]), 70, "curated"))
        self.assertNotEqual(mount.root, old)
        with zipfile.ZipFile(output) as archive:
            self.assertIn("base.slice/note.md", archive.namelist())
            self.assertIn("base.slice/extra.md", archive.namelist())
            self.assertEqual(archive.read("base.slice/asset.bin"), b"\x00\xff")
            self.assertFalse(any(".git" in name for name in archive.namelist()))

    def test_archive_cannot_be_inside_the_new_mount_directory(self):
        self.ws.write("topic/note", summary="Portable note.")
        output = self.root / "slices/topic.slice/topic.zip"
        with self.assertRaises(MountError):
            self.ws.bake("@topic", output, prefix="topic/", dry_run=True)
        self.assertFalse(output.parent.exists())
        self.assertIsNone(self.ws.table().get("@topic"))

    def test_existing_archive_is_not_overwritten(self):
        output = self.tmp / "topic.zip"
        output.write_bytes(b"keep this archive")
        self.ws.write("topic/note", summary="Portable note.")
        with self.assertRaises(AlreadyExistsError):
            self.ws.bake("@topic", output, prefix="topic/")
        self.assertEqual(output.read_bytes(), b"keep this archive")
        self.assertTrue(self.overlay_file("topic/note").exists())
        self.assertIsNone(self.ws.table().get("@topic"))

    def test_failed_archive_does_not_replace_the_mount(self):
        from unittest.mock import patch

        old = self.mount_slice("base", {"note": card_text("Note", "Baseline.")}, "@base", 70, "curated")
        self.ws.write("extra", summary="More advice.", extends=["@base/note"])
        with patch("mindslice.bake.write_archive", side_effect=OSError("archive failed")):
            with self.assertRaisesRegex(OSError, "archive failed"):
                self.ws.bake("@base", self.tmp / "base.zip")
        self.assertEqual(self.ws.table().get("@base").root, old)
        self.assertTrue(self.overlay_file("extra").exists())
        self.assertFalse((self.root / "slices/base-2.slice").exists())
