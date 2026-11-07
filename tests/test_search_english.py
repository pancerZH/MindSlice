"""End-to-end English search: matching rules, query safety, field weights and ranking."""

from __future__ import annotations

import unittest

from .helpers import WorkspaceTestCase, add_filler


class EnglishMatchingTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write(
            "e/cafe", title="Café naïve", tags=["Reliability"], aliases=["exception-policy"],
            summary="The running tokens expired at the café.",
            content="- Uses AppError and async_patterns, RFC 7807, v2.0; don't panic.\n- Retry after 15 minutes.",
        )

    def assert_finds(self, *queries: str) -> None:
        for q in queries:
            with self.subTest(query=q):
                res = self.ws.search(q)
                self.assertEqual(self.addresses(res)[:1], ["@overlay/e/cafe"])
                self.assertEqual(res["results"][0]["coverage"], 1.0)

    def test_case_diacritics_and_stemming(self):
        self.assert_finds("CAFÉ", "cafe", "Café", "naive", "NAÏVE")
        self.assert_finds("token", "TOKENS", "run", "runs", "expire", "expiration", "minute")

    def test_identifiers_numbers_and_punctuation_inside_words(self):
        self.assert_finds("AppError", "apperror", "async_patterns", "async patterns", "RFC 7807", "7807", "15 minutes")
        self.assert_finds("exception-policy", "exception policy", "reliability")

    def test_prefix_queries(self):
        self.assert_finds("app*", "toke*", "caf*")
        self.assertEqual(self.ws.search("zzz*")["total_matches"], 0)

    def test_fts_syntax_is_always_treated_as_text(self):
        for q in ['NOT AND OR', 'NEAR(token café)', 'title:token', '-token', '"token', 'token*)', '^run',
                  '(café)', '{x}', "token''", 'a"b', "col:", "token +run", "“smart” ‘quotes’ token"]:
            with self.subTest(query=q):
                self.ws.search(q)  # must never raise an FTS5 syntax error
        self.assertEqual(self.addresses(self.ws.search('title:token')), ["@overlay/e/cafe"])

    def test_empty_whitespace_and_punctuation_queries(self):
        listing = self.ws.search("")  # filter-only listing
        self.assertEqual((listing["total_matches"], listing["results"][0]["coverage"]), (1, 0.0))
        self.assertEqual(self.ws.search("   \t")["total_matches"], 1)
        for q in ("!!!", "*", "--", "()"):
            with self.subTest(query=q):
                self.assertEqual(self.ws.search(q)["total_matches"], 0)

    def test_path_words_are_searchable(self):
        self.ws.write("observability/structured-logging", title="Logs", summary="Nothing else here.")
        self.assertEqual(self.addresses(self.ws.search("observability")), ["@overlay/observability/structured-logging"])
        self.assertEqual(self.addresses(self.ws.search("structured logging")), ["@overlay/observability/structured-logging"])

    def test_duplicate_and_long_queries(self):
        self.assertEqual(self.ws.search("token token TOKEN")["results"][0]["coverage"], 1.0)
        long_query = " ".join(f"word{i}" for i in range(80)) + " token"
        res = self.ws.search(long_query)
        self.assertEqual(self.addresses(res), ["@overlay/e/cafe"])
        self.assertAlmostEqual(res["results"][0]["coverage"], 1 / 81, places=3)

    def test_k_zero_still_counts(self):
        res = self.ws.search("token", k=0)
        self.assertEqual((res["results"], res["total_matches"], res["next_offset"]), ([], 1, 0))


class EnglishRankingTests(WorkspaceTestCase):
    def test_field_weights_order_equal_coverage(self):
        add_filler(self.ws)
        common = {"summary": "A short neutral sentence about things.", "content": "- Another neutral statement here."}
        self.ws.write("w/title", title="Zephyr", **common)
        self.ws.write("w/alias", title="Card A", aliases=["zephyr"], **common)
        self.ws.write("w/tag", title="Card G", tags=["zephyr"], **common)
        self.ws.write("w/summary", title="Card S", summary="A short neutral zephyr sentence about things.",
                      content=common["content"])
        self.ws.write("w/body", title="Card B", summary=common["summary"], content="- Another neutral zephyr statement here.")
        self.assertEqual(self.addresses(self.ws.search("zephyr")),
                         ["@overlay/w/title", "@overlay/w/alias", "@overlay/w/tag", "@overlay/w/summary", "@overlay/w/body"])

    def test_more_query_words_beat_higher_bm25(self):
        for i in range(8):  # make "ttl" common (low IDF) so BM25 alone would favor the title-heavy card
            self.ws.write(f"filler/{i}", title=f"Filler {i}", summary=f"Gardening note {i} with a ttl.")
        self.ws.write("title-hit", title="Cache", summary="Cache cache cache.")
        self.ws.write("both", title="Notes", summary="Entries in the cache expire after the TTL elapses.")
        res = {r["address"]: r for r in self.ws.search("cache ttl", k=20)["results"]}
        top = self.ws.search("cache ttl")["results"][0]
        self.assertEqual((top["address"], top["coverage"]), ("@overlay/both", 1.0))
        self.assertEqual(res["@overlay/title-hit"]["coverage"], 0.5)
        self.assertGreater(res["@overlay/title-hit"]["score"], top["score"])

    def test_coverage_values_and_monotonic_order(self):
        add_filler(self.ws)
        self.ws.write("three", summary="alpha beta gamma.")
        self.ws.write("two", summary="alpha beta.")
        self.ws.write("one", summary="alpha.")
        res = self.ws.search("alpha beta gamma")
        self.assertEqual(self.addresses(res), ["@overlay/three", "@overlay/two", "@overlay/one"])
        self.assertEqual([r["coverage"] for r in res["results"]], [1.0, 0.667, 0.333])

    def test_precedence_breaks_exact_ties(self):
        self.mount_slice("kb", {"same": "+++\ntitle = \"Same\"\n+++\n\nIdentical walrus text.\n"}, "@kb", 50, "curated")
        self.put_overlay("same", "+++\ntitle = \"Same\"\n+++\n\nIdentical walrus text.\n")
        self.assertEqual(self.addresses(self.ws.search("walrus")), ["@overlay/same", "@kb/same"])


if __name__ == "__main__":
    unittest.main()
