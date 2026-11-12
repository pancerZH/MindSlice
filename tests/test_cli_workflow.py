"""Human CLI status, review output, startup payloads, and address shorthand."""

from __future__ import annotations

import json
import os

from mindslice import NotFoundError
from mindslice.model.card import parse_card
from mindslice.interfaces.cli import build_parser
from mindslice.interfaces.mcp_server import INSTRUCTIONS

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class StatusTests(WorkspaceTestCase):
    def test_empty_status_and_json(self):
        result = self.ws.status()
        self.assertTrue(result["clean"])
        self.assertEqual([m["alias"] for m in result["mounts"]], ["@overlay"])
        self.assertEqual(result["pending_review"]["summary"]["total"], 0)
        self.assertEqual(result["dirty_slices"], [])
        code, out, err = run_cli("-w", str(self.root), "status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("@overlay", out)
        self.assertIn("No pending review", out)
        code, out, err = run_cli("status", "-w", str(self.root), "--json", "--compact")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), result)
        self.assertEqual(out.count("\n"), 1)

    def test_status_lists_all_mounts_without_pagination(self):
        for i in range(22):
            self.mount_slice(f"s{i}", {"base": card_text("Base", "A baseline.")}, f"@s{i}", i, "curated")
        mounts = self.ws.status()["mounts"]
        self.assertEqual(len(mounts), 23)
        self.assertEqual(mounts[1], {"alias": "@s21", "path": "./slices/s21.slice", "precedence": 21,
                                    "role": "curated", "kind": "slice", "card_count": 1,
                                    "missing": False, "dirty": False})

    def test_pending_review_lists_changes_conflicts_and_approval_reasons(self):
        self.ws.write("edit", summary="Original.")
        self.ws.write("remove", summary="Remove this.")
        self.ws.write("edit", op="replace", summary="Proposed edit.", stage=True)
        self.ws.write("remove", op="delete", stage=True)
        self.ws.write("lang", summary="Reply in Chinese.", load="always")
        self.put_overlay("edit", card_text("Edit", "Concurrent edit."))
        result = self.ws.status()
        self.assertEqual(result["pending_review"]["summary"],
                         {"total": 3, "create": 1, "modify": 1, "delete": 1, "conflicts": 1})
        files = {item["address"]: item for item in result["pending_review"]["files"]}
        self.assertTrue(files["@overlay/edit"]["conflict"])
        self.assertIn("always-loaded", files["@overlay/lang"]["requires_approval"])
        self.assertNotIn("diff", files["@overlay/edit"])
        code, out, _ = run_cli("-w", str(self.root), "status")
        self.assertEqual(code, 0)
        self.assertIn("conflict:", out)
        self.assertIn("awaiting approval:", out)
        self.assertIn("delete  @overlay/remove", out)
        self.assertNotIn("Proposed edit.", out)

    def test_dirty_slices_are_grouped_by_all_referenced_mounts(self):
        self.mount_slice("a", {"base": card_text("Base", "A baseline."), "shadow": card_text("Shadow", "Old.")},
                         "@a", 50, "baseline")
        self.mount_slice("b", {"base": card_text("Base", "B baseline.")}, "@b", 40, "curated")
        self.ws.write("both", summary="Extends two slices.", extends=["@a/base", "@b/base"])
        self.ws.write("replacement", summary="New A.", supersedes=["@a/base"])
        self.ws.write("shadow", summary="Overlay shadow.")
        self.ws.write("unrelated", summary="No owner.")
        self.ws.write("unresolved", summary="Missing target.", extends=["@missing/base"])
        before = (self.root / "mounts.toml").read_bytes()
        result = self.ws.status()
        groups = {group["alias"]: group for group in result["dirty_slices"]}
        self.assertEqual(groups["@a"]["summary"], {"total": 3, "extends": 1, "supersedes": 1, "shadow": 1})
        self.assertEqual(groups["@b"]["summary"], {"total": 1, "extends": 1, "supersedes": 0, "shadow": 0})
        self.assertEqual([c["address"] for c in result["unassigned_overlay_cards"]],
                         ["@overlay/unrelated", "@overlay/unresolved"])
        self.assertTrue(result["unassigned_overlay_cards"][1]["unresolved"])
        self.assertTrue(groups["@a"]["cards"][0]["unrebased"])
        self.assertEqual((self.root / "mounts.toml").read_bytes(), before)
        self.assertTrue(self.overlay_file("both").exists())
        self.assertFalse(result["clean"])

    def test_bake_clears_dirty_state_and_unmount_preserves_files(self):
        self.mount_slice("kb", {"base": card_text("Base", "Old baseline.")}, "@kb", 40, "curated")
        self.ws.write("new", summary="New baseline.", supersedes=["@kb/base"])
        self.assertEqual(len(self.ws.status()["dirty_slices"]), 1)
        self.ws.bake("kb")
        self.assertTrue(self.ws.status()["clean"])
        root = self.ws.table().get("@kb").root
        code, out, err = run_cli("-w", str(self.root), "unmount", "kb", "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["alias"], "@kb")
        self.assertEqual([m["alias"] for m in self.ws.status()["mounts"]], ["@overlay"])
        self.assertTrue((root / "new.md").exists())
        code, _, err = run_cli("-w", str(self.root), "unmount", "overlay", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["code"], "mount_error")


class ReviewOutputTests(WorkspaceTestCase):
    def test_diff_defaults_to_patch_and_json_is_explicit(self):
        self.ws.write("draft", summary="Review this note.", stage=True)
        code, out, err = run_cli("-w", str(self.root), "diff")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, self.ws.diff()["patch"])
        code, out, err = run_cli("-w", str(self.root), "diff", "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), self.ws.diff())
        self.ws.apply()
        code, out, err = run_cli("-w", str(self.root), "diff")
        self.assertEqual((code, out, err), (0, "", ""))
        code, out, _ = run_cli("-w", str(self.root), "diff", "--scope", "overlay")
        self.assertEqual(code, 0)
        self.assertIn("+Review this note.", out)

    def test_diff_reports_conflicts_on_stderr_without_polluting_patch(self):
        self.ws.write("note", summary="Original.")
        self.ws.write("note", op="replace", summary="Staged.", stage=True)
        self.put_overlay("note", card_text("Note", "Edited outside staging."))
        code, out, err = run_cli("-w", str(self.root), "diff")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("--- "))
        self.assertIn("conflict: @overlay/note", err)
        self.assertNotIn("conflict:", out)

    def test_boot_defaults_to_startup_payload_and_cards_only_is_pure(self):
        code, out, err = run_cli("-w", str(self.root), "boot")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith(INSTRUCTIONS))
        self.assertIn("# Empty memory workspace", out)
        code, out, err = run_cli("-w", str(self.root), "boot", "--cards-only")
        self.assertEqual((code, out, err), (0, "", ""))
        self.ws.write("lang", summary="Reply in Chinese.", load="always", stage=False)
        self.ws.write("lang", op="replace", summary="Reply in French.")
        for flags in (("--cards-only",), ("--cards-only", "--json")):
            code, out, err = run_cli("-w", str(self.root), "boot", *flags)
            self.assertEqual(code, 0)
            self.assertIn("Reply in Chinese.", out)
            self.assertNotIn("Reply in French.", out)
            self.assertNotIn(INSTRUCTIONS, out)
            self.assertNotIn("# Always-loaded memory", out)
            self.assertNotIn("pending_approval", out)
            self.assertIn("awaiting approval: @overlay/lang", err)
        code, out, err = run_cli("-w", str(self.root), "boot", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIn(INSTRUCTIONS, data["instructions"])
        self.assertEqual(data["pending_approval"][0]["id"], "lang")
        self.assertIn("awaiting approval:", err)


class CLIAddressTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.mount_slice("kb", {"base": card_text("Base", "Mounted baseline.", aliases=["short"]),
                                "replacement": card_text("Replacement", "Curated replacement.", supersedes=["base"])},
                         "@kb", 50, "curated")

    def cli(self, *args):
        return run_cli("-w", str(self.root), "--json", *args)

    def test_mount_alias_arguments_normalize_during_parsing(self):
        parser = build_parser()
        for args in (("mount", "folder", "--alias", "kb"), ("unmount", "kb"), ("bake", "kb")):
            self.assertEqual(parser.parse_args(args).alias, "@kb")
        self.assertEqual(parser.parse_args(["search", "term", "--source", "kb", "--source", "@overlay"]).source,
                         ["@kb", "@overlay"])
        self.assertEqual(parser.parse_args(["write", "note", "--alias", "friendly name"]).aliases, ["friendly name"])
        root = self.make_slice("new", {"note": card_text("Note", "A new note.")})
        code, out, err = self.cli("mount", str(root), "--alias", "new")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["alias"], "@new")

    def test_shorthand_read_resolves_and_has_canonical_display(self):
        code, out, err = self.cli("read", "kb/base", "--follow", "none")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["address"], "@kb/base")
        self.assertEqual(json.loads(out)["requested"], "@kb/base")
        code, out, _ = self.cli("read", "kb/short", "--follow", "none")
        self.assertEqual((code, json.loads(out)["address"]), (0, "@kb/base"))
        code, out, _ = self.cli("read", "kb/base", "--follow", "curated")
        self.assertEqual((code, json.loads(out)["address"]), (0, "@kb/replacement"))
        # The Python API keeps its original relative-path semantics.
        with self.assertRaises(NotFoundError):
            self.ws.read("kb/base")

    def test_read_ambiguity_uses_workspace_cards_and_can_be_disambiguated(self):
        self.ws.write("kb/base", summary="Relative overlay card.")
        code, out, err = self.cli("read", "kb/base")
        self.assertEqual((code, out), (1, ""))
        error = json.loads(err)
        self.assertEqual(error["code"], "ambiguous_address")
        self.assertEqual(error["details"]["relative"], ["@overlay/kb/base"])
        self.assertIn("./kb/base", error["message"])
        code, out, _ = self.cli("read", "./kb/base")
        self.assertEqual((code, json.loads(out)["address"]), (0, "@overlay/kb/base"))
        code, out, _ = self.cli("read", "@kb/base", "--follow", "none")
        self.assertEqual((code, json.loads(out)["address"]), (0, "@kb/base"))

    def test_read_card_aliases_also_participate_in_ambiguity(self):
        self.ws.write("other", summary="Alias collision.", aliases=["kb/base"])
        code, _, err = self.cli("read", "kb/base")
        self.assertEqual((code, json.loads(err)["code"]), (1, "ambiguous_address"))

    def test_cwd_file_is_not_a_workspace_reference_conflict(self):
        folder = self.tmp / "cwd"
        (folder / "kb").mkdir(parents=True)
        (folder / "kb/base.md").write_text("Unrelated local file.")
        previous = os.getcwd()
        try:
            os.chdir(folder)
            code, out, err = self.cli("read", "kb/base", "--follow", "none")
        finally:
            os.chdir(previous)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["address"], "@kb/base")

    def test_write_lineage_arguments_normalize_but_card_aliases_and_body_do_not(self):
        code, out, err = self.cli("write", "extra", "--summary", "More advice.", "--extends", "kb/base",
                                  "--alias", "friendly name", "--content", "- See [[kb/base]].")
        self.assertEqual((code, err), (0, ""))
        parsed = parse_card(self.overlay_file("extra").read_text())
        self.assertEqual(parsed.extends, ["@kb/base"])
        self.assertEqual(parsed.aliases, ["friendly name"])
        self.assertEqual(parsed.wikilink_targets(), ["kb/base"])
        code, _, err = self.cli("write", "new", "--summary", "Latest advice.", "--supersedes", "kb/base")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(parse_card(self.overlay_file("new").read_text()).supersedes, ["@kb/base"])

    def test_ambiguous_lineage_is_rejected_before_writing_and_relative_scope_is_preserved(self):
        self.ws.write("kb/base", summary="Relative overlay baseline.")
        code, out, err = self.cli("write", "extra", "--summary", "More.", "--extends", "kb/base")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(json.loads(err)["code"], "ambiguous_address")
        self.assertFalse(self.overlay_file("extra").exists())
        code, _, err = self.cli("write", "extra", "--summary", "More.", "--extends", "./kb/base")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(parse_card(self.overlay_file("extra").read_text()).extends, ["kb/base"])
        self.assertEqual(self.ws.read("extra")["baselines"][0]["address"], "@overlay/kb/base")

    def test_lineage_relative_candidates_only_come_from_overlay(self):
        self.mount_slice("other", {"kb/base": card_text("Other", "Another mount's relative card.")},
                         "@other", 60, "baseline")
        code, _, err = self.cli("write", "extra", "--summary", "More.", "--extends", "kb/base")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(parse_card(self.overlay_file("extra").read_text()).extends, ["@kb/base"])
        code, _, err = self.cli("read", "kb/base")
        self.assertEqual((code, json.loads(err)["code"]), (1, "ambiguous_address"))

    def test_relative_read_is_preserved_when_shorthand_target_does_not_exist(self):
        self.ws.write("kb/local", summary="Only a relative target.")
        code, out, err = self.cli("read", "kb/local")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["address"], "@overlay/kb/local")
