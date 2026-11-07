"""The retrieval evaluation (evals/retrieval) as a regression guard.

It checks that the frozen data is intact, that the metrics mean what PLAN.md says, that comparison systems
patch the engine only while they run, and that the engine hasn't regressed against the recorded results.
"""

from __future__ import annotations

import json
import math
import unittest

from evals.retrieval import systems
from evals.retrieval.dataset import load_queries
from evals.retrieval.metrics import interval, mrr_at, ndcg_at, percentile, recall_at, resamples, verdict
from evals.retrieval.run import RESULTS, check, rank_all, summarize
from mindslice import index as index_module

TOLERANCE = 0.02  # nDCG@5 a split/language may lose against results/run.json before this test fails


class EvalDataTests(unittest.TestCase):
    def test_data_integrity_and_frozen_digests(self):
        self.assertEqual(check(), [])

    def test_splits_are_balanced(self):
        counts: dict[tuple[str, str], int] = {}
        for q in load_queries():
            counts[q.split, q.lang] = counts.get((q.split, q.lang), 0) + 1
        self.assertEqual(counts, {("dev", "en"): 20, ("dev", "zh"): 20, ("holdout", "en"): 20, ("holdout", "zh"): 20,
                                  ("limits", "en"): 5, ("limits", "zh"): 5, ("holdout-2", "en"): 30, ("holdout-2", "zh"): 30})


class MetricTests(unittest.TestCase):
    def test_ndcg_recall_mrr(self):
        rel = {"a": 2, "b": 1}
        self.assertEqual(ndcg_at(["a", "b"], rel, 5), 1.0)
        ideal = 2 + 1 / math.log2(3)
        self.assertAlmostEqual(ndcg_at(["b", "a"], rel, 5), (1 + 2 / math.log2(3)) / ideal)
        self.assertAlmostEqual(ndcg_at(["x", "a"], rel, 5), (2 / math.log2(3)) / ideal)
        self.assertEqual(ndcg_at(["x", "y"], rel, 5), 0.0)
        self.assertEqual(recall_at(["a", "x"], rel, 10), 0.5)
        self.assertEqual(mrr_at(["b", "x", "a"], rel, 10), 1 / 3)  # first grade-2 result
        self.assertEqual(mrr_at(["b"], rel, 10), 0.0)

    def test_bootstrap_and_verdicts(self):
        self.assertEqual(percentile([0, 10], 0.25), 2.5)
        mean, low, high = interval([1.0] * 10, resamples(10, replicates=50))
        self.assertEqual((mean, low, high), (1.0, 1.0, 1.0))
        self.assertEqual(resamples(5, 3), resamples(5, 3))  # fixed seed: reproducible
        self.assertEqual(verdict(0.9, 0.85, 0.8), "confirmed")
        self.assertEqual(verdict(0.9, 0.75, 0.8), "point pass")
        self.assertEqual(verdict(0.7, 0.6, 0.8), "miss")


class SystemTests(unittest.TestCase):
    def test_patches_are_scoped_to_the_run(self):
        original = (index_module.index_text, index_module.analyze_query, index_module.Index._rank)
        with systems.system("v1-baseline"):
            self.assertIsNot(index_module.index_text, original[0])
        self.assertEqual((index_module.index_text, index_module.analyze_query, index_module.Index._rank), original)
        with self.assertRaises(ValueError):
            with systems.system("nope"):
                pass

    def test_aliases_only_change_the_data_and_retry_rewrites_whole_words(self):
        from evals.retrieval.dataset import ALIASED, DATA

        self.assertEqual((systems.data_for("aliases"), systems.data_for("mindslice")), (ALIASED, DATA))
        self.assertEqual(systems._replace_words("how to rollbak token预算 now", {"rollbak": "rollback", "now": "today"}),
                         "how to rollback token预算 today")
        self.assertEqual(systems._replace_words("ＲＯＬＬＢＡＫ deploy", {"ROLLBAK": "rollback"}), "rollback deploy")
        self.assertEqual(systems._replace_words("rollbacks rollbak", {"rollbak": "rollback"}), "rollbacks rollback")


class RegressionTests(unittest.TestCase):
    def test_engine_has_not_regressed_against_recorded_results(self):
        recorded = json.loads((RESULTS / "run.json").read_text(encoding="utf-8"))["summary"]
        queries = load_queries()  # every split and corpus, including the tiny ones
        now = summarize(rank_all(queries, ("mindslice",)), ("mindslice",))
        for key, group in now.items():
            with self.subTest(group=key):
                current = group["systems"]["mindslice"]["ndcg@5"]["mean"]
                before = recorded[key]["systems"]["mindslice"]["ndcg@5"]["mean"]
                self.assertGreaterEqual(current, before - TOLERANCE,
                                        f"{key}: nDCG@5 fell from {before:.3f} to {current:.3f}; see evals/retrieval/PLAN.md")

    def test_ranking_is_deterministic(self):
        queries = [q for q in load_queries() if q.split == "dev"][:10]
        self.assertEqual(rank_all(queries, ("mindslice",)), rank_all(queries, ("mindslice",)))


if __name__ == "__main__":
    unittest.main()
