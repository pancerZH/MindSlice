"""Always-loaded cards (``load = "always"``): boot set, delivery, and approval-gated writes."""

from __future__ import annotations

import json

from mindslice import FrontmatterError
from mindslice.card import parse_card
from mindslice.mcp_server import EMPTY_WORKSPACE_HINT, INSTRUCTIONS, MCPServer

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


def always_card(title: str, summary: str, bullets=(), **kw) -> str:
    return card_text(title, summary, bullets, **kw).replace(f'title = "{title}"\n', f'title = "{title}"\nload = "always"\n', 1)


class AlwaysLoadedCase(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.mount_slice("persona", {
            "tone": always_card("Persona: Mira", "You are Mira, a concise pair programmer.", ["Answer briefly."]),
            "glossary": card_text("Glossary", "Terms the team uses."),
        }, "@persona", 10, "baseline")

    def boot_addresses(self) -> list[str]:
        return [c["address"] for c in self.ws.boot()["cards"]]


class FormatTests(AlwaysLoadedCase):
    def test_field_parse_and_validate(self):
        self.assertEqual(parse_card(always_card("T", "S.")).load, "always")
        self.assertEqual(parse_card(card_text("T", "S.")).load, "as-needed")
        bad = card_text("T", "S.").replace('title = "T"\n', 'title = "T"\nload = "sometimes"\n')
        self.assertEqual(parse_card(bad).load, "as-needed")
        self.put_overlay("bad", bad)
        report = self.ws.validate()
        self.assertFalse(report["ok"])
        self.assertIn("'load' must be", report["errors"][0]["message"])

    def test_yaml_frontmatter_counts_too(self):
        root = self.make_slice("notes", {"me": "---\ntitle: About me\nload: always\n---\n\nCall me Wen.\n"}, alias="@notes")
        self.ws.mount(root, alias="@notes", precedence=20)
        self.assertEqual(self.boot_addresses(), ["@persona/tone", "@notes/me"])

    def test_write_sets_and_clears_the_field(self):
        self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        text = self.overlay_file("prefs/lang").read_text()
        self.assertIn('load = "always"', text.split("+++")[1].splitlines()[2])  # right after title
        self.ws.write("prefs/lang", op="replace", load="as-needed", stage=False)
        self.assertNotIn("load", self.overlay_file("prefs/lang").read_text())
        self.ws.write("plain", summary="An ordinary card.")
        self.assertNotIn("load", self.overlay_file("plain").read_text())
        with self.assertRaises(ValueError):
            self.ws.write("x", summary="s", load="sometimes")
        with self.assertRaises(FrontmatterError):  # hand-edited invalid value is not silently kept
            self.put_overlay("y", card_text("Y", "s").replace('title = "Y"\n', 'title = "Y"\nload = 3\n'))
            self.ws.write("y", op="append", content="- more")

    def test_read_and_search_flag_the_card(self):
        self.assertEqual(self.ws.read("@persona/tone")["load"], "always")
        self.assertNotIn("load", self.ws.read("@persona/glossary"))
        hit = self.ws.search("Mira pair programmer")["results"][0]
        self.assertEqual((hit["address"], hit["load"]), ("@persona/tone", "always"))


class BootSetTests(AlwaysLoadedCase):
    def test_boot_manifest_and_mount(self):
        boot = self.ws.boot()
        self.assertEqual(self.boot_addresses(), ["@persona/tone"])
        self.assertEqual(boot["cards"][0]["body"].strip(), "- Answer briefly.")
        m = self.ws.manifest()
        self.assertEqual([c["address"] for c in m["always_loaded"]], ["@persona/tone"])
        self.assertNotIn("always_loaded", self.ws.manifest(offset=1))
        self.assertNotIn("always_loaded", self.ws.manifest(include_always=False))
        root = self.make_slice("lang", {"zh": always_card("Language", "Reply in Chinese.")}, alias="@lang")
        mounted = self.ws.mount(root, alias="@lang", precedence=20)
        self.assertEqual([c["address"] for c in mounted["always_loaded"]], ["@lang/zh"])
        self.assertEqual(self.boot_addresses(), ["@persona/tone", "@lang/zh"])  # base layers first

    def test_supersedes_and_extends_compose_like_read(self):
        self.ws.write("persona-v2", summary="You are Mira v2.", supersedes=["@persona/tone"], stage=False)
        cards = self.ws.boot()["cards"]
        self.assertEqual([(c["address"], c.get("redirected_from")) for c in cards],
                         [("@overlay/persona-v2", "@persona/tone")])
        self.ws.write("persona-v2", op="delete", stage=False)
        self.ws.write("emoji", summary="Mira may use emoji.", extends=["@persona/tone"], load="always", stage=False)
        cards = self.ws.boot()["cards"]
        self.assertEqual(len(cards), 1, "an always-loaded extension is shown once, under its baseline")
        self.assertEqual([e["address"] for e in cards[0]["extensions"]], ["@overlay/emoji"])

    def test_markdown_rendering(self):
        code, out, _ = run_cli("-w", str(self.root), "boot")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# Always-loaded memory"))
        self.assertIn("## Persona: Mira (@persona/tone)", out)
        self.assertIn("- Answer briefly.", out)
        self.assertNotIn("Glossary", out)


class ProtectionTests(AlwaysLoadedCase):
    def assert_staged(self, result, reason_part):
        self.assertTrue(result["staged"], result)
        self.assertIn(reason_part, result["requires_approval"])

    def test_changes_to_the_boot_context_are_staged(self):
        self.assert_staged(self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always"), "always-loaded")
        self.assert_staged(self.ws.write("emoji", summary="May use emoji.", extends=["@persona/tone"]), "extends @persona/tone")
        self.assert_staged(self.ws.write("v2", summary="Mira v2.", supersedes=["@persona/tone"]), "supersedes @persona/tone")
        self.assertEqual(self.boot_addresses(), ["@persona/tone"], "nothing applied yet")
        self.assertFalse(self.overlay_file("prefs/lang").exists())
        pending = self.ws.boot()["pending_approval"]
        self.assertEqual(sorted(p["id"] for p in pending), ["emoji", "prefs/lang", "v2"])
        self.assertTrue(all(i["requires_approval"] for i in self.ws.diff()["items"]))
        self.assertEqual(len(self.ws.manifest()["staging"]["awaiting_approval"]), 3)
        # A later write to a path whose staged version is always-loaded stays staged.
        self.assert_staged(self.ws.write("prefs/lang", op="append", content="- Simplified characters."), "always-loaded")
        self.ws.write("v2", op="delete")  # forget the staged-only create
        self.ws.apply()
        self.assertEqual(self.boot_addresses(), ["@persona/tone", "@overlay/prefs/lang"])
        self.assertIn("Simplified characters", self.ws.read("prefs/lang")["body"])

    def test_edits_and_deletes_of_applied_cards_are_staged(self):
        self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        self.ws.write("prefs/base", summary="Shared premise.", stage=False)
        self.ws.write("prefs/lang", op="append", extends=["prefs/base"], stage=False)
        self.assert_staged(self.ws.write("prefs/lang", op="replace", summary="Reply in English."), "always-loaded")
        self.assert_staged(self.ws.write("prefs/lang", op="delete"), "always-loaded")
        # A baseline composed into an always-loaded card is part of the context too.
        self.assert_staged(self.ws.write("prefs/base", op="append", content="- Changed."), "part of the always-loaded")

    def test_ordinary_and_explicit_writes_are_direct(self):
        res = self.ws.write("notes/x", summary="Unrelated.")
        self.assertFalse(res["staged"])
        self.assertNotIn("requires_approval", res)
        res = self.ws.write("prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        self.assertFalse(res["staged"])  # a human at the API or CLI may approve inline
        self.assertEqual(self.boot_addresses(), ["@persona/tone", "@overlay/prefs/lang"])


class MCPAlwaysLoadedTests(AlwaysLoadedCase):
    def setUp(self):
        super().setUp()
        self.server = MCPServer(self.ws)

    def tool(self, name, **arguments):
        res = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": name, "arguments": arguments}})["result"]
        return res["isError"], json.loads(res["content"][0]["text"])

    def test_session_start_and_mid_session_updates(self):
        init = self.server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        instructions = init["result"]["instructions"]
        self.assertIn("## Persona: Mira (@persona/tone)", instructions)
        self.assertIn("Answer briefly.", instructions)
        err, res = self.tool("search", query="glossary")
        self.assertNotIn("always_loaded_update", res, "already delivered at initialize")

        # The agent records a preference: staged even though it asked for a direct write.
        err, res = self.tool("write", id="prefs/lang", summary="Reply in Chinese.", load="always", stage=False)
        self.assertFalse(err, res)
        self.assertTrue(res["staged"])
        self.assertIn("requires_approval", res)
        self.assertNotIn("always_loaded_update", res)

        self.ws.apply()  # the user approves, outside the session
        err, res = self.tool("search", query="glossary")
        update = res["always_loaded_update"]
        self.assertEqual([c["address"] for c in update["cards"]], ["@overlay/prefs/lang"])
        err, res = self.tool("search", query="glossary")
        self.assertNotIn("always_loaded_update", res, "delivered once")

        self.ws.unmount("@persona")
        err, res = self.tool("read", address="prefs/lang")
        self.assertEqual(res["always_loaded_update"]["removed"], ["@persona/tone"])

    def test_manifest_delivers_the_set(self):
        err, res = self.tool("manifest")
        self.assertEqual([c["address"] for c in res["always_loaded"]], ["@persona/tone"])
        err, res = self.tool("search", query="glossary")
        self.assertNotIn("always_loaded_update", res)

    def test_stage_writes_mode_still_flags_approval(self):
        server = MCPServer(self.ws, stage_writes=True)
        res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "write", "arguments": {"id": "emoji", "summary": "May use emoji.", "extends": ["@persona/tone"]}}})
        payload = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("extends @persona/tone", payload["requires_approval"])


class OnboardingTests(WorkspaceTestCase):
    """Empty workspaces surface a cold-start onboarding hint until a card is written, staged, or mounted."""

    def test_empty_workspace_surfaces_onboarding_and_retires_once_seeded(self):
        boot = self.ws.boot()
        self.assertEqual(boot["cards"], [])
        self.assertTrue(boot["empty_workspace"])

        manifest = self.ws.manifest()
        self.assertIn("onboarding_hint", manifest)
        self.assertNotIn("onboarding_hint", self.ws.manifest(include_always=False))

        server = MCPServer(self.ws)
        init = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        instructions = init["result"]["instructions"]
        self.assertTrue(instructions.startswith(INSTRUCTIONS))
        self.assertIn(EMPTY_WORKSPACE_HINT, instructions)

        # Plain `mindslice boot` stays empty when there are no always-loaded cards;
        # `--mcp-instructions` emits the full MCP startup prompt for session-start hooks.
        code, plain_out, _ = run_cli("-w", str(self.root), "boot")
        self.assertEqual((code, plain_out), (0, ""))
        code, hook_out, _ = run_cli("-w", str(self.root), "boot", "--mcp-instructions")
        self.assertEqual(code, 0)
        self.assertIn(INSTRUCTIONS, hook_out)
        self.assertIn("# Empty memory workspace", hook_out)

        # Writing a single ordinary card retires the empty-workspace hint (zero extra tokens).
        self.ws.write("tooling/python", summary="Use uv for Python dependencies.")
        self.assertNotIn("empty_workspace", self.ws.boot())
        self.assertNotIn("onboarding_hint", self.ws.manifest())
        self.assertEqual(MCPServer(self.ws).instructions(), INSTRUCTIONS)
        self.ws.write("tooling/python", op="delete")
        self.assertTrue(self.ws.boot()["empty_workspace"])

        # Staging an always-loaded card also retires the empty-workspace hint immediately.
        self.ws.write("prefs/lang", summary="Reply in Simplified Chinese.", load="always")
        self.assertNotIn("empty_workspace", self.ws.boot())
        self.assertNotIn("onboarding_hint", self.ws.manifest())
        self.assertEqual(MCPServer(self.ws).instructions(), INSTRUCTIONS)

        # Once approved, `--mcp-instructions` combines MCP instructions with Always-loaded memory.
        self.ws.apply()
        code, hook_out, _ = run_cli("-w", str(self.root), "boot", "--mcp-instructions")
        self.assertEqual(code, 0)
        self.assertIn(INSTRUCTIONS, hook_out)
        self.assertIn("# Always-loaded memory", hook_out)
        self.assertIn("Reply in Simplified Chinese.", hook_out)
        code, json_out, _ = run_cli("-w", str(self.root), "boot", "--json", "--mcp-instructions")
        self.assertEqual(code, 0)
        self.assertIn("# Always-loaded memory", json.loads(json_out)["instructions"])

    def test_mounted_slice_retires_empty_workspace_hint(self):
        root = self.make_slice("empty_notes", {}, alias="@notes")
        self.ws.mount(root, alias="@notes", precedence=20)
        self.assertNotIn("empty_workspace", self.ws.boot())
        self.assertNotIn("onboarding_hint", self.ws.manifest())
        self.assertEqual(MCPServer(self.ws).instructions(), INSTRUCTIONS)
