"""Search feedback: ``unmatched_terms`` and ``did_you_mean`` describe the query and change no result."""

from __future__ import annotations

import sqlite3
import unittest

from mindslice import Workspace
from mindslice.lexical import edit_distance, surface_words

from .helpers import WorkspaceTestCase, add_filler, bump_mtime, card_text


class LexicalHelperTests(unittest.TestCase):
    def test_surface_words_are_unstemmed_spaced_script_words(self):
        words = surface_words("Roll back via `make_rollback`: ＪＷＴ, Café, v2, 2026, 回滚上线 ok")
        self.assertEqual(words, {"roll", "back", "via", "make", "rollback", "jwt", "café"})

    def test_edit_distance_counts_adjacent_swaps_once_and_stops_at_the_limit(self):
        self.assertEqual(edit_distance("rollbak", "rollback", 2), 1)
        self.assertEqual(edit_distance("canray", "canary", 2), 1)  # swap
        self.assertEqual(edit_distance("same", "same", 1), 0)
        self.assertEqual(edit_distance("kitten", "sitting", 2), 3)  # limit + 1
        self.assertEqual(edit_distance("ab", "abcdef", 2), 3)


class SearchFeedbackTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        add_filler(self.ws)
        self.ws.write("deploy/rollback", title="Rollback", tags=["deploy"],
                      summary="Roll back by redeploying the previous image.", content="- Announce every rollback.")
        self.ws.write("deploy/canary", title="Canary releases", tags=["deploy"],
                      summary="A canary takes 5% of traffic for an hour.")
        self.ws.write("zh/rollback", title="回滚", summary="回滚就是重新部署上一个镜像。")

    def feedback(self, query: str, **kw) -> tuple[list[str], dict[str, list[str]]]:
        res = self.ws.search(query, **kw)
        return res["unmatched_terms"], res["did_you_mean"]

    def test_typo_gets_a_suggestion_that_finds_the_card(self):
        res = self.ws.search("rollbak")
        self.assertEqual(res["results"], [])
        self.assertEqual((res["unmatched_terms"], res["did_you_mean"]), (["rollbak"], {"rollbak": ["rollback"]}))
        self.assertEqual(self.addresses(self.ws.search(res["did_you_mean"]["rollbak"][0]))[:1], ["@overlay/deploy/rollback"])

    def test_only_the_words_that_match_nothing_are_reported(self):
        res = self.ws.search("rollback canray zebra")
        self.assertEqual(self.addresses(res)[:1], ["@overlay/deploy/rollback"])
        self.assertEqual(res["unmatched_terms"], ["canray", "zebra"])
        self.assertEqual(res["did_you_mean"], {"canray": ["canary"]})

    def test_fully_matched_queries_and_listings_report_nothing(self):
        for query in ("rollback", "canary traffic", "回滚", "previous image", ""):
            with self.subTest(query=query):
                self.assertEqual(self.feedback(query), ([], {}))
        self.assertEqual(self.feedback("", tags=["deploy"]), ([], {}))

    def test_case_and_width_are_normalized_and_the_key_is_the_query_word(self):
        self.assertEqual(self.feedback("ROLLBAK"), (["ROLLBAK"], {"ROLLBAK": ["rollback"]}))
        self.assertEqual(self.feedback("ｒｏｌｌｂａｋ"), (["rollbak"], {"rollbak": ["rollback"]}))

    def test_unspaced_runs_are_reported_whole_without_suggestions(self):
        self.assertEqual(self.feedback("账户口令"), (["账户口令"], {}))
        self.assertEqual(self.feedback("rollbak 回滚"), (["rollbak"], {"rollbak": ["rollback"]}))

    def test_short_words_numbers_and_prefixes_get_no_suggestions(self):
        self.assertEqual(self.feedback("zq"), (["zq"], {}))
        self.assertEqual(self.feedback("4096"), (["4096"], {}))
        self.assertEqual(self.feedback("rollbak*"), (["rollbak"], {}))

    def test_suggestions_respect_the_search_scope(self):
        other = self.project({"ops/pager": card_text("Pager", "Pagerduty escalation after ten minutes.")})
        self.assertTrue(other.exists())
        self.assertEqual(self.feedback("pagrduty")[1], {"pagrduty": ["pagerduty"]})
        self.assertEqual(self.feedback("pagrduty", source="@overlay")[1], {})
        self.assertEqual(self.feedback("rollbak", source="@project")[1], {})
        self.assertEqual(self.feedback("canray", tags=["deploy"])[1], {"canray": ["canary"]})
        self.assertEqual(self.feedback("canray", tags=["gardening"])[1], {})

    def test_scoped_searches_still_match_and_report_per_scope(self):
        self.project({"ops/pager": card_text("Pager", "Pagerduty escalation after ten minutes.")})
        res = self.ws.search("pagerduty rollback", source="@project")
        self.assertEqual(self.addresses(res), ["@project/ops/pager"])
        self.assertEqual(res["unmatched_terms"], ["rollback"])  # it occurs, but not in @project
        res = self.ws.search("canary rollback", tags=["deploy"])
        self.assertEqual(sorted(self.addresses(res)), ["@overlay/deploy/canary", "@overlay/deploy/rollback"])
        self.assertEqual(res["unmatched_terms"], [])

    def test_closest_first_then_most_frequent(self):
        self.ws.write("a/one", title="Paged one", summary="Paged once.")
        self.ws.write("a/two", title="Paged two", summary="Paged twice.")
        self.ws.write("a/three", title="Pages", summary="Three pages.")
        self.assertEqual(self.feedback("pagex")[1], {"pagex": ["paged", "pages"]})

    def test_vocabulary_follows_edits_and_deletions_on_disk(self):
        file = self.overlay_file("deploy/canary")
        file.write_text(card_text("Canary releases", "A canary takes 5% of traffic; watch the dashboards."),
                        encoding="utf-8")
        bump_mtime(file)
        self.assertEqual(self.feedback("dashbords")[1], {"dashbords": ["dashboards"]})
        self.ws.write("deploy/rollback", op="delete")
        self.ws.write("zh/rollback", op="delete")
        self.assertEqual(self.feedback("rollbak"), (["rollbak"], {}))

    def test_index_built_before_the_vocabulary_existed_is_rebuilt(self):
        self.ws.close()
        conn = sqlite3.connect(self.root / ".cache/index.sqlite")
        conn.execute("DELETE FROM card_words")
        conn.execute("UPDATE meta SET value='1:unicode-15.0.0' WHERE key='analyzer'")
        conn.commit()
        conn.close()
        self.ws = Workspace(self.root)
        self.assertEqual(self.feedback("rollbak")[1], {"rollbak": ["rollback"]})


if __name__ == "__main__":
    unittest.main()
