"""``bake()``: a new version of a mounted slice, with overlay cards baked in, mounted in the old one's place."""

from __future__ import annotations

import json

from mindslice import AlreadyExistsError, BakeConflictError, MountError, NotFoundError, UnresolvedExportDependencyError
from mindslice.card import parse_card
from mindslice.config import load_slice_manifest

from .helpers import WorkspaceTestCase, card_text


def snapshot(root):
    return {str(f.relative_to(root)): f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()}
from .test_interfaces import run_cli


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
        with self.assertRaises(NotFoundError):
            self.ws.bake("@nope")

    def test_always_loaded_card_keeps_loading_from_the_slice(self):
        self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        self.ws.bake("@persona", prefix="prefs/")
        self.assertEqual([c["address"] for c in self.ws.boot()["cards"]], ["@persona/prefs/lang"])

    def test_cli(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=False)
        code, out, _ = run_cli("-w", str(self.root), "bake", "@persona", "--dry-run")
        self.assertEqual((code, json.loads(out)["created"]), (0, ["@persona/emoji"]))
        out_dir = self.tmp / "elsewhere" / "persona-next.slice"
        code, out, _ = run_cli("-w", str(self.root), "bake", "@persona", "--output", str(out_dir))
        res = json.loads(out)
        self.assertEqual((res["output"], res["retired_overlay_cards"]), (str(out_dir), ["@overlay/emoji"]))
        self.assertEqual(self.baked, out_dir)
