"""End-to-end Chinese coverage across search, ranking, metadata, writes, packaging and tooling.

Regression targets from other FTS5 memory projects: whole-run tokens (claude-mem #3801),
2-character words lost to trigram (basic-memory #1294), silent misses on unspaced compounds
under strict phrase matching (basic-memory #1533).
"""

from __future__ import annotations

import zipfile

from .helpers import WorkspaceTestCase, add_filler, card_text


class ChineseMatchingTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write("auth", title="认证流程", summary="令牌过期时间为15分钟。",
                      content="- 刷新令牌每天轮换。\n- 第3章介绍用uv管理依赖。")

    def assert_finds(self, *queries: str, coverage: float = 1.0) -> None:
        for q in queries:
            with self.subTest(query=q):
                res = self.ws.search(q)
                self.assertEqual(self.addresses(res), ["@overlay/auth"])
                self.assertEqual(res["results"][0]["coverage"], coverage)

    def test_substrings_of_every_length_and_position(self):
        self.assert_finds("令", "过", "钟", "令牌", "过期", "期时", "过期时间", "令牌过期时间为15分钟")
        self.assert_finds("认证", "证流", "流程", "认证流程")  # title
        self.assert_finds("刷新令牌", "每天轮换", "轮换")  # body bullets
        self.assertEqual(self.ws.search("猫")["total_matches"], 0)
        self.assertEqual(self.ws.search("猫狗")["total_matches"], 0)

    def test_mixed_scripts_digits_and_width_variants(self):
        self.assert_finds("15分钟", "１５分钟", "第3章", "用uv管理", "uv管理", "用UV", "ｕｖ")
        self.assert_finds("分钟15", coverage=1.0)

    def test_punctuation_quotes_and_spacing_in_queries(self):
        self.assert_finds("令牌，过期。", "“令牌”", "「过期」", "《认证流程》", "令牌　过期", "令牌 过期", "过期*")
        self.assert_finds("令牌🔑过期")
        for q in ("，。！", "……", "“”"):
            with self.subTest(query=q):
                self.assertEqual(self.ws.search(q)["total_matches"], 0)

    def test_traditional_text_matches_traditional_queries(self):
        self.ws.write("trad", title="認證流程", summary="權杖過期時間為十五分鐘。")
        self.assertEqual(self.addresses(self.ws.search("過期")), ["@overlay/trad"])
        self.assertEqual(self.addresses(self.ws.search("認證")), ["@overlay/trad"])

    def test_rare_ideographs_and_repeats(self):
        self.ws.write("rare", title="𠮷野家", summary="哈哈哈哈，好吃。")
        self.assertEqual(self.addresses(self.ws.search("𠮷")), ["@overlay/rare"])
        self.assertEqual(self.addresses(self.ws.search("哈哈")), ["@overlay/rare"])


class ChineseRankingTests(WorkspaceTestCase):
    def test_unspaced_compound_is_found_not_silently_missed(self):
        self.ws.write("rime", title="输入法笔记", summary="09-07 雾凇词库部署时实测。")
        self.ws.write("pinyin", title="拼音方案", summary="雾凇拼音是一套输入方案。")
        res = self.ws.search("雾凇拼音")
        self.assertEqual(self.addresses(res), ["@overlay/pinyin", "@overlay/rime"])
        self.assertEqual(res["results"][0]["coverage"], 1.0)
        self.assertTrue(0 < res["results"][1]["coverage"] < 1)  # partial credit, never a silent miss

    def test_verbatim_and_scattered_bigrams_are_both_found(self):
        add_filler(self.ws)
        self.ws.write("scattered", title="时间到了就过期 期时不候", summary="无关的说明。")  # all bigrams, no phrase
        self.ws.write("verbatim", title="令牌说明", summary="令牌的过期时间是十五分钟。")
        res = self.ws.search("过期时间")
        self.assertEqual(sorted(self.addresses(res)), ["@overlay/scattered", "@overlay/verbatim"])
        self.assertEqual([r["coverage"] for r in res["results"]], [1.0, 1.0])  # both contain every bigram
        scores = [r["score"] for r in res["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))  # ordered by BM25 (title weight)

    def test_spaced_words_coverage(self):
        add_filler(self.ws)
        self.ws.write("both", title="说明", summary="令牌会过期。")
        self.ws.write("one", title="说明", summary="令牌很安全。")
        res = self.ws.search("令牌 过期")
        self.assertEqual(self.addresses(res), ["@overlay/both", "@overlay/one"])
        self.assertEqual(res["results"][0]["coverage"], 1.0)
        self.assertTrue(0 < res["results"][1]["coverage"] < 1)

    def test_mixed_language_query_ranks_by_coverage(self):
        self.ws.write("both", title="Token policy", summary="JWT 的过期时间为 30 分钟。")
        self.ws.write("jwt-only", title="JWT JWT JWT", summary="JWT signing keys rotate weekly.")
        res = self.ws.search("JWT过期")
        self.assertEqual(self.addresses(res), ["@overlay/both", "@overlay/jwt-only"])
        self.assertEqual(res["results"][0]["coverage"], 1.0)
        self.assertTrue(0 < res["results"][1]["coverage"] < 1)

    def test_field_weights_order_equal_coverage(self):
        add_filler(self.ws)
        common = {"summary": "一句普通的说明文字。", "content": "- 另一条普通的陈述。"}
        self.ws.write("w/title", title="缓存", **common)
        self.ws.write("w/alias", title="卡片甲", aliases=["缓存"], **common)
        self.ws.write("w/tag", title="卡片乙", tags=["缓存"], **common)
        self.ws.write("w/summary", title="卡片丙", summary="一句普通的缓存说明文字。", content=common["content"])
        self.ws.write("w/body", title="卡片丁", summary=common["summary"], content="- 另一条普通的缓存陈述。")
        self.assertEqual(self.addresses(self.ws.search("缓存")),
                         ["@overlay/w/title", "@overlay/w/alias", "@overlay/w/tag", "@overlay/w/summary", "@overlay/w/body"])


class ChineseMetadataTests(WorkspaceTestCase):
    def test_paths_aliases_tags_and_wikilinks(self):
        self.ws.write("笔记/认证流程", title="认证流程", summary="认证使用短期令牌。",
                      tags=["认证", "ＡＰＩ"], aliases=["身份验证"])
        self.ws.write("笔记/刷新", title="刷新", summary="刷新令牌见 [[身份验证]] 和 [[笔记/认证流程|流程]]。")
        self.assertEqual(self.addresses(self.ws.search("笔记 刷新"))[0], "@overlay/笔记/刷新")  # path words
        self.assertIn("@overlay/笔记/认证流程", self.addresses(self.ws.search("身份验证")))  # alias words
        self.assertEqual(self.ws.search("", tags=["认证"])["total_matches"], 1)
        self.assertEqual(self.ws.search("令牌", tags=["api"])["total_matches"], 1)  # full-width tag folds
        card = self.ws.read("身份验证")
        self.assertEqual(card["address"], "@overlay/笔记/认证流程")
        self.assertEqual([b["address"] for b in card["backlinks"]], ["@overlay/笔记/刷新"])
        refresh = self.ws.read("@overlay/笔记/刷新")
        self.assertEqual([l["address"] for l in refresh["links"]], ["@overlay/笔记/认证流程"] * 2)

    def test_frontmatter_round_trip_with_quotes(self):
        title = '认证「流程」"引号" \\ 反斜杠 🚀'
        self.ws.write("q", title=title, summary="摘要。", tags=["中文标签"])
        card = self.ws.read("q")
        self.assertEqual((card["title"], card["tags"]), (title, ["中文标签"]))

    def test_long_summary_preview_and_lint(self):
        long_summary = "这是一段很长的中文摘要" * 30  # 330 characters, no spaces anywhere
        self.ws.write("long", title="长摘要", summary=long_summary)
        preview = self.ws.search("中文摘要")["results"][0]
        self.assertLessEqual(len(preview["summary"]), 240)
        self.assertTrue(preview["summary"].endswith("…"))
        self.assertTrue(preview["summary_truncated"])
        codes = {i["code"] for i in self.ws.validate()["warnings"]}
        self.assertIn("long_summary", codes)

    def test_validate_flags_broken_chinese_wikilink(self):
        self.ws.write("a", title="甲", summary="链接到 [[不存在的卡片]]。")
        warnings = self.ws.validate()["warnings"]
        self.assertTrue(any(w["code"] == "broken_wikilink" and "不存在的卡片" in w["message"] for w in warnings))

    def test_manifest_description_truncation(self):
        self.mount_slice("kb", {"a": card_text("甲", "内容。")}, "@kb", 10, "baseline", description="描述" * 100)
        mount = next(m for m in self.ws.manifest()["mounts"] if m["alias"] == "@kb")
        self.assertLessEqual(len(mount["description"]), 160)
        self.assertTrue(mount["description_truncated"])


class ChineseWorkflowTests(WorkspaceTestCase):
    def test_write_append_and_dedupe(self):
        self.ws.write("tools", title="工具", summary="工具偏好。", content="- 使用ＵＶ管理依赖")
        self.assertFalse(self.ws.write("tools", op="append", content="- 使用UV管理依赖")["changed"])  # width variant
        res = self.ws.write("tools", op="append", content="固定 Python 版本\n锁定依赖")  # no bullet markers
        self.assertEqual(res["added_statements"], 2)
        self.assertEqual(self.ws.read("tools")["body"], "- 使用ＵＶ管理依赖\n- 固定 Python 版本\n- 锁定依赖\n")
        self.assertEqual(self.addresses(self.ws.search("锁定依赖")), ["@overlay/tools"])

    def test_supersession_redirect_and_source_filter(self):
        self.project({"api/auth": card_text("认证", "令牌过期时间为15分钟。")})
        self.ws.write("api/jwt", title="JWT 有效期", summary="会话改用签名 JWT，有效期 30 分钟。",
                      supersedes=["@project/api/auth"])
        res = self.ws.search("令牌过期")
        self.assertEqual(self.addresses(res), ["@overlay/api/jwt"])
        self.assertEqual(res["results"][0]["matched_via_superseded"], ["@project/api/auth"])
        scoped = self.ws.search("令牌过期", source="@project")
        self.assertEqual(scoped["results"][0]["status"], "superseded_by: @overlay/api/jwt")
        self.assertEqual(self.ws.read("api/auth")["address"], "@overlay/api/jwt")

    def test_staging_diff_and_apply(self):
        self.ws.write("草稿", title="草稿", summary="暂存的中文内容。", stage=True)
        self.assertEqual(self.ws.search("暂存")["total_matches"], 0)
        self.assertIn("+暂存的中文内容。", self.ws.diff()["patch"])
        self.ws.apply()
        self.assertEqual(self.addresses(self.ws.search("暂存")), ["@overlay/草稿"])

    def test_bake_chinese_paths(self):
        self.ws.write("笔记/甲", title="甲", summary="见 [[笔记/乙]]。")
        self.ws.write("笔记/乙", title="乙", summary="乙的内容。")
        res = self.ws.bake("@notes", self.tmp / "notes.zip", prefix="笔记/")
        self.assertEqual(res["cards"], ["笔记/乙", "笔记/甲"])
        self.assertTrue(res["validation"]["ok"])
        with zipfile.ZipFile(self.tmp / "notes.zip") as zf:
            self.assertIn("notes.slice/笔记/甲.md", zf.namelist())
        self.assertEqual(self.ws.read("@notes/笔记/甲")["links"][0]["address"], "@notes/笔记/乙")
