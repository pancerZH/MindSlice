"""TOML serializer, card parsing, addressing and wikilink handling."""

from __future__ import annotations

import tomllib
import unittest

from mindslice import tomlfmt
from mindslice.addressing import (
    MountCatalog,
    extract_wikilinks,
    normalize_path,
    parse_address,
    resolve_ref,
    rewrite_wikilinks,
)
from mindslice.card import append_statements, parse_card, preview_text, statement_blocks
from mindslice.errors import FrontmatterError, InvalidAddressError

from .helpers import card_text


class TomlSerializerTests(unittest.TestCase):
    def test_round_trip_unicode_and_escapes(self):
        data = {
            "title": 'Emoji 🚀 "quoted" back\\slash',
            "aliases": ["tab\there", "new\nline", "cr\rx", "bell\x07", "del\x7f", "nul\x00", "ff\fbs\b"],
            "tags": [],
            "weird key": "ünïcödé — 中文",
        }
        text = tomlfmt.dumps_flat(data)
        self.assertEqual(tomllib.loads(text), data)
        self.assertIn("🚀", text)  # UTF-8 emitted directly, never as surrogate escapes
        self.assertNotIn("\\ud83d", text.lower())
        self.assertIn("\\u0007", text)
        self.assertIn("\\u007F", text)
        self.assertIn('"weird key"', text)

    def test_lone_surrogate_rejected(self):
        with self.assertRaises(FrontmatterError):
            tomlfmt.dumps_flat({"title": "bad \ud83d"})

    def test_document_with_tables(self):
        text = tomlfmt.dumps_document(
            tables={"overlay": {"path": "./overlay", "alias": "@overlay", "precedence": 100}},
            array_tables={"mounts": [{"path": "./a", "alias": "@a", "precedence": 1}, {"path": "./b", "alias": "@b", "precedence": 2}]},
            header="comment",
        )
        parsed = tomllib.loads(text)
        self.assertEqual(parsed["overlay"]["precedence"], 100)
        self.assertEqual([m["alias"] for m in parsed["mounts"]], ["@a", "@b"])


class CardParsingTests(unittest.TestCase):
    def test_standard_card(self):
        text = card_text(
            "Error Handling",
            "All services raise typed AppError subclasses.",
            ["See [[architecture/http-middleware]].", "Log via [[observability/structured-logging|logging]]."],
            tags=["python"],
            aliases=["error-handling"],
        )
        parsed = parse_card(text)
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.title, "Error Handling")
        self.assertEqual(parsed.aliases, ["error-handling"])
        self.assertEqual(parsed.summary, "All services raise typed AppError subclasses.")
        self.assertTrue(parsed.body.startswith("- See"))
        self.assertEqual(parsed.wikilink_targets(), ["architecture/http-middleware", "observability/structured-logging"])

    def test_wikilinks_ignore_code(self):
        text = "Use [[real]].\n\n```\n[[not-a-link]]\n```\n\nInline `[[nope]]` and [[also-real#section|label]].\n"
        targets = [l.target for l in extract_wikilinks(text)]
        self.assertEqual(targets, ["real", "also-real"])
        rewritten = rewrite_wikilinks(text, {"also-real": "x/also-real"})
        self.assertIn("[[x/also-real#section|label]]", rewritten)
        self.assertIn("`[[nope]]`", rewritten)

    def test_no_frontmatter_and_heading_title(self):
        parsed = parse_card("# Overview\n\nThis slice covers payments.\n")
        self.assertFalse(parsed.has_frontmatter)
        self.assertEqual(parsed.display_title("overview"), "Overview")
        self.assertEqual(preview_text(parsed.summary, parsed.body)[0], "This slice covers payments.")

    def test_unclosed_frontmatter_is_reported(self):
        parsed = parse_card("+++\ntitle = \"x\"\n\nbody\n")
        self.assertTrue(parsed.errors)

    def test_invalid_schema(self):
        parsed = parse_card('+++\ntitle = "x"\ncount = 3\n+++\n\nSummary.\n')
        self.assertTrue(any("count" in e for e in parsed.errors))

    def test_statement_normalization_and_dedupe(self):
        blocks = statement_blocks("first fact\n* second fact\n  continued\n- third")
        self.assertEqual(blocks, ["- first fact", "- second fact\n  continued", "- third"])
        after = "\nSummary.\n\n- first   fact\n"
        new_after, added = append_statements(after, blocks + ["- Third"])
        self.assertEqual(added, ["- second fact\n  continued", "- third"])
        self.assertTrue(new_after.endswith("- first   fact\n- second fact\n  continued\n- third\n"))
        again, added_again = append_statements(new_after, blocks)
        self.assertEqual(added_again, [])
        self.assertEqual(again, new_after)

    def test_append_after_summary_only(self):
        new_after, _ = append_statements("\nJust a summary.\n", ["- fact"])
        self.assertEqual(new_after, "\nJust a summary.\n\n- fact\n")


class AddressingTests(unittest.TestCase):
    def test_parse_and_normalize(self):
        self.assertEqual(parse_address("@project/api/auth-flow"), ("@project", "api/auth-flow"))
        self.assertEqual(parse_address("./api/auth-flow.md"), (None, "api/auth-flow"))
        for bad in ("../x", "@project", "", "a/.hidden", "@/x"):
            with self.assertRaises(InvalidAddressError, msg=bad):
                parse_address(bad)
        self.assertEqual(normalize_path("a//b/"), "a/b")

    def test_slice_relative_resolution_never_uses_other_mounts(self):
        cats = {"@db": MountCatalog(), "@overlay": MountCatalog()}
        cats["@db"].add("db/conn", ["connection"])
        cats["@overlay"].add("db/conn")
        cats["@overlay"].add("other")
        self.assertEqual(resolve_ref("db/conn", "@db", cats).address, "@db/db/conn")
        self.assertEqual(resolve_ref("connection", "@db", cats).address, "@db/db/conn")
        self.assertFalse(resolve_ref("other", "@db", cats).resolved)
        self.assertEqual(resolve_ref("@overlay/other", "@db", cats).address, "@overlay/other")
        unresolved = resolve_ref("@missing/x", "@db", cats)
        self.assertFalse(unresolved.resolved)
        self.assertEqual(unresolved.mount, "@missing")


if __name__ == "__main__":
    unittest.main()
