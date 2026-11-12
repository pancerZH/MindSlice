"""Lifecycle ergonomics: write() impact reports, zero-conversion mounts, and retiring imported overlay copies."""

from __future__ import annotations

import json
import sqlite3
import unittest

from mindslice.operations.impact import MAX_AFFECTED
from mindslice.interfaces.mcp_server import MCPServer

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


def affected(result: dict) -> dict:
    return {k: v for k, v in result.items() if "affected" in k}


class WriteImpactTests(WorkspaceTestCase):
    """write() lists the cards that still link to or extend what it supersedes or deletes."""

    def setUp(self) -> None:
        super().setUp()
        self.project({"team/lead-sarah-chen": card_text("Team lead", "The team lead is Sarah Chen."),
                      "team/review": card_text("Reviews", "Reviews go to [[team/lead-sarah-chen]].")})
        self.ws.write("team/lead", summary="The lead is Sarah Chen.", content="- Lead: Sarah Chen.")
        self.ws.write("team/assignee", summary="The code review assignee is the lead.",
                      content="- See [[team/lead]].", extends=["team/lead"])
        self.ws.write("notes/standup", summary="Standup notes.",
                      content="- Ask [[team/lead]] and [[@project/team/lead-sarah-chen]].")

    def supersede(self, **kw) -> dict:
        return self.ws.write("team/lead-2026-11", summary="The lead is Jihoon Ryu.",
                             content="- Lead: Jihoon Ryu (formerly [[team/lead]]).",
                             supersedes=["team/lead", "@project/team/lead-sarah-chen"], **kw)

    def test_supersede_lists_backlinks_and_extensions(self):
        res = self.supersede()
        self.assertEqual(res["affected_backlinks"], [
            {"address": "@overlay/notes/standup", "links_to": "@overlay/team/lead"},
            {"address": "@overlay/notes/standup", "links_to": "@project/team/lead-sarah-chen"},
            {"address": "@overlay/team/assignee", "links_to": "@overlay/team/lead"},
            {"address": "@project/team/review", "links_to": "@project/team/lead-sarah-chen", "read_only": True},
        ])
        self.assertEqual(res["affected_extensions"], [{"address": "@overlay/team/assignee", "extends": "@overlay/team/lead"}])
        self.assertEqual((res["total_affected_backlinks"], res["total_affected_extensions"]), (4, 1))
        # The writer's own "formerly [[team/lead]]" link is not reported.
        self.assertNotIn("@overlay/team/lead-2026-11", [b["address"] for b in res["affected_backlinks"]])

    def test_report_is_a_function_of_the_state(self):
        first = self.supersede()
        retry = self.supersede()
        self.assertFalse(retry["changed"])
        self.assertEqual(affected(retry), affected(first))
        later = self.ws.write("team/lead-2026-11", op="append", content="- Started on 2026-11-01.")
        self.assertEqual(affected(later), affected(first))
        # Once a dependent is fixed it drops out.
        self.ws.write("team/assignee", op="replace", content="- See [[team/lead-2026-11]].", extends=["team/lead-2026-11"])
        again = self.ws.write("team/lead-2026-11", op="append", content="- Started on 2026-11-01.")
        self.assertEqual(again["total_affected_extensions"], 0)
        self.assertNotIn("@overlay/team/assignee", [b["address"] for b in again["affected_backlinks"]])

    def test_writes_that_retire_nothing_carry_no_report(self):
        res = self.ws.write("notes/standup", op="append", content="- Retro on Friday.")
        self.assertEqual(affected(res), {})

    def test_delete_reports_before_and_after_the_card_is_gone(self):
        res = self.ws.write("team/lead", op="delete")
        self.assertTrue(res["changed"])
        expected = {
            "affected_backlinks": [{"address": "@overlay/notes/standup", "links_to": "@overlay/team/lead"},
                                   {"address": "@overlay/team/assignee", "links_to": "@overlay/team/lead"}],
            "total_affected_backlinks": 2,
            "affected_extensions": [{"address": "@overlay/team/assignee", "extends": "@overlay/team/lead"}],
            "total_affected_extensions": 1,
        }
        self.assertEqual(affected(res), expected)
        retry = self.ws.write("team/lead", op="delete")  # the references now dangle; still the same cards
        self.assertFalse(retry["changed"])
        self.assertEqual(affected(retry), expected)

    def test_staged_writes_use_the_prospective_state(self):
        self.ws.write("notes/plan", summary="Plan.", content="- Owner: [[team/lead]].", stage=True)
        res = self.supersede(stage=True)
        self.assertTrue(res["staged"])
        self.assertIn({"address": "@overlay/notes/plan", "links_to": "@overlay/team/lead"}, res["affected_backlinks"])
        # A staged rewrite of a linker replaces its live links.
        self.ws.write("notes/standup", op="replace", content="- Ask the lead.", stage=True)
        res = self.supersede(stage=True)
        self.assertNotIn("@overlay/notes/standup", [b["address"] for b in res["affected_backlinks"]])
        deleted = self.ws.write("team/assignee", op="delete", stage=True)
        self.assertEqual(deleted["total_affected_backlinks"], 0)

    def test_lists_are_bounded_and_totals_exact(self):
        for i in range(MAX_AFFECTED + 3):
            self.ws.write(f"links/l{i:02d}", summary=f"Link {i}.", content="- [[team/lead]]")
        res = self.supersede()
        self.assertEqual(len(res["affected_backlinks"]), MAX_AFFECTED)
        self.assertEqual(res["total_affected_backlinks"], MAX_AFFECTED + 3 + 4)  # + the 4 from setUp

    def test_mcp_write_returns_the_report(self):
        server = MCPServer(self.ws)
        out = server._tools_call({"name": "write", "arguments": {
            "id": "team/lead", "op": "delete"}})
        payload = json.loads(out["content"][0]["text"])
        self.assertFalse(out["isError"])
        self.assertEqual(payload["total_affected_extensions"], 1)


class ZeroConversionMountTests(WorkspaceTestCase):
    """A folder of ordinary Markdown mounts as is."""

    def notes(self):
        root = self.tmp / "My Notes"
        (root / "projects").mkdir(parents=True)
        (root / "projects" / "alpha.md").write_text(
            "---\ntitle: Alpha Project\ntags: [work, alpha]\naliases:\n  - project a\n  - \"the alpha thing\"\n"
            "date: 2024-01-03\nauthor:\n  name: Dana\n---\n\n# Alpha Project\n\nAlpha ships the billing rewrite in Q3.\n\n"
            "- Owner is Dana.\n- See [[projects/beta]].\n", encoding="utf-8")
        (root / "projects" / "beta.md").write_text("# Beta\n\nBeta is the mobile app.\n\n- Uses React Native.\n",
                                                   encoding="utf-8")
        (root / "projects" / "2024-01-01 (draft) & notes.md").write_text("Notes from the kickoff, before the draft.\n",
                                                                         encoding="utf-8")
        (root / "README.md").write_text("# My Notes\n\nPersonal knowledge base.\n", encoding="utf-8")
        return root

    def test_plain_folder_mounts_without_conversion(self):
        res = self.ws.mount(self.notes())
        self.assertEqual(res["alias"], "@My-Notes")
        self.assertEqual(res["cards"], 4)
        self.assertEqual(res["formats"], {"toml": 0, "yaml": 1, "plain": 3})
        hit = self.ws.search("billing")["results"][0]
        self.assertEqual((hit["address"], hit["title"], hit["tags"]), ("@My-Notes/projects/alpha", "Alpha Project", ["work", "alpha"]))
        self.assertEqual(hit["summary"], "Alpha ships the billing rewrite in Q3.")
        self.assertEqual(self.addresses(self.ws.search("the alpha thing"))[0], "@My-Notes/projects/alpha")
        self.assertEqual(self.ws.search("date author")["results"], [])  # frontmatter keys are not body text
        card = self.ws.read("@My-Notes/projects/alpha")
        self.assertEqual(card["meta"], {"date": "2024-01-03"})
        self.assertFalse(card["body"].startswith("---"))
        self.assertEqual(card["links"], [{"ref": "projects/beta", "address": "@My-Notes/projects/beta"}])
        odd = self.ws.read("@My-Notes/projects/2024-01-01 (draft) & notes")
        self.assertEqual(odd["summary"], "Notes from the kickoff, before the draft.")
        mount = next(m for m in self.ws.manifest()["mounts"] if m["alias"] == "@My-Notes")
        self.assertEqual(mount["description"], "Personal knowledge base.")

    def test_validate_reports_formats_not_false_problems(self):
        self.ws.mount(self.notes(), alias="notes")
        report = self.ws.validate()
        self.assertEqual(report["errors"], [])
        codes = sorted((w["code"], w.get("address")) for w in report["warnings"])
        self.assertIn(("yaml_frontmatter", "@notes/projects/alpha"), codes)
        self.assertIn(("frontmatter_schema", "@notes/projects/alpha"), codes)  # the nested 'author' mapping
        self.assertIn(("missing_frontmatter", "@notes/projects/beta"), codes)
        self.assertNotIn("missing_summary", [c for c, _ in codes])

    def test_explicit_aliases_still_must_be_valid(self):
        with self.assertRaises(Exception):
            self.ws.mount(self.notes(), alias="My Notes")

    def test_new_card_ids_stay_link_safe_but_existing_files_are_writable(self):
        with self.assertRaises(Exception):
            self.ws.write("notes/kickoff (draft)", summary="x")
        self.put_overlay("notes/kickoff (draft)", "# Kickoff\n\nWe met on Monday.\n")
        res = self.ws.write("notes/kickoff (draft)", op="append", content="- Next: Friday.")
        self.assertTrue(res["changed"])
        self.assertTrue(self.ws.write("notes/kickoff (draft)", op="delete")["changed"])

    def test_yaml_card_edits_keep_or_convert_the_frontmatter(self):
        self.put_overlay("legacy", "---\ntitle: Legacy\ntags: [old]\n---\n\nA legacy note.\n")
        self.ws.write("legacy", op="append", content="- One more fact.")
        text = self.overlay_file("legacy").read_text()
        self.assertTrue(text.startswith("---\ntitle: Legacy\ntags: [old]\n---\n"), text)  # body edit: YAML kept verbatim
        self.ws.write("legacy", op="append", tags=["new"])
        text = self.overlay_file("legacy").read_text()
        self.assertTrue(text.startswith('+++\ntitle = "Legacy"\n'), text)  # field edit: written as a TOML card
        self.assertIn('tags = ["old", "new"]', text)
        self.assertIn("- One more fact.", text)
        self.assertNotIn("---", text)

    def test_parser_upgrade_reindexes_existing_caches(self):
        self.put_overlay("legacy", "---\ntitle: Legacy\n---\n\nA legacy note.\n")
        self.ws.search("legacy")
        conn = sqlite3.connect(self.root / ".cache" / "index.sqlite")
        conn.execute("UPDATE cards SET title='stale'")
        conn.execute("UPDATE meta SET value=replace(value, '|parser-', '|parser-old-') WHERE key='analyzer'")
        conn.commit()
        conn.close()
        self.assertEqual(self.ws.search("legacy")["results"][0]["title"], "Legacy")


class RetireImportedCopiesTests(WorkspaceTestCase):
    """Mounting an imported slice removes the overlay copies that would shadow it."""

    def setUp(self) -> None:
        super().setUp()
        self.project({"api/auth-flow": card_text("Auth flow", "Token expiration is 15 minutes.")})
        self.ws.write("api/jwt-ttl", summary="JWT TTL is 30 minutes.", content="- TTL 30m.",
                      supersedes=["@project/api/auth-flow"])
        self.ws.write("api/edge", summary="Edge cases.", content="- See [[api/jwt-ttl]].", extends=["api/jwt-ttl"])
        self.ws.write("notes/todo", summary="Todo.", content="- Check [[api/jwt-ttl]] and [[@overlay/api/edge]].",
                      extends=["@overlay/api/jwt-ttl"])
        # Model an imported slice containing the same cards as the overlay.
        self.imported = self.make_slice("api", {
            "api/jwt-ttl": self.overlay_file("api/jwt-ttl").read_text(),
            "api/edge": self.overlay_file("api/edge").read_text(),
        }, alias="@api", dependencies=["@project"])

    def test_mount_retires_copies_and_rebases_references(self):
        res = self.ws.mount(self.imported, alias="@api", precedence=60, role="curated")
        self.assertEqual(res["retired_overlay_cards"], ["@overlay/api/edge", "@overlay/api/jwt-ttl"])
        self.assertNotIn("shadowing_overlay_cards", res)
        self.assertFalse(self.overlay_file("api/jwt-ttl").exists())
        self.assertEqual(sorted((r["kind"], r["ref"], r["to"]) for r in res["rebased_references"]), [
            ("extends", "@overlay/api/jwt-ttl", "@api/api/jwt-ttl"),
            ("wikilink", "@overlay/api/edge", "@api/api/edge"),
            ("wikilink", "api/jwt-ttl", "@api/api/jwt-ttl"),
        ])
        # One replacement, not two competing ones.
        read = self.ws.read("@project/api/auth-flow")
        self.assertEqual((read["address"], read["status"]), ("@api/api/jwt-ttl", "active"))
        todo = self.ws.read("notes/todo")
        self.assertEqual([b["address"] for b in todo["baselines"]], ["@api/api/jwt-ttl"])
        self.assertTrue(all(l["address"] for l in todo["links"]))
        self.assertTrue(self.ws.validate()["ok"])

    def test_edited_and_staged_copies_are_kept(self):
        self.ws.write("api/edge", op="append", content="- A new edge case.")
        self.ws.write("notes/todo", op="append", content="- [[api/jwt-ttl]] again", stage=True)
        res = self.ws.mount(self.imported, alias="@api", precedence=60, role="curated")
        self.assertEqual(res["shadowing_overlay_cards"], [
            {"address": "@overlay/api/edge", "reason": "differs from @api/api/edge"},
            {"address": "@overlay/api/jwt-ttl", "reason": "referenced by staged @overlay/notes/todo"},
        ])
        self.assertNotIn("retired_overlay_cards", res)
        self.assertTrue(self.overlay_file("api/jwt-ttl").exists())

    def test_references_from_read_only_slices_are_reported(self):
        self.mount_slice("watcher", {"w": card_text("Watcher", "Watches [[@overlay/api/jwt-ttl]].")}, "@watcher", 10, "baseline")
        res = self.ws.mount(self.imported, alias="@api", precedence=60, role="curated")
        self.assertEqual(res["broken_references"], [{"address": "@watcher/w", "kind": "wikilink", "ref": "@overlay/api/jwt-ttl"}])

    def test_keep_overlay_opts_out(self):
        code, out, _ = run_cli("-w", str(self.root), "--json", "mount", str(self.imported), "--alias", "@api",
                               "--keep-overlay")
        self.assertEqual(code, 0, out)
        self.assertNotIn("retired_overlay_cards", json.loads(out))
        self.assertTrue(self.overlay_file("api/jwt-ttl").exists())
        self.assertEqual(self.ws.read("@project/api/auth-flow")["status"], "competing_replacements")


if __name__ == "__main__":
    unittest.main()
