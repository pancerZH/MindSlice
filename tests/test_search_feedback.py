"""Search feedback: ``unmatched_terms`` names the query words no card in scope contains, and changes no result."""

from __future__ import annotations

import sqlite3
import unittest

from mindslice import Workspace

from .helpers import WorkspaceTestCase, add_filler, card_text


class UnmatchedTermsTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        add_filler(self.ws)
        self.ws.write("deploy/rollback", title="Rollback", tags=["deploy"],
                      summary="Roll back by redeploying the previous image.", content="- Announce every rollback.")
        self.ws.write("deploy/canary", title="Canary releases", tags=["deploy"],
                      summary="A canary takes 5% of traffic for an hour.")
        self.ws.write("zh/rollback", title="回滚", summary="回滚就是重新部署上一个镜像。")

    def unmatched(self, query: str, **kw) -> list[str]:
        return self.ws.search(query, **kw)["unmatched_terms"]

    def test_a_typo_alone_finds_nothing_and_is_named(self):
        res = self.ws.search("rollbak")
        self.assertEqual((res["results"], res["unmatched_terms"]), ([], ["rollbak"]))
        self.assertNotIn("did_you_mean", res)  # spelling suggestions were evaluated and removed

    def test_only_the_words_that_match_nothing_are_reported(self):
        res = self.ws.search("rollback canray zebra")
        self.assertEqual(self.addresses(res)[:1], ["@overlay/deploy/rollback"])
        self.assertEqual(res["unmatched_terms"], ["canray", "zebra"])

    def test_fully_matched_queries_and_listings_report_nothing(self):
        for query in ("rollback", "canary traffic", "回滚", "previous image", "deplo*", ""):
            with self.subTest(query=query):
                self.assertEqual(self.unmatched(query), [])
        self.assertEqual(self.unmatched("", tags=["deploy"]), [])

    def test_words_are_reported_as_normalized_query_text(self):
        self.assertEqual(self.unmatched("ROLLBAK"), ["ROLLBAK"])
        self.assertEqual(self.unmatched("ｒｏｌｌｂａｋ"), ["rollbak"])
        self.assertEqual(self.unmatched("zzz*"), ["zzz"])

    def test_unspaced_runs_are_reported_whole(self):
        self.assertEqual(self.unmatched("账户口令"), ["账户口令"])
        self.assertEqual(self.unmatched("rollbak 回滚"), ["rollbak"])

    def test_scope_decides_what_counts_as_matched(self):
        self.project({"ops/pager": card_text("Pager", "Pagerduty escalation after ten minutes.")})
        res = self.ws.search("pagerduty rollback", source="@project")
        self.assertEqual(self.addresses(res), ["@project/ops/pager"])
        self.assertEqual(res["unmatched_terms"], ["rollback"])  # it occurs, but not in @project
        res = self.ws.search("canary rollback", tags=["deploy"])
        self.assertEqual(sorted(self.addresses(res)), ["@overlay/deploy/canary", "@overlay/deploy/rollback"])
        self.assertEqual(res["unmatched_terms"], [])
        self.assertEqual(self.unmatched("canary", tags=["gardening"]), ["canary"])

    def test_cache_from_the_suggestion_engine_is_cleaned_and_reindexed(self):
        self.ws.close()
        conn = sqlite3.connect(self.root / ".cache/index.sqlite")
        conn.execute("CREATE TABLE card_words(card_id INTEGER NOT NULL, word TEXT NOT NULL)")
        conn.execute("UPDATE meta SET value='2:unicode-15.0.0' WHERE key='analyzer'")
        conn.commit()
        conn.close()
        self.ws = Workspace(self.root)
        self.assertEqual(self.addresses(self.ws.search("rollback"))[:1], ["@overlay/deploy/rollback"])
        tables = {r[0] for r in self.ws.index.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("card_words", tables)


if __name__ == "__main__":
    unittest.main()
