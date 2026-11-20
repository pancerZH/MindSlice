"""``bake()`` creates or updates a slice, mounts it, and retires overlay copies."""

from __future__ import annotations

import json

from mindslice import AlreadyExistsError, BakeConflictError, MountError, NotFoundError, UnresolvedExportDependencyError
from mindslice.errors import InvalidArgumentsError
from mindslice.model.card import parse_card
from mindslice.storage.config import load_slice_manifest
from mindslice.storage.history import file_sha

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
        self.assertIn("drop its `extends` link", ctx.exception.details["conflicts"][0]["fix"])
        steps = ctx.exception.details["next_steps"]
        self.assertTrue(steps[0].startswith("@overlay/tone: "), steps)
        self.assertIn("`mindslice bake @persona`", steps[-1])
        self.assertEqual((self.persona / "tone.md").read_text(), before)
        self.assertEqual(self.baked, self.persona)
        self.assertFalse((self.root / "slices" / "persona-2.slice").exists())
        self.assertTrue(self.overlay_file("tone").exists())

    def test_staged_cards_block_the_bake(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], stage=True)
        self.ws.write("emoji2", summary="Also stickers.", extends=["@persona/tone"], stage=False)
        self.ws.apply()
        self.ws.write("emoji", op="append", content="- Sparingly.", stage=True)
        with self.assertRaises(BakeConflictError) as ctx:
            self.ws.bake("@persona")
        self.assertIn("`mindslice apply emoji`", ctx.exception.details["conflicts"][0]["fix"])
        self.assertIn("`mindslice discard emoji`", ctx.exception.details["next_steps"][0])

    def test_prefix_dependencies_and_rewritten_references(self):
        self.ws.write("persona/style", summary="Uses the [[persona/words]] list; see [[@kb/api/auth]].",
                      extends=["@persona/tone"], stage=False)
        self.ws.write("persona/words", summary="Favourite words.", stage=False)
        self.ws.write("diary", summary="Talked about [[persona/style]] today.", stage=False)
        with self.assertRaises(UnresolvedExportDependencyError) as ctx:
            self.ws.bake("@persona", prefix="persona/style")
        self.assertIn("`--include-deps`", ctx.exception.details["next_steps"][0])  # the fix the next line takes
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

    def test_tags_and_prefix_select_overlay_cards_but_never_the_overview(self):
        self.ws.write("style/emoji", summary="Emoji are fine.", tags=["fun"])
        self.ws.write("stylebook", summary="Unrelated house style.", tags=["fun"])
        self.put_overlay("overview", card_text("Overview", "The overlay's overview.", tags=["fun"]))

        def cards(alias="@persona", **options):
            return self.ws.bake(alias, dry_run=True, **options)["cards"]

        self.assertEqual(cards(tags="fun"), ["style/emoji", "stylebook"])  # one tag may be a plain string
        for prefix in ("style/", "./style/", "/style/"):
            with self.subTest(prefix=prefix):
                self.assertEqual(cards(prefix=prefix), ["style/emoji"])
        self.assertEqual(cards("@new", prefix="", tags=["fun"]), ["style/emoji", "stylebook"])

    def test_update_rewrites_references_and_keeps_declared_dependencies(self):
        self.ws.write("style/emoji", summary="Emoji rules.", aliases=["emoji rules"], extends=["@persona/glossary"])
        self.ws.write("api/auth", summary="The persona's view of auth.", content="- See [[@kb/api/auth]].",
                      extends=["@persona/tone"])
        self.ws.write("tone", summary="Mira is warm.", content="- Follow [[emoji rules]].",
                      supersedes=["@persona/tone", "@persona/glossary"])
        res = self.ws.bake("@persona")
        self.assertEqual(res["dependencies_added"], ["@kb"])
        self.assertEqual(res["validation"], {"ok": True, "errors": [], "warnings": 0})
        self.assertIn("[[style/emoji]]", (self.baked / "tone.md").read_text())  # the alias becomes the path
        self.assertIn("[[@kb/api/auth]]", (self.baked / "api/auth.md").read_text())  # same path, another slice
        self.assertEqual(self.slice_card("tone").supersedes, ["glossary"])  # only the self-reference goes
        self.ws.write("api/tokens", summary="Token notes.", content="- See [[@kb/api/auth]].", extends=["@persona/tone"])
        self.assertEqual(self.ws.bake("@persona")["dependencies_added"], [])
        self.assertEqual(load_slice_manifest(self.baked).dependencies, ["@kb"])

    def test_bake_event_records_each_card_and_the_changes_it_carries(self):
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"])
        self.ws.write("stickers", summary="And stickers.", extends=["@persona/tone"])
        self.put_overlay("gifs", card_text("Gifs", "Written by hand.", extends=["@persona/tone"]))  # no recorded change
        stickers = self.overlay_file("stickers")
        stickers.write_text(stickers.read_text() + "\n- Edited by hand.\n", encoding="utf-8")  # past its recorded change
        emoji = next(e["change_id"] for e in self.ws.history.events() if e.get("address") == "@overlay/emoji")
        res = self.ws.bake("@persona")
        baked = self.ws.history.events()[-1]
        self.assertEqual({k: baked.get(k) for k in ("event", "event_id", "alias", "path", "output", "previous_path",
                                                    "version", "dropped")},
                         {"event": "baked", "event_id": res["history_event_id"], "alias": "@persona",
                          "path": str(self.baked), "output": res["output"], "previous_path": str(self.persona),
                          "version": "1.0.1", "dropped": None})
        self.assertEqual([(c["source"], c["target"], c["change_ids"]) for c in baked["cards"]],
                         [("@overlay/emoji", "@persona/emoji", [emoji]), ("@overlay/gifs", "@persona/gifs", []),
                          ("@overlay/stickers", "@persona/stickers", [])])
        self.assertEqual(baked["cards"][0]["after_sha256"], file_sha(self.baked / "emoji.md"))
        self.assertEqual((baked["change_ids"], baked["retired_overlay_cards"]), ([emoji], res["retired_overlay_cards"]))

    def test_update_of_a_folder_without_manifest_keeps_its_name_and_leaves_internal_files_behind(self):
        root = self.root / "slices" / "team-notes.slice"
        files = {"sub/only.md": card_text("Only", "Alone in sub."), "keep/a.md": card_text("A", "Dropped."),
                 "keep/b.md": card_text("B", "Stays."), ".git/HEAD": "ref", ".history/changes.jsonl": "{}",
                 ".bake-plan.json": "{}"}
        for path, text in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding="utf-8")
        self.ws.mount(root, alias="@team", precedence=20)
        self.ws.write("keep/c", summary="New. See [[nowhere]].", extends=["@team/keep/b"])
        res = self.ws.bake("@team", drop=["sub/only", "keep/a"], description="Team\n  notes")
        new = self.root / "slices" / "team-notes-2.slice"
        self.assertEqual(res["path"], str(new))
        self.assertEqual(sorted(f.relative_to(new).as_posix() for f in new.rglob("*") if f.is_file()),
                         ["keep/b.md", "keep/c.md", "slice.toml"])
        self.assertFalse((new / "sub").exists())  # the folder the drop emptied
        manifest = load_slice_manifest(new)
        self.assertEqual((manifest.name, manifest.description), ("team-notes", "Team notes"))
        self.assertIn("[[nowhere]]", (new / "keep/c.md").read_text())  # a dangling link is copied as written

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
        code, out, _ = run_cli("-w", str(self.root), "--json", "bake", "@persona", "--dry-run")
        self.assertEqual((code, json.loads(out)["created"]), (0, ["@persona/emoji"]))
        out_dir = self.tmp / "elsewhere" / "persona-next.slice"
        code, out, _ = run_cli("-w", str(self.root), "--json", "bake", "@persona", "--output", str(out_dir))
        res = json.loads(out)
        self.assertEqual((res["output"], res["retired_overlay_cards"]), (str(out_dir), ["@overlay/emoji"]))
        self.assertEqual(self.baked, out_dir)


class BakeDropTests(WorkspaceTestCase):
    """``bake(alias, drop=...)`` is the one way to take a card out of a slice: the next version leaves it out."""

    def setUp(self):
        super().setUp()
        self.kb = self.mount_slice("kb", {
            "old": card_text("Old", "The old fact."),
            "new": card_text("New", "The new fact.", supersedes=["old"]),
            "notes": card_text("Notes", "Pointers.", ["See [[old]]."]),
            "keep": card_text("Keep", "A card that stays."),
        }, "@kb", 50, "baseline")
        self.mount_slice("other", {"ref": card_text("Ref", "Links across.", ["See [[@kb/old]]."])}, "@other", 40, "baseline")
        self.original = snapshot(self.kb)

    @property
    def mounted(self):
        return self.ws._reload_table().get("@kb").root

    def test_drop_leaves_the_card_out_and_clears_the_supersedes_that_pointed_at_it(self):
        res = self.ws.bake("@kb", drop=["old"])  # nothing in overlay: a drop-only bake
        self.assertEqual((res["dropped"], res["cleared_supersedes"], res["cards"]), (["@kb/old"], ["@kb/new"], []))
        self.assertEqual(res["dangling_links"], ["@kb/notes", "@other/ref"])
        self.assertFalse((self.mounted / "old.md").exists())
        self.assertEqual(parse_card((self.mounted / "new.md").read_text()).supersedes, [])
        self.assertEqual(snapshot(self.kb), self.original)  # the old folder still holds it
        self.assertTrue(res["validation"]["ok"])
        with self.assertRaises(NotFoundError):
            self.ws.read("@kb/old")
        self.assertEqual(self.ws.read("@kb/new")["address"], "@kb/new")
        baked = [e for e in self.ws.history.events() if e["event"] == "baked"][-1]
        self.assertEqual(baked["dropped"], ["@kb/old"])

    def test_an_overlay_replacement_bakes_in_while_the_stub_it_forwards_from_is_dropped(self):
        self.ws.write("v2/keep", summary="A newer card.", content="- Replaces [[@kb/keep]].",
                      supersedes=["@kb/keep"], stage=False)
        res = self.ws.bake("@kb", drop=["keep"])
        self.assertEqual((res["cards"], res["dropped"], res["cleared_supersedes"]), (["v2/keep"], ["@kb/keep"], []))
        self.assertEqual(res["dangling_links"], ["@kb/v2/keep"])  # named where the card lives after the bake
        self.assertFalse((self.mounted / "keep.md").exists())
        self.assertEqual(parse_card((self.mounted / "v2" / "keep.md").read_text()).supersedes, [])
        self.assertFalse(self.overlay_file("v2/keep").exists())
        self.assertTrue(res["validation"]["ok"])

    def test_lineage_that_would_dangle_blocks_the_bake(self):
        self.ws.write("ext", summary="Refines keep.", extends=["@kb/keep"], stage=False)
        with self.assertRaises(BakeConflictError) as cm:
            self.ws.bake("@kb", drop=["keep"])
        self.assertEqual([c["address"] for c in cm.exception.details["conflicts"]], ["@overlay/ext"])
        self.ws.write("ext", op="delete")
        # A replacement left out of this bake would supersede a card that no longer exists.
        self.ws.write("v2/keep", summary="A newer card.", supersedes=["@kb/keep"], stage=False)
        with self.assertRaises(BakeConflictError) as cm:
            self.ws.bake("@kb", prefix="elsewhere/", drop=["keep"])
        self.assertEqual([c["address"] for c in cm.exception.details["conflicts"]], ["@overlay/v2/keep"])
        # An overlay card at the same path already replaces the card: nothing to drop.
        self.ws.write("notes", summary="Rewritten pointers.", stage=False)
        with self.assertRaises(BakeConflictError) as cm:
            self.ws.bake("@kb", drop=["notes"])
        self.assertEqual([c["address"] for c in cm.exception.details["conflicts"]], ["@kb/notes"])
        self.assertEqual(self.mounted, self.kb)

    def test_arguments_and_dry_run(self):
        with self.assertRaises(NotFoundError):
            self.ws.bake("@kb", drop=["missing"])
        with self.assertRaisesRegex(InvalidArgumentsError, "names @other"):
            self.ws.bake("@kb", drop=["@other/ref"])
        self.ws.write("fresh/card", summary="New.")
        with self.assertRaisesRegex(InvalidArgumentsError, "not mounted"):
            self.ws.bake("@fresh", prefix="fresh/", drop=["x"])
        with self.assertRaises(InvalidArgumentsError):
            self.ws.bake(drop=["old"])
        res = self.ws.bake("@kb", drop=["@kb/old.md"], dry_run=True)
        self.assertEqual(res["dropped"], ["@kb/old"])
        self.assertEqual((self.mounted, snapshot(self.kb)), (self.kb, self.original))

    def test_every_dropped_card_is_checked(self):
        (self.kb / "b.md").write_text(card_text("B", "Refines old.", extends=["old"]), encoding="utf-8")
        res = self.ws.bake("@kb", drop=["old", "b"], dry_run=True)  # b refines old, but goes too
        self.assertEqual(res["dropped"], ["@kb/old", "@kb/b"])
        other = self.ws.table().get("@other").root
        (other / "ext.md").write_text(card_text("Ext", "Refines old.", extends=["@kb/old"]), encoding="utf-8")
        self.ws.write("notes", summary="Rewritten pointers.")
        with self.assertRaises(BakeConflictError) as cm:
            self.ws.bake("@kb", drop=["notes", "old", "b"], dry_run=True)
        conflicts = cm.exception.details["conflicts"]
        self.assertEqual([c["address"] for c in conflicts], ["@kb/notes", "@other/ext"])
        self.assertTrue(conflicts[1]["reason"].startswith("extends @kb/old"), conflicts[1])

    def test_clearing_supersedes_keeps_the_entries_of_cards_that_stay(self):
        (self.kb / "new.md").write_text(card_text("New", "The new fact.", supersedes=["old", "keep"]), encoding="utf-8")
        self.ws.bake("@kb", drop=["old"])
        self.assertEqual(parse_card((self.mounted / "new.md").read_text()).supersedes, ["keep"])

    def test_deleting_a_slice_card_points_the_agent_at_the_user_run_drop(self):
        res = self.ws.write("old", op="delete")
        self.assertEqual(res["warnings"], ["@overlay/old does not exist; @kb/old is in a read-only slice, so only the "
                                           "user can remove it, with `mindslice bake @kb --drop old`: tell the user"])
        self.assertTrue((self.kb / "old.md").exists())

    def test_cli(self):
        code, _, err = run_cli("-w", str(self.root), "bake", "--drop", "old")
        self.assertNotEqual(code, 0)
        self.assertIn("--drop needs a target alias", err)
        code, out, _ = run_cli("-w", str(self.root), "bake", "@kb", "--drop", "old")
        self.assertEqual(code, 0)
        self.assertIn("dropped: @kb/old", out)
        self.assertIn("links left dangling", out)


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
        code, _, err = run_cli("-w", str(self.root), "--json", "bake", "@python", "--tag", "python")
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

    def test_new_slice_manifest_nested_paths_and_an_empty_output_folder(self):
        self.ws.write("python/lint/strict", summary="Strict lint rules.")
        output = self.tmp / "out/deep/python.slice"
        self.ws.bake("@python", output, prefix="python/")
        manifest = load_slice_manifest(output)
        self.assertEqual((manifest.name, manifest.alias, manifest.version, manifest.description),
                         ("python", "@python", "0.1.0", "Baked from @overlay (prefix=python/)"))
        self.assertTrue((output / "python/lint/strict.md").is_file())
        empty = self.tmp / "empty.slice"
        empty.mkdir()
        self.assertEqual(self.ws.bake("@other", empty, prefix="other")["path"], str(empty))

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
        code, out, err = run_cli("-w", str(self.root), "--json", "bake", "@python", "--prefix", "python/", "--output", str(output),
                                "--name", "Python notes", "--description", "Team Python notes", "--slice-version", "2.0.0")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["output"], str(output))
        self.assertEqual(self.ws._reload_table().get("@python").root, output)
        manifest = load_slice_manifest(output)
        self.assertEqual((manifest.name, manifest.description, manifest.version),
                         ("Python notes", "Team Python notes", "2.0.0"))

    def test_pack_is_no_longer_a_public_operation(self):
        from mindslice.interfaces.cli import build_parser

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
        with patch("mindslice.baking.bake.dump_slice_manifest", side_effect=OSError("write failed")):
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
        from mindslice.baking.archive import write_archive

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
        with patch("mindslice.baking.bake.write_archive", side_effect=OSError("archive failed")):
            with self.assertRaisesRegex(OSError, "archive failed"):
                self.ws.bake("@base", self.tmp / "base.zip")
        self.assertEqual(self.ws.table().get("@base").root, old)
        self.assertTrue(self.overlay_file("extra").exists())
        self.assertFalse((self.root / "slices/base-2.slice").exists())
