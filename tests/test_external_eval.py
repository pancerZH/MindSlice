"""The external-benchmark harness (evals/external): compilers, card rendering, lineage checks, metrics.

Everything here runs on small synthetic datasets written in the benchmarks' own formats, so it needs no
download. ``ExternalDataTests`` additionally verifies the real files and the Parquet decoding when the
data directory holds them, and skips otherwise.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evals.external import hints, sources
from evals.external.corpus import Card, Session, Turn, add_files, address, make_card, round_cards, rounds, summary_line
from evals.external.datasets import (fact_values, label_fact, locomo, longmemeval, meme, normalize_text, normalize_value,
                                     subject_anchors, words)
from evals.external.harness import run_in_tmp
from evals.external.checks import CHECKS
from evals.external.parquet import rle_hybrid, snappy_decompress
from evals.external.run import STATE_GRANULARITY, jobs_for, summarize
from evals.external.score import auroc, auroc_ci, levels, state
from mindslice import Workspace


def _write(root: Path, key: str, data) -> None:
    p = sources.path_of(key, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _conv(*user_lines: str) -> list[dict]:
    out = [{"role": "assistant", "content": "Hi! How can I help you today?"}]
    for line in user_lines:
        out += [{"role": "user", "content": line}, {"role": "assistant", "content": "Noted."}]
    return out


def _fact(entity, value, turn, **kw):
    return {"entity": entity, "value": value, "fact_text": value, "conveyed_in_turn": turn, "conveyed": True, **kw}


def meme_episode() -> dict:
    """A small MEME episode: a root change with 1- and 2-hop dependents, a deletion, a 3-step history."""
    s0 = {"session_id": "evidence_a", "type": "evidence", "timestamp": "2023/03/01 (Wed) 10:00",
          "conversation": _conv("My health condition is lactose intolerance.", "I drive a Zyvanta Sedan.",
                                "My partner's name is James.", "I take Quelmithin because of my lactose intolerance.",
                                "My regular appointment is tutoring, because of my lactose intolerance.",
                                "My exercise routine is swimming, because of my lactose intolerance.",
                                "I work out at Crysthene Pool for my swimming.",
                                "If my health condition changes, my medication will switch to multivitamin.",
                                "If my health condition changes, my exercise routine will be cycling.",
                                "If my exercise routine changes, I will work out at Velthari Studio.",
                                "I bought James a watch for our anniversary."),
          "gold_facts": [_fact("health_condition", "lactose intolerance", 1), _fact("vehicle", "Zyvanta Sedan", 3),
                         _fact("partner", "James", 5),
                         _fact("medication", "Quelmithin", 7, has_dependency=True, dependency_source="health_condition"),
                         _fact("regular_appointment", "tutoring", 9, has_dependency=True, dependency_source="health_condition"),
                         _fact("exercise_routine", "swimming", 11, has_dependency=True, dependency_source="health_condition"),
                         _fact("fitness_facility", "Crysthene Pool", 13, has_dependency=True, dependency_source="exercise_routine"),
                         _fact("medication", "multivitamin", 15, has_dependency=True, dependency_source="health_condition", is_if_then=True),
                         _fact("exercise_routine", "cycling", 17, has_dependency=True, dependency_source="health_condition", is_if_then=True),
                         _fact("fitness_facility", "Velthari Studio", 19, has_dependency=True, dependency_source="exercise_routine", is_if_then=True),
                         _fact("anniversary_gift", "watch", 21, has_dependency=True, dependency_source="partner")]}
    filler = {"session_id": "sharegpt_1", "type": "filler", "timestamp": "2023/03/02 (Thu) 10:00",
              "conversation": _conv("Can you suggest a pasta recipe?", "What about a soup for winter?")}
    s1 = {"session_id": "evidence_b", "type": "evidence", "timestamp": "2023/03/03 (Fri) 10:00",
          "conversation": _conv("Update: I drive a Therwyn Compact now.", "Now I drive a Xylorim Scooter."),
          "gold_facts": [_fact("vehicle", "Therwyn Compact", 1), _fact("vehicle", "Xylorim Scooter", 3)]}
    s2 = {"session_id": "evidence_change+delete_event", "type": "evidence", "timestamp": "2023/03/04 (Sat) 10:00",
          "conversation": _conv("My lactose intolerance is resolved, but I was diagnosed with high blood pressure.",
                                "My partner is James. Please remove that from your memory."),
          "gold_facts": [_fact("health_condition", "high blood pressure", 1, type="root_change"),
                         _fact("partner", "James", 3, type="delete")]}
    q = lambda task, entity, text, **kw: {"task_type": task, "entity": [entity], "question": text, **kw}
    return {"episode_id": "pl_900", "domain": "personal_life", "root": "health_condition",
            "dependency_edges_used": [{"source": "health_condition", "target": "medication", "hop": 1},
                                      {"source": "health_condition", "target": "regular_appointment", "hop": 1},
                                      {"source": "health_condition", "target": "exercise_routine", "hop": 1},
                                      {"source": "exercise_routine", "target": "fitness_facility", "hop": 2}],
            "sessions": [s0, filler, s1, s2],
            "before_questions": {"position_after_session": 2, "questions": [q("Cas", "medication", "What medication am I taking?", hop=1)]},
            "after_questions": {"position_after_session": 3, "questions": [
                q("Cas", "medication", "What medication am I taking?", hop=1),
                q("Cas", "fitness_facility", "Where do I work out?", hop=2),
                q("Abs", "regular_appointment", "What regular appointments do I have?", hop=1),
                q("Del", "partner", "What's my partner's name?"),
                q("Tr", "vehicle", "List all vehicles I've had over time, from earliest to latest.")]}}


class CardTests(unittest.TestCase):
    def test_rounds_and_rendering_match_write(self):
        turns = (Turn("Assistant", "Hi!", "a", "assistant"), Turn("User", "1. My [[odd]] list\n  - item", "b", "user"),
                 Turn("Assistant", "Sure.", "c", "assistant"), Turn("User", "Next.", "d", "user"))
        self.assertEqual([[t.ref for t in r] for r in rounds(turns)], [["a", "b", "c"], ["d"]])
        cards = round_cards([Session("x", "2023/01/01", turns)])
        self.assertEqual(cards[0].summary, "My [ [odd]] list - item")  # markup can't turn it into a list
        self.assertNotIn("[[", cards[0].render())
        with tempfile.TemporaryDirectory() as tmp:
            bulk, api = Workspace.init(Path(tmp) / "a"), Workspace.init(Path(tmp) / "b")
            try:
                add_files(bulk, cards)
                for c in cards:
                    api.write(c.path, op="create", **c.write_args())
                for c in cards:
                    self.assertEqual((bulk.table().overlay.root / f"{c.path}.md").read_bytes(),
                                     (api.table().overlay.root / f"{c.path}.md").read_bytes())
                self.assertEqual(bulk.validate()["errors"], [])
                self.assertIsNone(bulk.read(address(cards[0])).get("links"))  # no accidental wikilink
            finally:
                bulk.close()
                api.close()

    def test_summary_line(self):
        self.assertEqual(summary_line("## Heading\nmore"), "Heading more")
        self.assertEqual(summary_line("> - quoted"), "quoted")
        self.assertLessEqual(len(summary_line("word " * 100)), 240)

    def test_paths_sort_chronologically(self):
        sessions = [Session(str(i), "", (Turn("A", f"t{i}", f"{i}#0"),)) for i in range(1200)]
        paths = [c.path for c in round_cards(sessions)]
        self.assertEqual(paths, sorted(paths))


class CompilerTests(unittest.TestCase):
    def test_meme_judgments_and_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "meme-filler32k", [meme_episode()])
            (h,) = list(meme("meme-filler32k", Path(tmp)))
        q = {x.id: x for x in h.questions}
        self.assertEqual(q["pl_900/before0"].gold, {"0#7"})  # pre-change value only
        self.assertEqual(q["pl_900/before0"].at_session, 2)
        self.assertEqual(q["pl_900/after0"].gold, {"0#7", "0#15", "0#1", "3#1"})  # chain up to the root
        self.assertEqual(q["pl_900/after1"].gold, {"0#13", "0#19", "0#11", "0#17", "0#1", "3#1"})  # 2 hops
        self.assertEqual(q["pl_900/after4"].meta["history"], ["0#3", "2#1", "2#3"])
        lin = h.lineage
        self.assertEqual(lin.supersedes, {"2#1": ["0#3"], "2#3": ["2#1"], "3#1": ["0#1"]})
        self.assertEqual(lin.deletes, {"3#3": ["0#5"]})
        self.assertEqual(lin.extends["0#15"], ["0#7"])  # the rule extends the dependent
        self.assertEqual(lin.extends["0#13"], ["0#11"])  # the 2-hop dependent extends the middle

    def test_meme_lineage_run_passes_every_structural_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "meme-filler32k", [meme_episode()])
            (h,) = list(meme("meme-filler32k", Path(tmp)))
        self.assertEqual([(g, l) for _, g, l in jobs_for(h)], [("session", False), ("round", False), ("round", True)])
        records, _, rows = run_in_tmp(h, "round", True, CHECKS["meme-filler32k"])
        failed = [r for r in rows if not r["ok"] and r["check"] != "e2e"]
        self.assertEqual(failed, [])
        checks = {r["check"] for r in rows}
        self.assertTrue({"root-forwarding", "root-unrebased", "dependent-flagged", "rule-attached", "no-rule",
                         "deleted-unreadable", "deleted-never-returned", "dependent-of-deleted-flagged",
                         "history-chain", "history-forwarding"} <= checks)
        by = {r["id"]: r for r in records}
        # Deletion: the deleted card is gone, the request was not stored.
        self.assertNotIn("@overlay/s000/r002", by["pl_900/after3"]["ranked"])
        # Tracking: results collapse onto the latest value, naming the history it absorbed.
        tr = by["pl_900/after4"]
        self.assertIn("@overlay/s002/r001", tr["ranked"])
        self.assertTrue(any("@overlay/s000/r001" in v for v in tr["via"]))
        # Dependents are flagged in their search previews at 1 and 2 hops (the extends closure, as in read()).
        e2e = {r["group"]: r for r in rows if r["check"] == "e2e"}
        self.assertTrue(e2e["Cas-hop1"]["preview_flag"])
        self.assertTrue(e2e["Cas-hop2"]["preview_flag"])
        self.assertTrue(e2e["Cas-hop2"]["read_flag"])
        flat, _, _ = run_in_tmp(h, "round", False)
        self.assertEqual(sum(1 for r in flat if r["id"] == "pl_900/before0"), 1)
        summary = summarize(flat + records, rows)
        self.assertIn("meme/Cas-hop1", summary["ablation"]["groups"])

    def test_longmemeval_knowledge_update(self):
        sess = lambda sid, text, has: [{"role": "user", "content": text, **({"has_answer": True} if has else {})},
                                        {"role": "assistant", "content": "ok"}]
        data = [{"question_id": "q1", "question_type": "knowledge-update", "question": "What is my 5K personal best?",
                 "question_date": "2023/06/01", "answer": "25:50",
                 "answer_session_ids": ["answer_x_2", "answer_x_1"],
                 "haystack_session_ids": ["answer_x_2", "noise", "answer_x_1"],
                 "haystack_dates": ["2023/05/30 (Tue) 10:00", "2023/05/01 (Mon) 10:00", "2023/05/20 (Sat) 10:00"],
                 "haystack_sessions": [sess("a", "My new 5K personal best is 25:50.", True),
                                       sess("n", "Tell me about the weather.", False),
                                       sess("b", "My 5K personal best is 27:12.", True)]},
                {"question_id": "q2_abs", "question_type": "single-session-user", "question": "What is my hamster called?",
                 "question_date": "2023/06/01", "answer": "not mentioned", "answer_session_ids": ["noise"],
                 "haystack_session_ids": ["noise"], "haystack_dates": ["2023/05/01 (Mon) 10:00"],
                 "haystack_sessions": [sess("n", "My cat is Luna.", False)]}]
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "longmemeval-s", data)
            h1, h2 = list(longmemeval(Path(tmp)))
        self.assertEqual([s.ref for s in h1.sessions], ["noise", "answer_x_1", "answer_x_2"])  # by date
        self.assertEqual(h1.lineage.supersedes, {"answer_x_2#0": ["answer_x_1#0"]})
        self.assertFalse(h2.questions[0].answerable)
        flat, _, _ = run_in_tmp(h1, "round", False)
        lin, _, rows = run_in_tmp(h1, "round", True, CHECKS["longmemeval-s"])
        self.assertEqual([r["ok"] for r in rows], [True])
        self.assertEqual(lin[0]["ranked"][0], "@overlay/s002/r000")
        self.assertEqual(state(lin[0])["stale@10"], 0.0)
        self.assertEqual(state(flat[0])["stale@10"], 1.0)
        self.assertTrue(all(a.startswith("@overlay/s") for a in flat[0]["ranked"]))  # ids never reach a path

    def test_locomo_evidence(self):
        data = [{"sample_id": "conv-1", "conversation": {
            "speaker_a": "Caroline", "speaker_b": "Melanie", "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [{"speaker": "Caroline", "dia_id": "D1:1", "text": "I went to a support group."},
                          {"speaker": "Melanie", "dia_id": "D1:2", "text": "I painted a sunrise.", "blip_caption": "a painting"}]},
            "qa": [{"question": "When did Caroline go to the support group?", "answer": "7 May", "evidence": ["D1:1"], "category": 2},
                   {"question": "What did Caroline paint?", "adversarial_answer": "sunrise", "evidence": ["D1:2", "D9:9"], "category": 5}]}]
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "locomo", data)
            (h,) = list(locomo(Path(tmp)))
        self.assertEqual(h.info["dropped_evidence_ids"], 1)
        self.assertEqual([q.category for q in h.questions], ["temporal", "adversarial"])
        self.assertFalse(h.questions[1].answerable)
        recs, b, _ = run_in_tmp(h, "turn", False)
        self.assertIn("shared an image: a painting", b.cards[1].render())
        self.assertEqual(recs[0]["ranked"][0], "@overlay/s000/t000")
        self.assertEqual(levels(recs[0])["card"]["mrr@10"], 1.0)

    def test_mab_label_rule(self):
        facts = {0: "The capital of Romania is Bucharest.", 1: "London is located in the continent of Europe.",
                 2: "The capital of Romania is Rajanpur.", 3: "Paris is the capital of France."}
        self.assertEqual(label_fact("What is the capital of Romania?", ["Rajanpur"], facts)[:2], (2, "labeled"))
        self.assertEqual(label_fact("What is the capital of Peru?", ["Lima"], facts)[1], "no fact ends with an answer")


class ValueExportTests(unittest.TestCase):
    """agent_test.md 6.1: each question's units also as normalized value strings."""

    def test_normalization(self):
        self.assertEqual(normalize_value("  Quelmithin. "), "quelmithin")
        self.assertEqual(normalize_value("“Xelvari  Dawn,”"), "xelvari dawn")
        self.assertEqual(normalize_value("The Quorath Codex (book)"), "the quorath codex (book)")  # brackets stay
        self.assertEqual(normalize_value("Jen’s —"), "jen's")
        self.assertEqual(normalize_value("ＡBC"), "abc")  # NFKC
        self.assertEqual(normalize_text("I  drive\na  Zyvanta Sedan."), "i drive a zyvanta sedan.")

    def test_meme_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "meme-filler32k", [meme_episode()])
            (h,) = list(meme("meme-filler32k", Path(tmp)))
        v = {x.id: x.meta["values"] for x in h.questions}
        self.assertEqual(v["pl_900/before0"], {"current": ["quelmithin"]})  # the pre-change value is current
        self.assertEqual(v["pl_900/after0"], {"stale": ["quelmithin"], "current": ["multivitamin"]})
        self.assertEqual(v["pl_900/after1"], {"stale": ["crysthene pool"], "current": ["velthari studio"]})
        self.assertEqual(v["pl_900/after2"], {"stale": ["tutoring"], "current": []})
        self.assertEqual(v["pl_900/after3"], {"stale": ["james"], "deleted": ["james"]})
        self.assertEqual(v["pl_900/after4"], {"history": ["zyvanta sedan", "therwyn compact", "xylorim scooter"]})
        timeline = {e["unit"]: e for e in h.info["timeline"]}
        self.assertEqual(timeline["0#15"], {"entity": "medication", "unit": "0#15", "session": 0, "kind": "rule",
                                            "value": "multivitamin", "source": "health_condition"})
        self.assertEqual(timeline["3#1"]["kind"], "value")
        self.assertEqual(timeline["3#3"]["kind"], "delete")
        self.assertIsNone(timeline["0#3"]["source"])
        self.assertEqual([e["unit"] for e in h.info["timeline"]],
                         sorted(timeline, key=lambda u: tuple(map(int, u.split("#")))))  # chronological

    def test_mab_values_and_anchors(self):
        facts = {0: "The capital of Romania is Bucharest.", 1: "Bucharest is located in the continent of Europe.",
                 2: "The capital of Romania is Rajanpur.", 3: "The capital of France is Paris.",
                 4: "Paris is located in the continent of Europe."}
        df = Counter(w for t in facts.values() for w in set(words(t)))
        n, _, prefix = label_fact("What is the capital of Romania?", ["Rajanpur"], facts)
        self.assertEqual(prefix, "The capital of Romania is")
        v = fact_values(facts, n, prefix, [0], [], df)
        self.assertEqual(v, {"current": ["rajanpur"], "stale": ["bucharest"], "anchors": ["romania"], "latest": True})
        self.assertNotIn("stale", fact_values(facts, 0, prefix, [], [2], df))  # not the latest: no stale value
        # No prefix word is rare enough (5 facts: at most 0.05 each): the rarest ones name the subject.
        self.assertEqual(subject_anchors("Paris is located in the continent of", df, len(facts)),
                         ["paris", "located", "continent"])

    def test_longmemeval_current_value(self):
        data = [{"question_id": "q1", "question_type": "knowledge-update", "question": "What is my 5K best?",
                 "question_date": "2023/06/01", "answer": "25:50.", "answer_session_ids": ["a"],
                 "haystack_session_ids": ["a"], "haystack_dates": ["2023/05/30 (Tue) 10:00"],
                 "haystack_sessions": [[{"role": "user", "content": "My 5K best is 25:50.", "has_answer": True}]]}]
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "longmemeval-s", data)
            (h,) = list(longmemeval(Path(tmp)))
        self.assertEqual(h.questions[0].meta["values"], {"current": ["25:50"]})


class AblationPairingTests(unittest.TestCase):
    def test_flat_partner_comes_from_the_same_dataset(self):
        """MEME's filler32k and nofiller share question ids; a lineage record pairs with its own dataset's flat one."""
        def rec(dataset, variant, ranked):
            return {"dataset": dataset, "haystack": f"{dataset}/pl_1", "id": "pl_1/after0", "category": "Cas-hop1",
                    "granularity": "round", "variant": variant, "answerable": True, "phase": "after", "task": "Cas",
                    "ranked": ranked, "warned": [False] * len(ranked), "via": [[] for _ in ranked],
                    "stale": ["@overlay/s"], "current": ["@overlay/c"], "gold": [], "gold_sessions": [], "sessions": []}
        records = [rec("meme-filler32k", "flat", ["@overlay/s", "@overlay/c"]),
                   rec("meme-filler32k", "lineage", ["@overlay/c"]),
                   rec("meme-nofiller", "flat", ["@overlay/c", "@overlay/s"])]
        from evals.external.run import summarize_ablation

        group = summarize_ablation(records)["groups"]["meme/Cas-hop1"]["metrics"]
        self.assertEqual(group["stale-first"]["flat"]["mean"], 1.0)  # filler32k's flat page, not nofiller's


class MetricTests(unittest.TestCase):
    def test_auroc(self):
        self.assertEqual(auroc([3, 4], [1, 2]), 1.0)
        self.assertEqual(auroc([1, 2], [3, 4]), 0.0)
        self.assertEqual(auroc([1, 1], [1, 1]), 0.5)
        self.assertAlmostEqual(auroc([0.9, 0.4], [0.5, 0.1]), 0.75)
        ci = auroc_ci([0.9, 0.8, 0.7], [0.1, 0.2], replicates=50)
        self.assertEqual((ci["mean"], ci["low"], ci["high"]), (1.0, 1.0, 1.0))
        self.assertTrue(math.isnan(auroc([], [1.0])))

    def test_state_metrics(self):
        rec = {"ranked": ["s", "c", "x"], "warned": [False, False, False], "stale": ["s"], "current": ["c"]}
        self.assertEqual(state(rec), {"stale@10": 1.0, "current@10": 1.0, "stale-first": 1.0})
        rec["warned"] = [True, False, False]  # flagged in its preview: not a silent intrusion
        self.assertEqual(state(rec)["stale-first"], 0.0)

    def test_snappy_and_rle(self):
        # Literal "abc", then a 1-byte-offset copy of length 4 at offset 3 (overlapping): "abcabca".
        self.assertEqual(snappy_decompress(bytes([7, 0b1000, 97, 98, 99, 0b00000001, 3])), b"abcabca")
        # RLE run of 3 x value 5 (bit width 3), then a bit-packed group of 8 values 0..7.
        packed = (sum(v << (3 * i) for i, v in enumerate(range(8)))).to_bytes(3, "little")
        data = bytes([3 << 1, 5, 1 << 1 | 1]) + packed
        self.assertEqual(rle_hybrid(data, 0, len(data), 3, 11), [5, 5, 5, 0, 1, 2, 3, 4, 5, 6, 7])


class HintTests(unittest.TestCase):
    """Mode C (PLAN.md): probes replay Mode B ingestion; scoring follows the pre-registered selection rule."""

    def test_probes_cover_every_lineage_write_once_in_harness_order(self):
        self.assertEqual(hints.GRANULARITY_OF, STATE_GRANULARITY)
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "meme-filler32k", [meme_episode()])
            (h,) = list(meme("meme-filler32k", Path(tmp)))
        with tempfile.TemporaryDirectory() as tmp:
            dev = hints.probe_haystack(h, "dev", Path(tmp) / "a")
            holdout = hints.probe_haystack(h, "holdout", Path(tmp) / "b")
        recs = dev + holdout
        self.assertTrue(all(r["split"] == "dev" for r in dev) and all(r["split"] == "holdout" for r in holdout))
        by = {r["path"]: r for r in recs}
        self.assertEqual(len(by), len(recs))
        g = hints.groups(recs)
        # Every supersedes write is a positive (2 Tracking steps, the root change); every extends-only write
        # (dependents and if-then rules) is in the extends group; the deletion request is never probed.
        self.assertEqual(sorted(r["path"] for r in g["positive"]), ["s002/r000", "s002/r001", "s003/r000"])
        self.assertEqual(by["s002/r001"]["predecessors"], ["@overlay/s002/r000"])
        self.assertTrue(all(r["baselines"] and not r["predecessors"] for r in g["extends"]))
        self.assertTrue(all(not (r["predecessors"] or r["baselines"]) for r in g["plain"]))
        for r in recs:
            self.assertEqual(set(r["probes"]), set(hints.VARIANTS))
            self.assertTrue(all(c["address"] != f"@overlay/{r['path']}" for v in r["probes"].values() for c in v))
        # Probed before the write: the second Tracking step finds the first, which is still active.
        self.assertIn("@overlay/s002/r000", [c["address"] for c in by["s002/r001"]["probes"]["summary"]])

    def test_query_drops_date_line(self):
        card = make_card("s000/r000", [Turn("User", "My 5K best is 25:10.", "0#0", role="user")], "2023/05/01", "0")
        self.assertEqual(hints.query_text(card, "summary"), "My 5K best is 25:10.")
        self.assertNotIn("2023/05/01", hints.query_text(card, "full"))
        self.assertIn("User: My 5K best is 25:10.", hints.query_text(card, "full"))

    @staticmethod
    def _rec(group, cands, pred=(), base=(), dataset="d"):
        probe = [{"address": a, "coverage": c, "score": 1.0} for a, c in cands]
        return {"dataset": dataset, "group": group, "predecessors": list(pred), "baselines": list(base),
                "probes": {"full": probe, "summary": probe}}

    def test_hint_threshold_and_top3(self):
        r = self._rec("positive", [("a", 0.2), ("b", 0.5), ("c", 0.4), ("p", 0.9)], pred=["p"])
        self.assertEqual(hints.hinted(r, "full", 0.40), ["b", "c"])  # only the top 3 may be named
        self.assertEqual(hints.at_k(r, "full", 3), 0.0)
        self.assertEqual(hints.found(r, "full", 0.0), 0.0)
        self.assertEqual(hints.hinted(r, "full", 0.5), ["b"])  # rounded coverage meets the threshold exactly

    def test_selection_rule(self):
        pos = [self._rec("positive", [("p", 0.6)], pred=["p"]), self._rec("positive", [("q", 0.3)], pred=["q"])]
        plain = [self._rec("plain", [("x", 0.35)])] + [self._rec("plain", [("y", 0.1)]) for _ in range(9)]
        choice = hints.select(pos + plain)
        # t <= 0.10 fires on all 10 plain writes (over the cap); 0.15-0.35 fires on 1 of 10 (allowed). Recall is
        # 1.0 up to t = 0.30 (q's coverage) and 0.5 at 0.35, so the rule keeps recall 1.0 at the highest t, 0.30.
        self.assertTrue(choice["qualified"])
        self.assertEqual((choice["variant"], choice["t"], choice["dev_recall"]), ("full", 0.30, 1.0))
        none = hints.select(pos + [self._rec("plain", [("x", 0.99)])])
        self.assertFalse(none["qualified"])
        lines = hints.read_lines(pos + plain, none)
        self.assertEqual([l["verdict"] for l in lines[1:]], ["miss (by rule)"] * 2)

    def test_h2b_is_lower_is_better(self):
        pos = [self._rec("positive", [("p", 0.9)], pred=["p"]) for _ in range(5)]
        quiet = [self._rec("plain", [("x", 0.1)]) for _ in range(50)]
        lines = {l["id"]: l for l in hints.read_lines(pos + quiet, {"qualified": True, "variant": "full", "t": 0.5})}
        self.assertEqual(lines["H2b"]["stat"]["mean"], 0.0)
        self.assertEqual(lines["H2b"]["verdict"], "confirmed")
        self.assertEqual(lines["H1"]["verdict"], "confirmed")


class ExternalDataTests(unittest.TestCase):
    def test_pinned_files_and_parquet_decoding(self):
        present = [k for k in sources.SOURCES if sources.path_of(k).is_file()]
        if not present:
            self.skipTest("external datasets not fetched (python -m evals.external fetch)")
        self.assertEqual(sources.problems(keys=tuple(present)), [])


if __name__ == "__main__":
    unittest.main()
