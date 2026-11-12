"""TOML serializer, card parsing, addressing and wikilink handling."""

from __future__ import annotations

import tomllib
import unittest

from mindslice.model import tomlfmt
from mindslice.model.addressing import (
    MountCatalog,
    alias_from_name,
    extract_wikilinks,
    normalize_path,
    parse_address,
    resolve_ref,
    rewrite_wikilinks,
)
from mindslice.model.card import append_statements, parse_card, preview_text, split_lead, statement_blocks
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


class PlainMarkdownTests(unittest.TestCase):
    def test_yaml_subset(self):
        parsed = parse_card(
            "---\n"
            "title: \"Alpha: the project\"  # quoted, with a comment\n"
            "tags: work, alpha\n"
            "aliases: [project a, 'it''s alpha', \"b, c\"]\n"
            "extends:\n"
            "- notes/base\n"
            "summary: >\n"
            "  folded over\n"
            "  two lines\n"
            "description: plain text that\n"
            "  continues here\n"
            "draft: true\n"
            "empty:\n"
            "nested:\n"
            "  key: value\n"
            "inline: {a: 1}\n"
            "...\n"
            "\n"
            "# Alpha\n"
            "\n"
            "Lead paragraph.\n"
        )
        self.assertEqual(parsed.frontmatter_format, "yaml")
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.title, "Alpha: the project")
        self.assertEqual(parsed.tags, ["work", "alpha"])
        self.assertEqual(parsed.aliases, ["project a", "it's alpha", "b, c"])
        self.assertEqual(parsed.extends, ["notes/base"])
        self.assertEqual(parsed.frontmatter["summary"], "folded over two lines")
        self.assertEqual(parsed.frontmatter["description"], "plain text that continues here")
        self.assertEqual(parsed.frontmatter["draft"], "true")
        self.assertNotIn("empty", parsed.frontmatter)
        self.assertEqual(len(parsed.warnings), 2)  # nested and inline mappings are skipped
        self.assertEqual(parsed.after.lstrip("\n"), "# Alpha\n\nLead paragraph.\n")
        self.assertEqual(parsed.index_parts(), ("Lead paragraph.", "# Alpha"))

    def test_dashes_that_are_not_frontmatter(self):
        for text in ("---\nJust a thematic break, then prose.\n---\n\nMore.\n",  # prose inside
                     "---\ntitle: never closed\n\nBody.\n",  # unclosed
                     "Intro.\n---\ntitle: x\n---\n"):  # not at the top
            parsed = parse_card(text)
            self.assertIsNone(parsed.frontmatter_format, text)
            self.assertEqual(parsed.frontmatter, {}, text)
            self.assertEqual(parsed.errors, [], text)

    def test_lead_paragraph(self):
        body = "# Title\n\n```\ncode\n```\n\nFirst prose\nparagraph.\n\n- bullet\n\nLater prose."
        lead, rest = split_lead(body)
        self.assertEqual(lead, "First prose paragraph.")
        self.assertEqual(rest, "# Title\n\n```\ncode\n```\n\n- bullet\n\nLater prose.")
        self.assertEqual(split_lead("- only\n- bullets"), ("", "- only\n- bullets"))
        native = parse_card(card_text("T") + "\n# Heading\n\nProse.\n")
        self.assertEqual(native.index_parts()[0], "")  # native cards keep the summary-under-frontmatter rule


class AddressingTests(unittest.TestCase):
    def test_parse_and_normalize(self):
        self.assertEqual(parse_address("@project/api/auth-flow"), ("@project", "api/auth-flow"))
        self.assertEqual(parse_address("./api/auth-flow.md"), (None, "api/auth-flow"))
        for bad in ("../x", "@project", "", "a/.hidden", "@/x"):
            with self.assertRaises(InvalidAddressError, msg=bad):
                parse_address(bad)
        self.assertEqual(normalize_path("a//b/"), "a/b")

    def test_any_existing_file_name_is_addressable_but_new_ids_are_link_safe(self):
        name = "notes/2024-01-01 (draft) & Q&A, v2#3"
        self.assertEqual(normalize_path(name), name)
        self.assertEqual(parse_address("@notes/" + name), ("@notes", name))
        for bad in ("a/.hidden", "a/../b", "a/ padded", "tab\there"):
            with self.assertRaises(InvalidAddressError, msg=bad):
                normalize_path(bad)
        with self.assertRaises(InvalidAddressError):
            normalize_path(name, strict=True)
        self.assertEqual(normalize_path("team/lead-2026_11.v2", strict=True), "team/lead-2026_11.v2")

    def test_alias_from_name(self):
        self.assertEqual(alias_from_name("My Notes"), "@My-Notes")
        self.assertEqual(alias_from_name("kb-en"), "@kb-en")
        self.assertEqual(alias_from_name("_drafts"), "@s_drafts")
        self.assertEqual(alias_from_name("笔记"), "@slice")

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
