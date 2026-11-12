"""Unit tests for mindslice.retrieval.lexical (text analysis feeding the FTS5 index).

Chinese and English are covered exhaustively; other unspaced scripts get compact checks.
"""

from __future__ import annotations

import unittest

from mindslice.retrieval.lexical import analyze_query, analyzer_signature, fold, index_text, normalize

from .helpers import WorkspaceTestCase


def tokens(text: str) -> list[str]:
    return index_text(text).split()


def terms(query: str) -> list[tuple[str, ...]]:
    return [u.terms for u in analyze_query(query).units]


class ChineseAnalysisTests(unittest.TestCase):
    def test_run_becomes_unigrams_then_contiguous_bigrams(self):
        self.assertEqual(tokens("令牌过期"), ["令", "牌", "过", "期", "令牌", "牌过", "过期"])
        self.assertEqual(tokens("猫"), ["猫"])
        self.assertEqual(tokens("哈哈哈"), ["哈", "哈", "哈", "哈哈", "哈哈"])

    def test_boundaries_with_latin_digits_punctuation_and_emoji(self):
        self.assertEqual(tokens("JWT过期15分钟"), ["JWT", "过", "期", "过期", "15", "分", "钟", "分钟"])
        self.assertEqual(tokens("用uv管理"), ["用", "uv", "管", "理", "管理"])
        self.assertEqual(tokens("第3章"), ["第", "3", "章"])
        self.assertEqual(tokens("令牌，过期。"), ["令", "牌", "令牌", ",", "过", "期", "过期", "。"])
        self.assertEqual(tokens("“令牌”《过期》"), ["“", "令", "牌", "令牌", "”《", "过", "期", "过期", "》"])
        self.assertEqual(tokens("令牌🔑过期"), ["令", "牌", "令牌", "🔑", "过", "期", "过期"])

    def test_normalization(self):
        self.assertEqual(index_text("ＪＷＴ　１５"), "JWT 15")  # full-width ASCII + ideographic space
        self.assertEqual(tokens("１５分钟"), tokens("15分钟"))
        self.assertEqual(tokens("令​牌"), tokens("令牌"))  # zero-width space
        self.assertEqual(tokens("葛\U000e0100城"), tokens("葛城"))  # ideographic variation selector
        self.assertEqual(tokens("⾦"), tokens("金"))  # Kangxi radical folds to the unified ideograph
        self.assertEqual(normalize("令牌"), "令牌")

    def test_rare_and_traditional_ideographs(self):
        self.assertIn("𠮷野", tokens("𠮷野家"))  # supplementary plane (U+20BB7) is one unit
        self.assertIn("認證", tokens("認證流程"))
        self.assertIn("々", tokens("時々"))

    def test_query_plans(self):
        plan = analyze_query("雾凇拼音")
        self.assertEqual(terms("雾凇拼音"), [('"雾凇"', '"凇拼"', '"拼音"')])
        self.assertEqual(plan.units[0].phrase, '"雾凇 凇拼 拼音"')
        self.assertIsNone(analyze_query("过期").units[0].phrase)
        self.assertEqual(terms("猫"), [('"猫"',)])
        self.assertEqual(terms("令牌 过期"), [('"令牌"',), ('"过期"',)])
        self.assertEqual(terms("令牌，过期。"), terms("令牌 过期"))
        self.assertEqual(terms("“令牌”"), terms("令牌"))
        self.assertEqual(terms("过期*"), terms("过期"))  # prefix star is meaningless on n-grams
        self.assertEqual(terms("JWT过期"), [('"JWT"',), ('"过期"',)])
        self.assertEqual(terms("过期JWT"), [('"过期"',), ('"JWT"',)])
        self.assertEqual(terms("哈哈哈"), [('"哈哈"',)])
        self.assertEqual(terms("令牌 令牌"), [('"令牌"',)])
        self.assertEqual(terms("，。！"), [])


class EnglishAnalysisTests(unittest.TestCase):
    def test_spaced_text_passes_through(self):
        text = "The quick brown fox, version v2.0 (RFC 7807)."
        self.assertEqual(index_text(text), text)

    def test_query_words_are_quoted_and_operators_are_plain_words(self):
        self.assertEqual(terms("cache TTL"), [('"cache"',), ('"TTL"',)])
        self.assertEqual(terms("walr*"), [('"walr"*',)])
        self.assertEqual(analyze_query("a AND b OR NOT c").match_expression, '"a" OR "AND" OR "b" OR "OR" OR "NOT" OR "c"')
        self.assertEqual(terms('title:"jwt" -x (y)'), [('"title"',), ('"jwt"',), ('"x"',), ('"y"',)])
        self.assertEqual(terms("!!! *"), [])
        self.assertEqual(terms("café"), [('"café"',)])

    def test_fold(self):
        self.assertEqual(fold("  Error   Handling "), "error handling")
        self.assertEqual(fold("ＡＰＩ  認証"), "api 認証")
        self.assertEqual(fold("Straße"), "strasse")

    def test_signature_tracks_unicode_version(self):
        import unicodedata

        self.assertIn(unicodedata.unidata_version, analyzer_signature())


class OtherScriptAnalysisTests(unittest.TestCase):
    """Nice-to-have coverage: Japanese, Korean, Thai, Khmer, Myanmar, Tibetan."""

    def test_segmentation(self):
        cases = {
            "東京に行く": "京に",  # kanji + kana in one run
            "ﾄｰｸﾝ": "トー",  # half-width katakana folds
            "검색팀을": "검색",  # Hangul
            "ภาษาไทย": "ไท",  # Thai vowels stay attached (ษา is a unit pair)
            "ខ្មែរ": "ខ្មែ",  # Khmer coeng attaches to its consonant
            "မြန်မာ": "မြန်",  # Myanmar medials/asat attach
            "བོད་ཡིག": "ཡིག",  # Tibetan tsheg separates syllables
            "ㄅㄆㄇ": "ㄅㄆ",  # Bopomofo
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, tokens(text))
        self.assertNotIn("་", "".join(t for t in tokens("བོད་ཡིག") if len(t) > 1))
        self.assertFalse([t for t in tokens("トークン・リフレッシュ") if "・" in t and t != "・"])
        self.assertEqual(tokens("か\u3099"), tokens("が"))  # combining voicing mark composes


class OtherScriptSearchTests(WorkspaceTestCase):
    def test_substring_search(self):
        self.ws.write("ja", title="出張メモ", summary="東京に行きました。ﾄｰｸﾝの有効期限は30分です。")
        self.ws.write("ko", title="팀 소개", summary="검색팀을 이끌었다.")
        self.ws.write("th", title="ภาษา", summary="ภาษาไทยเป็นภาษาราชการ")
        self.ws.write("km", title="ភាសា", summary="ភាសាខ្មែរ")
        self.ws.write("my", title="ဘာသာ", summary="မြန်မာဘာသာ")
        self.ws.write("bo", title="ཡིག", summary="བོད་ཡིག")
        cases = {"東京": "ja", "トークン": "ja", "期限": "ja", "검색팀": "ko", "ไทย": "th",
                 "ខ្មែរ": "km", "မြန်မာ": "my", "བོད": "bo"}
        for query, card in cases.items():
            with self.subTest(query=query):
                self.assertEqual(self.addresses(self.ws.search(query)), [f"@overlay/{card}"])


class AnalyzerUpgradeTests(WorkspaceTestCase):
    def test_analyzer_change_reindexes_and_keeps_telemetry(self):
        import sqlite3

        from mindslice import Workspace

        # Simulate an index built by an older analyzer (raw, un-segmented text in FTS).
        self.ws.write("auth", title="认证", summary="令牌过期时间为15分钟。")
        self.ws.read("auth")
        self.ws.close()
        conn = sqlite3.connect(self.root / ".cache/index.sqlite")
        conn.execute("UPDATE cards_fts SET title='认证', summary='令牌过期时间为15分钟。'")
        conn.execute("UPDATE meta SET value='0:unicode-14.0.0' WHERE key='analyzer'")
        conn.commit()
        conn.close()
        self.ws = Workspace(self.root)
        self.assertEqual(self.ws.search("过期")["total_matches"], 1)
        self.assertEqual(self.ws.read("auth")["read_count"], 2)


if __name__ == "__main__":
    unittest.main()
