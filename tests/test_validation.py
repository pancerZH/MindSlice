"""validate(): the exact issue each rule reports (severity, code, message, address, file) and the stats."""
from __future__ import annotations

import shutil
from pathlib import Path

from .helpers import WorkspaceTestCase, card_text


def warning(code, message, address=None, file=None):
    return issue("warning", code, message, address, file)


def error(code, message, address=None, file=None):
    return issue("error", code, message, address, file)


def issue(severity, code, message, address, file):
    out = {"severity": severity, "code": code, "message": message}
    if address:
        out["address"] = address
    if file:
        out["file"] = str(file)
    return out


class ValidationReportTests(WorkspaceTestCase):
    def slice_dir(self, name, files, toml=None):
        root = self.tmp / f"{name}.slice"
        for rel, text in files.items():
            (root / f"{rel}.md").parent.mkdir(parents=True, exist_ok=True)
            (root / f"{rel}.md").write_text(text, encoding="utf-8")
        if toml is not None:
            (root / "slice.toml").write_text(toml, encoding="utf-8")
        return root

    def without_parser_text(self, issues):
        """tomllib's wording differs between Python versions: keep only the engine's own prefix."""
        for item in issues:
            if item["code"] in ("invalid_slice_manifest", "invalid_frontmatter", "invalid_staged_card"):
                item["message"] = item["message"].split(":")[0]
        return issues

    def test_every_rule_on_a_workspace(self):
        lib = self.slice_dir("lib", {
            "overview": "# Lib\n",  # the overview needs no frontmatter or summary
            "plain": "# Plain\n\nProse paragraph.\n",
            "heading-only": "# Heading only\n",
            "legacy": "---\ntitle: Legacy\nnested:\n  a: 1\n---\n\nLegacy prose.\n",
            "untitled": '+++\ntitle = ""\n+++\n\nHas a summary.\n',
            "no-summary": card_text("No summary"),
            "long": card_text("Long", ("word " * 50).strip(), [f"line {i}" for i in range(50)]),
            "bad": "+++\ntitle = \n+++\n",
            "refs": card_text("Refs", "References.", ["[[nowhere]] [[only-other]] [[twice]] [[refs]] [[@ghost/x]]"],
                              extends=["refs", "../x", "@ghost/x", "@/x"], supersedes=["missing"]),
            "a": card_text("A", "First.", aliases=["Same"]),
            "b": card_text("B", "Second.", aliases=["same"]),
            "c1": card_text("C1", "Cycle one.", extends=["c2"]),
            "c2": card_text("C2", "Cycle two.", extends=["c1"]),
        }, 'name = "lib"\ndescription = "' + "d" * 161 + '"\ndependencies = ["bad alias!", "@ghost"]\n')
        other = self.slice_dir("other", {"only-other": card_text("Only other", "Here."), "twice": card_text("Twice", "One.")})
        third = self.slice_dir("third", {"twice": card_text("Twice", "Two.")})
        broken = self.slice_dir("broken", {"fine": card_text("Fine", "Fine.")}, "[[invalid")
        for root, alias in ((lib, "lib"), (other, "other"), (third, "third"), (broken, "broken")):
            self.ws.mount(root, alias=alias)
        report = self.ws.validate()
        refs = lib / "refs.md"
        self.assertEqual(self.without_parser_text(report["errors"]), [
            error("invalid_slice_manifest", "invalid slice.toml", file=broken / "slice.toml"),
            error("invalid_dependency", "invalid dependency alias 'bad alias!'", "@lib"),
            error("invalid_frontmatter", "invalid TOML frontmatter", "@lib/bad", lib / "bad.md"),
            error("self_reference", "extends points at the card itself", "@lib/refs", refs),
            error("broken_lineage", "extends target '../x' does not exist", "@lib/refs", refs),
            error("invalid_reference", "extends reference '@/x' is not a valid address", "@lib/refs", refs),
            error("broken_lineage", "supersedes target 'missing' does not exist", "@lib/refs", refs),
            error("lineage_cycle", "circular extends/supersedes chain: @lib/c1 -> @lib/c2 -> @lib/c1", "@lib/c1"),
        ])
        plain = ("plain Markdown (no +++ TOML frontmatter): titled by its first heading or file name, "
                 "summarized by its first paragraph")
        no_summary = "no summary paragraph directly below the frontmatter"
        self.assertEqual(report["warnings"], [
            warning("long_description", "slice.toml description exceeds 160 chars", file=lib / "slice.toml"),
            warning("missing_dependency", "@lib depends on @ghost, which is not mounted", "@lib"),
            warning("missing_title", "frontmatter has no title", "@lib/bad", lib / "bad.md"),
            warning("missing_summary", no_summary, "@lib/bad", lib / "bad.md"),
            warning("missing_frontmatter", plain, "@lib/heading-only", lib / "heading-only.md"),
            warning("missing_summary", "no prose paragraph to summarize the note", "@lib/heading-only",
                    lib / "heading-only.md"),
            warning("frontmatter_schema", "YAML field 'nested' is a nested mapping; ignored", "@lib/legacy",
                    lib / "legacy.md"),
            warning("yaml_frontmatter", "legacy --- YAML frontmatter, read as a flat subset (title, aliases, tags, "
                    "extends, supersedes); +++ TOML is the card format", "@lib/legacy", lib / "legacy.md"),
            warning("long_summary", "summary exceeds 240 chars", "@lib/long", lib / "long.md"),
            warning("card_too_long", "card has 60 lines (> 50); consider splitting", "@lib/long", lib / "long.md"),
            warning("missing_summary", no_summary, "@lib/no-summary", lib / "no-summary.md"),
            warning("missing_frontmatter", plain, "@lib/plain", lib / "plain.md"),
            warning("unmounted_dependency", "extends reference '@ghost/x' targets @ghost, which is not mounted",
                    "@lib/refs", refs),
            warning("broken_wikilink", "[[nowhere]] does not resolve", "@lib/refs", refs),
            warning("broken_wikilink", "[[only-other]] does not resolve; unqualified links only search @lib — "
                    "did you mean [[@other/only-other]]?", "@lib/refs", refs),
            warning("broken_wikilink", "[[twice]] does not resolve; unqualified links only search @lib — "
                    "found in [[@other/twice]], [[@third/twice]]", "@lib/refs", refs),
            warning("unmounted_dependency", "wikilink reference '@ghost/x' targets @ghost, which is not mounted",
                    "@lib/refs", refs),
            warning("missing_title", "frontmatter has no title", "@lib/untitled", lib / "untitled.md"),
            warning("duplicate_alias", "alias 'same' is used by a, b", "@lib"),
        ])
        self.assertEqual((report["ok"], report["target"], report["stats"]),
                         (False, str(self.root), {"slices": 5, "cards": 17, "errors": 8, "warnings": 19}))

    def test_thresholds_are_exclusive(self):
        root = self.slice_dir("edge", {
            "at-limit": card_text("At", "x" * 240, [f"l{i}" for i in range(40)]).rstrip("\n"),  # 50 lines, no final newline
            "over": card_text("Over", "y" * 241, [f"l{i}" for i in range(41)]).rstrip("\n"),  # 51 lines
        }, 'name = "edge"\ndescription = "' + "d" * 160 + '"\n')
        self.ws.mount(root, alias="edge")
        report = self.ws.validate()
        self.assertEqual([(w["code"], w["address"], w["message"]) for w in report["warnings"]], [
            ("long_summary", "@edge/over", "summary exceeds 240 chars"),
            ("card_too_long", "@edge/over", "card has 51 lines (> 50); consider splitting")])

    def test_a_mount_nested_in_another_is_linted_once(self):
        outer = self.slice_dir("outer", {"o": card_text("O", "Outer."), "inner/i": card_text("I", "Inner.")})
        self.ws.mount(outer, alias="outer")
        self.ws.mount(outer / "inner", alias="inner")
        report = self.ws.validate()
        self.assertEqual((report["stats"]["cards"], report["errors"], report["warnings"]), (2, [], []))

    def test_workspace_level_checks(self):
        gone = self.slice_dir("gone", {"g": card_text("G", "Gone.")})
        self.ws.mount(gone, alias="gone")
        self.ws.write("a", summary="A.")
        self.ws.write("a", op="replace", summary="A, pending.", stage=True)
        self.overlay_file("a").write_text(card_text("A", "Edited behind the stage's back."))
        self.ws.write("b", summary="B, pending.", stage=True)
        self.ws.staging.file("b").unlink()
        self.ws.write("c", summary="C, pending.", stage=True)
        self.ws.staging.file("c").write_text("+++\ntitle = \n+++\n")
        self.ws.write("d", summary="D.")
        self.ws.write("d", op="delete", stage=True)  # a staged delete has no staged file to check
        shutil.rmtree(gone)
        report = self.ws.validate()
        errors = self.without_parser_text(report["errors"])
        self.assertEqual(errors, [
            error("missing_mount", f"mount path {self.ws.table().get('@gone').path} does not exist", "@gone"),
            error("staged_file_missing", "manifest entry has no staged file", "@overlay/b"),
            error("invalid_staged_card", "invalid TOML frontmatter", "@overlay/c", self.ws.staging.file("c"))])
        [conflict] = report["warnings"]
        self.assertEqual((conflict["severity"], conflict["code"], conflict["address"]),
                         ("warning", "staging_conflict", "@overlay/a"))
        self.assertTrue(conflict["message"].startswith("staged change would not apply: "))
        self.assertEqual(report["target"], str(self.root))

    def test_standalone_slice_checks_declared_dependencies(self):
        self.ws.mount(self.slice_dir("other", {"only-other": card_text("Only other", "Here.")}), alias="other")
        solo = self.slice_dir("solo", {
            "s": card_text("S", "Solo.", ["[[@ghost/x]] [[@phantom/y]] [[@other/only-other]]"],
                           extends=["@other/only-other"]),
        }, 'name = "solo"\ndependencies = ["@ghost"]\n')
        report = self.ws.validate(solo)
        file = solo / "s.md"
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [
            warning("undeclared_dependency", "extends reference '@other/only-other' targets @other, which is not "
                    "declared in slice.toml dependencies", "@solo/s", file),
            warning("undeclared_dependency", "wikilink reference '@phantom/y' targets @phantom, which is not declared "
                    "in slice.toml dependencies", "@solo/s", file),
            warning("undeclared_dependency", "wikilink reference '@other/only-other' targets @other, which is not "
                    "declared in slice.toml dependencies", "@solo/s", file),
        ])
        self.assertEqual(report["stats"], {"slices": 1, "cards": 1, "errors": 0, "warnings": 3})
        self.assertEqual(report["target"], str(solo.resolve()))
        checked = self.slice_dir("checked", {"k": card_text("K", "Checked.", ["[[@other/missing]] [[only-other]]"])},
                                 'name = "checked"\ndependencies = ["@other"]\n')
        self.assertEqual([w["message"] for w in self.ws.validate(checked)["warnings"]], [
            "[[@other/missing]] does not resolve",  # a declared, mounted dependency is checked
            "[[only-other]] does not resolve; unqualified links only search @checked — did you mean [[@other/only-other]]?"])
        odd = self.slice_dir("!!!", {"x": card_text("X")})
        self.assertEqual([w["address"] for w in self.ws.validate(odd)["warnings"]], ["@self/x"])
        self.assertEqual(self.ws.validate(self.tmp / "absent")["errors"],
                         [error("missing_slice", f"{(self.tmp / 'absent').resolve()} is not a directory")])
