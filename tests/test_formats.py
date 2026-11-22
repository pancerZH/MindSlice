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
from mindslice.model.card import (append_statements, parse_card, parse_yaml_subset, preview_text, split_lead,
                                  statement_blocks)
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



def yaml(text):
    return parse_yaml_subset(text.split("\n"))


class YamlSubsetTests(unittest.TestCase):
    """The legacy ``---`` frontmatter subset, one rule per case."""

    def test_comments_after_quoted_values(self):
        self.assertEqual(yaml('title: "say \\"hi\\" # not" # c'), ({"title": 'say "hi" # not'}, []))
        self.assertEqual(yaml("title: 'it''s # here' # c"), ({"title": "it's # here"}, []))
        self.assertEqual(yaml('title: "a" b'), ({"title": '"a" b'}, []))  # text after the quote: not a quoted scalar
        self.assertEqual(yaml('title: "abc # x'), ({"title": '"abc # x'}, []))  # never closed: kept whole
        self.assertEqual(yaml("tags: a#b"), ({"tags": ["a#b"]}, []))  # a comment needs a space before the #
        self.assertEqual(yaml("title: a # b # c"), ({"title": "a"}, []))  # the first comment marker wins
        self.assertEqual(yaml("x: |   # keep\n  a\n  b"), ({"x": "a\nb"}, []))  # a block indicator may carry a comment
        self.assertEqual(yaml('title: "\\x"'), ({"title": "\\x"}, []))  # not valid JSON: the text between the quotes

    def test_quotes_inside_quoted_values(self):
        for text, value in (("title: 'a' # it's", "a"), ('title: "" # c', ""), ("title: '''' # c", "'"),
                            ("title: 'abc # x", "'abc # x"), ("title: 'a''b' # it's", "a'b"), ("title: 'a''' # c", "a'"),
                            ('title: "a\\"b" # say "x"', 'a"b'), ('title: "a\\"" # c', 'a"'), ('title: "a"b # c', '"a"b # c')):
            self.assertEqual(yaml(text), ({"title": value}, []), text)

    def test_a_skipped_field_does_not_end_the_block(self):
        for text, warning in (("aliases: [a, [b]]", "YAML field 'aliases' is not a flat list; ignored"),
                              ("inline: {a: 1}", "YAML field 'inline' is a mapping; ignored"),
                              ("k:\n  sub: 1", "YAML field 'k' is a nested mapping; ignored")):
            self.assertEqual(yaml(text + "\ntitle: T"), ({"title": "T"}, [warning]), text)

    def test_fences(self):
        empty = parse_card("---\n---\n\nBody.\n")
        self.assertEqual((empty.frontmatter_format, empty.frontmatter, empty.after), ("yaml", {}, "\nBody.\n"))
        spaced = parse_card("---  \ntitle: x\n---   \nFirst line.\n")  # trailing spaces after the fences
        self.assertEqual((spaced.frontmatter_format, spaced.title, spaced.after), ("yaml", "x", "First line.\n"))

    def test_fields_after_blank_lines_and_comments(self):
        self.assertEqual(yaml("a: 1\n\n# note\n  # indented comment\nb: 2"), ({"a": "1", "b": "2"}, []))
        self.assertEqual(yaml("k\t:  v  "), ({"k": "v"}, []))
        self.assertEqual(yaml("key_1-x: v"), ({"key_1-x": "v"}, []))

    def test_lines_that_end_the_block(self):
        for text in ("  title: x", "title:x", "-key: v"):
            self.assertIsNone(yaml(text), text)

    def test_flow_lists(self):
        self.assertEqual(yaml("aliases: [one,\n  two,\n  three]  # c\nb: x"),
                         ({"aliases": ["one", "two", "three"], "b": "x"}, []))
        self.assertEqual(yaml("aliases: [a, ~, null, '']"), ({"aliases": ["a", ""]}, []))
        for text in ("aliases: [a, [b]]", "aliases: [a, {b: 1}]", "aliases: [a, b"):
            fields, warnings = yaml(text)
            self.assertEqual(fields, {}, text)
            self.assertEqual(warnings, ["YAML field 'aliases' is not a flat list; ignored"], text)

    def test_block_scalars_keep_or_fold_lines(self):
        self.assertEqual(yaml("x: |\n  one\n\n  two\n\ny: 1"), ({"x": "one\n\ntwo", "y": "1"}, []))
        self.assertEqual(yaml("x: >\n  one\n\n  two\n\ny: 1"), ({"x": "one two", "y": "1"}, []))
        self.assertEqual(yaml("x: |-\n  a\n  b"), ({"x": "a\nb"}, []))
        self.assertEqual(yaml("x: >+\n  a\n  b"), ({"x": "a b"}, []))

    def test_block_lists_and_nulls(self):
        self.assertEqual(yaml("aliases:\n- a\n-\n  - b\n# c\n- ~\nnext: v"), ({"aliases": ["a", "b"], "next": "v"}, []))
        self.assertEqual(yaml("tags:\n  - ~"), ({"tags": []}, []))
        self.assertEqual(yaml("empty:\nnext: v"), ({"next": "v"}, []))
        self.assertEqual(yaml("k:\n  sub: 1\n  - a"), ({}, ["YAML field 'k' is a nested mapping; ignored"]))
        self.assertEqual(yaml("title: ~\nsummary: null"), ({}, []))

    def test_list_fields_given_as_scalars(self):
        self.assertEqual(yaml("tags: a, b ,, c"), ({"tags": ["a", "b", "c"]}, []))
        self.assertEqual(yaml("aliases: one, two"), ({"aliases": ["one, two"]}, []))
        self.assertEqual(yaml("extends: base"), ({"extends": ["base"]}, []))


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
