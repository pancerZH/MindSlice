"""The pre-registered reader-QA protocol (evals/agent/reader_qa.py) on a synthetic runs root: no data, no model."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evals.agent import reader_qa as qa


def question(qid, phase, task, point, current=(), stale=(), deleted=()):
    values = {"current": list(current)}
    if stale:
        values["stale"] = list(stale)
    if deleted:
        values["deleted"] = list(deleted)
    return {"kind": "question", "id": qid, "phase": phase, "task": task, "point": point, "query": f"q {qid}",
            "values": values, "page": []}


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="reader-qa-test-"))
        self.root = self.tmp / "runs"
        for src in qa.ARMS.values():
            d = self.root / src / "meme-nofiller__pl_900"
            d.mkdir(parents=True)
            recs = [question("pl_900/before0", "before", "Cas", 1, current=["a"]),
                    question("pl_900/after0", "after", "Cas", "end", current=["b"], stale=["a"]),
                    question("pl_900/before1", "before", "Abs", 1, current=["c"]),
                    question("pl_900/after1", "after", "Abs", "end", stale=["c"])]
            (d / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        self.patches = [mock.patch.object(qa, "FREEZE", self.tmp / "freeze.json"),
                        mock.patch.object(qa, "AUDIT", self.tmp / "audit"),
                        mock.patch.dict(qa.GATE, {"repeats": 2, "min_repeat_agreement": 2})]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lines_and_readers(self):
        ids = [l["id"] for l in qa.LINES]
        self.assertEqual(ids[0], "R1")
        self.assertEqual(sum(i.startswith("R2") for i in ids), 3)
        self.assertEqual(sum(i.startswith("R3") for i in ids), 7)
        self.assertEqual(qa.READER_ARMS[qa.COMPARISON_READER], ("flat", "oracle"))
        self.assertEqual(set(qa.READER_ARMS[qa.LINE_READER]), set(qa.ARMS))

    def test_freeze_and_check(self):
        facts = qa.facts(self.root)
        self.assertEqual(facts["questions"]["flat"], {"target": 2, "control": 2})
        qa.FREEZE.write_text(json.dumps(facts))
        self.assertEqual(qa.check(self.root), [])
        f = self.root / qa.ARMS["oracle"] / "meme-nofiller__pl_900" / "records.jsonl"
        f.write_text(f.read_text() + "\n")
        self.assertIn("inputs_sha256 changed since the freeze", qa.check(self.root))

    def test_stage_items(self):
        s1 = qa.stage_items(self.root, qa.COMPARISON_READER, 1)
        self.assertEqual(len(s1["stage1.jsonl"]), 4)  # flat and oracle controls
        self.assertEqual(len(s1["repeats.jsonl"]), 2)
        s2 = qa.stage_items(self.root, qa.COMPARISON_READER, 2)
        self.assertEqual(len(s2["stage2.jsonl"]), 4)  # flat and oracle targets
        self.assertNotIn("variance.jsonl", s2)
        a2 = qa.stage_items(self.root, qa.LINE_READER, 2)
        self.assertEqual(len(a2["stage2.jsonl"]), 8 * 2 + 6 * 2)
        self.assertEqual(len(a2["variance.jsonl"]), 4)

    def write(self, reader, name, recs):
        d = qa.out_dir(self.root, reader)
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text("".join(json.dumps(r) + "\n" for r in recs))

    def rec(self, arm, unit_, set_, task, correct, status="current", value="x", valid=True):
        return {"arm": arm, "unit": unit_, "set": set_, "task": task, "hop": None, "query": "q", "answered": True,
                "valid": valid, "correct": correct, "parsed": {"status": status, "value": value} if valid else None,
                "values": {"current": ["gold"]}}

    def test_gate(self):
        r = qa.COMPARISON_READER
        s1 = [self.rec(a, f"pl_900|pl_900/before{i}|1", "control", "Cas", True) for a in ("flat", "oracle") for i in (0, 1)]
        self.write(r, "stage1.jsonl", s1)
        self.write(r, "repeats.jsonl", s1[:2])
        self.assertTrue(qa.gate_result(self.root, r)["pass"])
        s1[0] = self.rec("flat", s1[0]["unit"], "control", "Cas", False, status="unknown")
        s1[1] = self.rec("flat", s1[1]["unit"], "control", "Cas", False, valid=False)
        self.write(r, "stage1.jsonl", s1)
        g = qa.gate_result(self.root, r)
        self.assertFalse(g["pass"])
        self.assertEqual(g["control_accuracy"]["flat"], 0.0)

    def test_lines_wait_for_hand_checks(self):
        r = qa.LINE_READER
        recs = []
        for i in range(10):
            u = f"pl_900|q{i}|end"
            recs += [self.rec("flat", u, "target", "Abs", i < 3), self.rec("oracle", u, "target", "Abs", i < 9)]
            for arm in qa.AGENT_ARMS:
                recs.append(self.rec(arm, u, "target", "Abs", True))
            c = f"pl_900|c{i}|1"
            recs += [self.rec(a, c, "control", "Cas", True) for a in qa.ARMS]
        recs.append(self.rec("flat", "pl_900|c9|1", "control", "Cas", False, value="gold-ish"))  # a rejected 'current'
        recs = [x for x in recs if not (x["arm"] == "flat" and x["unit"] == "pl_900|c9|1" and x["correct"])]
        self.write(r, "stage2.jsonl", recs)
        res = qa.score(self.root)["readers"][r]
        self.assertTrue(str(res["lines"]).startswith("withheld"))
        sheet = qa.AUDIT / f"{r}.json"
        data = json.loads(sheet.read_text())
        self.assertEqual(len(data["cases"]), 1)
        data["cases"][0]["verdict"] = "correct"
        sheet.write_text(json.dumps(data))
        res = qa.score(self.root)["readers"][r]
        r1 = next(l for l in res["lines"] if l["id"] == "R1")
        self.assertAlmostEqual(r1["mean"], 0.6)
        r3 = next(l for l in res["lines"] if l["id"] == "R3 oracle")
        self.assertAlmostEqual(r3["mean"], 0.0)  # the hand verdict made flat's control correct


class RetryingTests(unittest.TestCase):
    def test_transport_failures_retry_but_invalid_answers_do_not(self):
        calls = []

        class Flaky:
            name = "flaky"

            def answer(self, system, user):
                calls.append(1)
                if len(calls) < 3:
                    raise OSError("connection refused")
                return {"content": "not json", "exit_code": 0, "status": "SUCCESS"}

        r = qa.Retrying(Flaky(), sleep=lambda s: None)
        self.assertEqual(r.answer("s", "u")["content"], "not json")
        self.assertEqual(len(calls), 3)

        class Dead:
            name = "dead"

            def answer(self, system, user):
                return {"content": None, "exit_code": 1, "status": "ERROR"}

        with self.assertRaises(RuntimeError):
            qa.Retrying(Dead(), sleep=lambda s: None).answer("s", "u")


if __name__ == "__main__":
    unittest.main()
