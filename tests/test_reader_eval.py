"""Reader QA harness (evals/agent/reader.py): parsing, grading, question selection, page rendering, quota floor.

No model and no dataset: the parts a run depends on, checked on synthetic inputs.
"""

from __future__ import annotations

import unittest
from unittest import mock

from evals.agent import reader

from .helpers import WorkspaceTestCase


def q(set_, task, **values):
    return {"set": set_, "task": task, "values": values}


class ParseTests(unittest.TestCase):
    def test_parse_answer(self):
        self.assertEqual(reader.parse_answer('{"status": "current", "value": "Quelmithin"}'),
                         {"status": "current", "value": "Quelmithin"})
        self.assertEqual(reader.parse_answer('```json\n{"status": "removed", "value": ""}\n```'),
                         {"status": "removed", "value": ""})
        self.assertEqual(reader.parse_answer('Here it is: {"status": "unknown", "value": null} hope it helps'),
                         {"status": "unknown", "value": ""})
        for bad in (None, "", "no json", '{"status": "maybe", "value": "x"}', '{"value": "x"}'):
            self.assertIsNone(reader.parse_answer(bad), bad)


class GradeTests(unittest.TestCase):
    def test_targets(self):
        cas = q("target", "Cas", stale=["velthari studio"], current=["kaelstrom fitness"])
        self.assertTrue(reader.grade(cas, {"status": "current", "value": "Kaelstrom Fitness on 5th"}))
        self.assertFalse(reader.grade(cas, {"status": "current", "value": "Velthari Studio"}))
        self.assertFalse(reader.grade(cas, {"status": "uncertain", "value": "Kaelstrom Fitness"}))
        abs_ = q("target", "Abs", stale=["mobile app development"], current=[])
        self.assertTrue(reader.grade(abs_, {"status": "uncertain", "value": "mobile app development"}))
        self.assertFalse(reader.grade(abs_, {"status": "current", "value": "mobile app development"}))
        self.assertFalse(reader.grade(abs_, {"status": "unknown", "value": ""}))
        dele = q("target", "Del", stale=["anniversary dinner"], deleted=["anniversary dinner"])
        self.assertTrue(reader.grade(dele, {"status": "removed", "value": ""}))
        self.assertTrue(reader.grade(dele, {"status": "unknown", "value": ""}))
        self.assertFalse(reader.grade(dele, {"status": "unknown", "value": "maybe the anniversary dinner"}))
        self.assertFalse(reader.grade(dele, {"status": "current", "value": "anniversary dinner"}))
        self.assertFalse(reader.grade(cas, None))

    def test_controls_and_value_matching(self):
        ctl = q("control", "Abs", current=["dermatologist (monthly)"])
        self.assertTrue(reader.grade(ctl, {"status": "current", "value": "A monthly dermatologist visit"}))  # bare value inside
        self.assertTrue(reader.grade(ctl, {"status": "current", "value": "Dermatologist"}))
        self.assertTrue(reader.grade(ctl, {"status": "current", "value": "dermatologist (monthly)"}))
        self.assertFalse(reader.grade(ctl, {"status": "uncertain", "value": "dermatologist (monthly)"}))
        self.assertTrue(reader.value_matches("ＥＭＰＬＯＹＥＲ + supplemental!", ["employer + supplemental"]))
        self.assertFalse(reader.value_matches("ab", ["ab"]))  # too short to count


class SelectionTests(unittest.TestCase):
    def test_questions(self):
        recs = [{"kind": "question", "task": "Cas", "phase": "after", "id": "a"},
                {"kind": "question", "task": "Cas", "phase": "before", "id": "b"},
                {"kind": "question", "task": "Tr", "phase": "after", "id": "c"},
                {"kind": "value", "task": "Cas", "phase": "after", "id": "d"}]
        self.assertEqual([(x["id"], x["set"]) for x in reader.questions(recs)], [("a", "target"), ("b", "control")])
        self.assertEqual([x["id"] for x in reader.questions(recs, ("target",))], ["a"])


class PageTests(WorkspaceTestCase):
    def test_render_page_carries_dates_and_lineage(self):
        self.ws.write("s000/r000", summary="I work at Velthari Studio.", content="- Date: 2023/03/01 (Wed) 09:00\n- User: I work out at Velthari Studio.")
        self.ws.write("gym", summary="The user works out at Kaelstrom Fitness.", content="- Since 2023/04.",
                      supersedes=["s000/r000"])
        res = self.ws.search("where do I work out Velthari", k=10)["results"]
        page = reader.render_page(self.ws, res)
        self.assertIn("[1] @overlay/gym", page)
        self.assertIn("matched_via_superseded: @overlay/s000/r000", page)
        self.assertNotIn("[2]", page)  # the superseded round is redirected into its replacement
        flat = self.ws.search("Date 2023", k=10, follow_supersedes=False)["results"]
        flat_page = reader.render_page(self.ws, flat)
        self.assertIn("Date: 2023/03/01 (Wed) 09:00", flat_page)
        self.assertIn("status: superseded_by: @overlay/gym", flat_page)
        self.assertEqual(reader.render_page(self.ws, []), "(no memory matched the question)")

    def test_lineage_targets_off_the_page_are_quoted(self):
        self.ws.write("health", summary="I am lactose intolerant.", content="- Date: 2023/03/01 (Wed) 09:00")
        self.ws.write("medication", summary="I take Quelmithin because of my health condition.",
                      content="- Date: 2023/03/01 (Wed) 09:05", extends=["health"])
        self.ws.write("health-2", summary="My lactose intolerance resolved; I now have high blood pressure.",
                      content="- Date: 2023/03/04 (Sat) 06:41", supersedes=["health"])
        hits = self.ws.search("Quelmithin", k=10)["results"]
        self.assertEqual([h["address"] for h in hits], ["@overlay/medication"])
        page = reader.render_page(self.ws, hits)
        self.assertIn("baseline_superseded_by: @overlay/health-2", page)
        self.assertIn("  @overlay/health-2 (2023/03/04 (Sat) 06:41): My lactose intolerance resolved", page)
        self.assertNotIn("health-2 (", reader.render_page(self.ws, hits, expand_lineage=False))


class QuotaFloorTests(unittest.TestCase):
    def test_gemini_reader_stops_below_the_floor(self):
        r = reader.GeminiReader("gemini-4-argon-medium", weekly_floor=0.05)
        with mock.patch("evals.agent.agy.read_usage", return_value={"weekly": {"remaining": 0.04, "reset": 0}}):
            with self.assertRaises(reader.QuotaFloor):
                r.answer("s", "u")
        with mock.patch("evals.agent.agy.read_usage", return_value=None):
            with self.assertRaises(reader.QuotaFloor):  # unreadable quota: don't spend
                r.answer("s", "u")


if __name__ == "__main__":
    unittest.main()
