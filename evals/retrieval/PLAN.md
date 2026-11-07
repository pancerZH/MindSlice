# Retrieval evaluation plan

Written on 2026-11-06, after the data was frozen and before any system was scored on any split.
The method follows [SpaceBridge](https://github.com/pancerZH/SpaceBridge): per-query scores, a percentile
bootstrap over queries, comparisons against alternatives, rules fixed in advance, and a ledger of which data
informed which decision.

## What is measured

`Workspace.search()` (what the MCP `search` tool calls) with its defaults (`k = 10`, `follow_supersedes = True`)
on two mounted handbooks and a runtime overlay. Only ranking quality: not the agent, and not `read()`.

## The data

Synthetic, written for this evaluation. There is no real material. It describes a fictional product team with
an English handbook (`@kb-en`, 31 cards) and a Chinese one written separately for a Beijing team, not as a
translation (`@kb-zh`, 31 cards). Six runtime cards in `@overlay` supersede or extend handbook cards. Vocabulary
overlaps on purpose: auth tokens, design tokens and LLM tokens; 令牌 in auth and in design.

| Split | English | Chinese | Use |
| --- | --- | --- | --- |
| `dev` | 20 | 20 | May inform engine changes. Every such change is recorded in the ledger below |
| `holdout` | 20 | 20 | The pass lines are read here, once per frozen engine |
| `limits` | 5 | 5 | Known limits of lexical search (synonyms, typos, Traditional script, cross-lingual). Reported, with no line |

Judgments are graded: 2 means the card answers the query, 1 means it is related. Unjudged results count as 0. A
superseded card is never judged; its replacement is. Judgments were written with the queries, before any run.

**Known bias, stated now:** the same author wrote the corpus, the queries and the engine, knowing how the engine
matches text. Lexical overlap between queries and answers is therefore likely higher than with real users. Three
partial guards: every language has `paraphrase` or `question` queries that share few words with their answer;
distractor cards share vocabulary with answers; and the `limits` split names where lexical search must fail.
Read the absolute numbers as an upper bound for real-world quality, and the comparisons between systems as
the more trustworthy part.

Data digests (SHA-256, `data/DIGESTS.json`; `python -m evals.retrieval check` verifies them):

| Part | Digest |
| --- | --- |
| Corpus (slices + overlay) | `6a4238a74e9d376792f58fe806e28ac8e5438e003611ed5358aa1438c6d8e6c3` |
| `dev` queries | `272302ea4b46dd92967e2b800e8ed5f3724dd94d89b2a74e30637319261dcc6f` |
| `holdout` queries | `121d592e4b12beac2748ce1fb1eadf85aa0c9bb6f15d8a36656908d08421c441` |
| `limits` queries | `8490ac6d5e4c7565e6312ed581dcf781319c44f2e3ad5c26342e171b6c59781b` |

## Systems

| System | What it is |
| --- | --- |
| `mindslice` | The engine as committed, unmodified |
| `bm25-order` | Coverage-first ranking undone: BM25 score alone orders results |
| `strict-phrase` | CJK query runs must match verbatim (basic-memory's approach) instead of OR-ed bigrams |
| `v1-baseline` | The engine at commit `bc0e7ac`: no script-aware analysis, no NFKC, BM25 order |

Each comparison system patches exactly one decision out of the same engine and gets its own fresh workspace.

## Metrics and intervals

- **Primary:** `nDCG@5`. Linear gain, discount `1 / log2(rank + 1)`, ideal ordering from the judgments.
- **Also:** `Recall@10` (judged cards on the first page an agent sees) and `MRR@10` (rank of the first grade-2 card).
- **Interval:** a 95% percentile bootstrap over queries: 2,000 replicates, seed 20261106. Each English and each
  Chinese group draws one set of resamples, shared by every system, so differences between systems are paired.
  With 20 queries per group, intervals are wide; this is said now.

## Lines and verdicts, fixed now

Read on `holdout` only:

| Line | Claim | Statistic | Line |
| --- | --- | --- | --- |
| L1 | English quality | `mindslice` nDCG@5 | 0.80 |
| L2 | Chinese quality | `mindslice` nDCG@5 | 0.80 |
| L3 | English first-page recall | `mindslice` Recall@10 | 0.90 |
| L4 | Chinese first-page recall | `mindslice` Recall@10 | 0.90 |
| L5 | Script-aware analysis matters | Chinese nDCG@5, `mindslice` minus `v1-baseline` | 0.30 |
| L6 | OR-ed bigrams don't lose to strict phrases | Chinese nDCG@5, `mindslice` minus `strict-phrase` | 0.00 |
| L7 | Coverage ranking doesn't lose (English) | English nDCG@5, `mindslice` minus `bm25-order` | 0.00 |
| L8 | Coverage ranking doesn't lose (Chinese) | Chinese nDCG@5, `mindslice` minus `bm25-order` | 0.00 |

| Verdict | Meaning |
| --- | --- |
| **confirmed** | The interval's lower bound is at or above the line |
| **point pass** | The point estimate is at or above the line; the lower bound is below it |
| **miss** | The point estimate is below the line |

For L6 to L8, "confirmed" means the design choice measurably helps, and "point pass" means it doesn't measurably
hurt. A miss stays a miss: no engine change and no data change before the result is reported. Any later fix is
judged on a new holdout set, since this one will have informed it.

## Second holdout (`holdout-2`)

Added on 2026-11-06, after the first holdout's L7 and L8 missed by one or two queries. Frozen, and these rules
written, before any system was scored on it. The engine is the one the first holdout read (source digest
`d4de322ebd6bdb16528464c5090c4c5fc00add21ac4d69d6297e2e7a94da3959`). Nothing in the engine changes because of
these results; they decide what is recommended.

**Why:** `holdout` mostly has one obvious answer per query, so ranking variants only differed on one or two
queries. `holdout-2` targets the ranking question directly:

| Condition | Corpus | Queries | What makes it harder |
| --- | --- | --- | --- |
| Full | The same handbooks and overlay | 20 English, 20 Chinese | 48 of 60 holdout-2 queries judge several cards (2.4 on average); 19 have several answers. Natural phrasing with filler words |
| Tiny | `tiny-en` / `tiny-zh`: a lone overlay of 10 cards, an agent's first week on one project | 10 English, 10 Chinese | Vocabulary is saturated: "deploy"/"部署" are in 7 of 10 cards and "production"/"生产" in 6, where FTS5's own IDF collapses to about zero. This is the case coverage-first ranking was designed for |

A fifth system joins: `unweighted-coverage`, coverage-first with every query word counted equally (the ranking
before the dev-informed IDF weighting), so the IDF question gets a proper reading too. It has no line.

Digests (`data/DIGESTS.json`; the four earlier digests above are unchanged):

| Part | Digest |
| --- | --- |
| Tiny English corpus | `91c77aaad4fb97a4f69e007fc8a7283ff4e63357edfb67d6d9fe4c738df56967` |
| Tiny Chinese corpus | `7eb65839c3b09f620dad1011b771b68905b01cfa3fb3c213ff6cd62696bbba7e` |
| `holdout-2` queries | `1e439e475174d158584bc37a455460d47e3aae412f3259dc9b0f4cc9e5f70e8b` |

Lines, read on `holdout-2` only, with the same verdict rules:

| Line | Group | Claim | Line |
| --- | --- | --- | --- |
| L9 | Full, English | `mindslice` nDCG@5 | 0.70 |
| L10 | Full, Chinese | `mindslice` nDCG@5 | 0.70 |
| L11 | Tiny, English | `mindslice` nDCG@5 | 0.70 |
| L12 | Tiny, Chinese | `mindslice` nDCG@5 | 0.70 |
| L13 | Full, English | `mindslice` minus `bm25-order` | 0.00 |
| L14 | Full, Chinese | `mindslice` minus `bm25-order` | 0.00 |
| L15 | Tiny, English | `mindslice` minus `bm25-order` | 0.00 |
| L16 | Tiny, Chinese | `mindslice` minus `bm25-order` | 0.00 |
| L17 | All 60 queries pooled | `mindslice` minus `bm25-order` | 0.00 |

**Decision rule, fixed now.** L17 decides the recommendation:
- **Confirmed or point pass:** keep coverage-first ranking.
- **Miss:** recommend reverting to BM25 order.

L13 to L16 say where any gain or loss comes from. The user makes the call either way; this fixes what the
evidence recommends. On 60 queries the pooled interval is still wide, and that is said now.

## Decision: BM25 order (2026-11-06)

Following L17's miss and the rule above, the user reverted the engine to BM25 order: results are ordered by
`score`, then precedence, then address. `coverage` stays in every preview as information only.

- **Verified equivalent:** on all 150 queries, the reverted engine's top 10 equals the archived `bm25-order`
  ranking, and the new `coverage-first` comparison system equals the archived engine. The evidence above is
  therefore evidence about exactly this engine (source digest `631ab34d3b4a3ad48ff0c7ea506fc707fca05ea5113f179cb243ebb62f473b74`).
- **Systems now:** `bm25-order` is the engine, so it is gone; `coverage-first` (the reverted ordering) takes its
  place. `strict-phrase` and `v1-baseline` now differ from the engine only in analysis, as both orderings are BM25.
- **Lines:** L7, L8 and L13 to L17 were decided on the archived engine and are retired. Their record is
  `results/archive/2026-11-06-coverage-first-engine/`. L1 to L6 and L9 to L12 are re-read on this engine
  and are no longer fresh evidence.
- **Next ranking change:** `holdout` and `holdout-2` have both informed ranking. Judge any further ranking
  change on a new split (`holdout-3`), frozen with its lines before it is scored.

## Third holdout (`holdout-3`) and the aliased corpus

Written on 2026-11-07, before any of its data existed. The engine is the BM25-order engine above, plus
the search feedback described below, which must leave every ranking unchanged.

**Why.** Three questions the record leaves open:

1. **Author bias.** Every query so far was written by the engine's author. `holdout-3`'s queries and
   judgments are written by a separate agent that has not seen the engine's code, this plan, the earlier
   queries or any result.
2. **Vocabulary mismatch.** All eight queries scoring below 0.5 nDCG@5 fail because the words they use are
   not in the answer card, and every card has `aliases = []`. MindSlice puts the remedy in policy, not in
   the engine: the `slice-builder` skill writes aliases. The aliased corpus measures that remedy.
3. **Search feedback.** `search()` now reports `unmatched_terms` (query words no card in scope contains)
   and `did_you_mean` (close words that do occur, for spaced-script words). Ordering is untouched.

**The data, and who writes it.**

| Part | Written by | Sees | Never sees |
| --- | --- | --- | --- |
| Aliased corpus, `data/aliased/` | A fresh agent following `skills/slice-builder/SKILL.md` | Every card of every corpus (including the tiny ones), and the skill | Queries, results, this plan, the engine's code |
| `holdout-3` queries and judgments | A second fresh agent | The plain corpus (no aliases) and the judging rules | All of the above, plus the aliased corpus and the skill |

The aliased corpus is the plain corpus with only each card's `aliases = [...]` line changed; `check`
verifies this. The skill's alias section was rewritten on 2026-11-07 after reading the failures on `dev`,
`holdout`, `limits` and `holdout-2` (see the ledger), which is why it is judged here and not there.

**Queries.** 40 English and 40 Chinese queries on the full corpus, ids `en-b01`... and `zh-b01`...
`lang` names the handbook whose team asks (as in `limits`, where `zh-l03` is English text).

| Category | Per language | What it is |
| --- | --- | --- |
| `natural` | 20 | Asked the way a teammate would type it into a search box or ask an assistant, in their own phrasing |
| `own-words` | 12 | The asker doesn't know the handbook's terms: describes the situation, symptom or goal, not the card's name |
| `cross-lingual` | 4 | Written in the other language from the card that answers it |
| `typo` | 4 | A natural query with one realistic typo (in Chinese, a wrong character from the input method) |

`own-words` and `cross-lingual` together are the **vocabulary-gap** queries (32 pooled).

**Systems added.** Both leave the engine unchanged:

- `aliases`: every workspace is built from `data/aliased/` instead of the plain corpus.
- `suggest-retry`: a fixed caller policy, with no agent. If the first search's `did_you_mean` is not empty,
  replace each suggested word in the query with its first suggestion, search once more, and score that
  second list instead.

They also run on the earlier splits, reported with no line, since those splits informed the skill.

**Lines**, read on `holdout-3` only, once, with the verdict rules above:

| Line | Group | Statistic | Line |
| --- | --- | --- | --- |
| L18 | English, `natural` | `mindslice` nDCG@5 | 0.80 |
| L19 | Chinese, `natural` | `mindslice` nDCG@5 | 0.80 |
| L20 | Vocabulary-gap, pooled (32) | `aliases` minus `mindslice` | 0.05 |
| L21 | `natural`, pooled (40) | `aliases` minus `mindslice` | −0.02 |
| L22 | All 80 pooled | `aliases` minus `mindslice` | 0.00 |
| L23 | `typo`, pooled (8) | `suggest-retry` minus `mindslice` | 0.00 |
| L24 | All 80 pooled | `suggest-retry` minus `mindslice` | 0.00 |

L21 is a margin: aliases may cost ordinary queries at most 0.02.

**Decision rules, fixed now.** The user makes the call either way; these fix what the evidence recommends.

- **Aliases.** If L22 is confirmed or a point pass, and L21 is not a miss, keep the skill's alias section
  and recommend aliases in the README. Otherwise, recommend reverting the alias section. L20 says whether
  aliases help where they are meant to.
- **Suggestions.** If L24 is confirmed or a point pass, keep `did_you_mean`. If it misses, recommend
  dropping it and keeping `unmatched_terms`, which changes no result. L23 says whether it helps on typos.

**Known limits, stated now.** The query writer is a language model, as is the author; a fresh context
reduces the shared-author bias but doesn't remove it. Only English typos can benefit from `did_you_mean`
(it makes no suggestions inside Chinese runs), so L23 pools 4 queries that may gain with 4 that can't.
With 8 typo and 32 vocabulary-gap queries, those intervals are wide. Once read, `holdout-3` has informed
the alias and suggestion questions, and any later change to either needs fresh data.

**Amendment, 2026-11-07: after the queries were written, before any system was scored on them.** The
query writer gave the other team's same-topic card a grade 1 on 73 of 80 queries (75 judgments, none a
grade 2). The earlier splits have 6 such judgments in 150 queries. Lexical search seldom returns a Chinese
card for an English query, or the reverse, so these cap nDCG@5. A query with one grade-2 card and one such
grade 1 scores at most 0.76 unless the other-language card is returned, which is below L18 and L19's 0.80.

- **The lines stay as written**, read on the judgments as written. A miss stays a miss.
- **Also reported, deciding nothing:** a *same-team reading*. The same rankings are scored without the
  judgments on the other team's handbook (`@kb-zh` for English-team queries, `@kb-en` for Chinese-team),
  with verdicts shown against the same lines.

The writer's report also named its four Chinese typos. That report was read after the engine was frozen
for this read (source digest `f8e62ecdcb2ea9683593c61959e81f81394c1db8605c2afbe19ff35e9f1236de`), and
`did_you_mean` makes no suggestions inside Chinese runs.

**Frozen data** (`data/DIGESTS.json`; every earlier digest is unchanged):

| Part | Digest |
| --- | --- |
| Aliased corpus, `data/aliased/` (88 cards, 539 aliases) | `89f7ba4e1455ec458189496b75dc4e01487f48d5867ef16a4f3de1d91c87ed44` |
| `holdout-3` queries | `a05d7a4e0d9a77c174af7baab70bc62de704a8713898d158b5dd5be862f74f1a` |

## Ledger

| Date | Run | What it informed |
| --- | --- | --- |
| 2026-11-06 | Data frozen, this plan written | Nothing scored yet |
| 2026-11-06 | `dev`, all systems. Engine: `a41bb82` plus the uncommitted deterministic tie-breaks | `bm25-order` beat `mindslice` by 0.003 nDCG@5 in both languages. Cause, from `en-d07` ("token budget for prompts"): unweighted coverage counts filler words, so a card matching "for" plus one word outranked the prompts card. **Engine changed:** coverage is now IDF-weighted. No data changed |
| 2026-11-06 | `dev`, after the change | `mindslice` minus `bm25-order`: +0.005 English, +0.002 Chinese. No further change. Engine frozen for the holdout read, source digest `d4de322ebd6bdb16528464c5090c4c5fc00add21ac4d69d6297e2e7a94da3959` (`run.json` records it) |
| 2026-11-06 | `holdout` and `limits`, once, frozen engine | L1 to L6 **confirmed**. L7 and L8 **miss**: `mindslice` minus `bm25-order` is −0.007 English [−0.021, 0.000] and −0.003 Chinese [−0.007, 0.000]. Causes: `en-h05` and `zh-h05`, where coverage ignores BM25's field weights, and IDF on about 70 cards overweights "must". No engine change |
| 2026-11-06 | Exploratory, after the verdict: unweighted coverage on `dev` and `holdout` | IDF-weighted minus unweighted: +0.007 and +0.005 on `dev`, −0.007 and −0.002 on `holdout`. The ranking variants differ by one or two queries here, so this set can't separate them. This `holdout` has now informed the ranking question; deciding it needs a new, harder holdout |
| 2026-11-06 | `holdout-2` written and frozen, its rules added above | Nothing scored on it yet |
| 2026-11-06 | `holdout-2`, once, same engine | Quality: L9, L11, L12 **confirmed**, L10 **point pass**. Ranking: L13 **miss** (−0.065 [−0.105, −0.027]), L14 **miss** (−0.016 [−0.047, 0.010]), L15 and L16 **confirmed** (+0.002 on the tiny corpora), and decision line L17 **miss** (−0.026 [−0.046, −0.010]). **By the rule above, the evidence recommends reverting to BM25 order.** Coverage-first was worse on 12 of 60 queries and better on 3. Cause, diagnosed after the verdict: in a corpus this size, words that are rare but carry no topic ("do", "when", 修改) earn heavy coverage credit, IDF-weighted or not, while BM25's field weights and term saturation keep the topical card first. `unweighted-coverage` falls between (−0.015 pooled). The engine is unchanged; the decision is the user's |
| 2026-11-06 | User decision: revert to BM25 order | Engine ordering changed; coverage kept as a reported field. Equivalence verified on all 150 queries (above). Record archived, L7, L8 and L13 to L17 retired, results and the regression floor regenerated on the new engine |
| 2026-11-07 | Reading the eight queries below 0.5 nDCG@5 (`dev`, `holdout`, `limits`, `holdout-2`) | All are vocabulary mismatches, and no card has aliases. **Skill changed:** `slice-builder`'s alias section rewritten (what aliases should cover, what to avoid; examples from a topic outside the corpus). No engine or data change |
| 2026-11-07 | `holdout-3` and aliased-corpus rules written (above), before any of their data existed | Nothing generated or scored |
| 2026-11-07 | Engine change: `search()` reports `unmatched_terms` and `did_you_mean` (analyzer version 2 adds the unstemmed `card_words` vocabulary). Harness: systems `aliases` and `suggest-retry`, lines L18-L24, category groups | No ranking change: on all 150 queries, every system's top 10 equals the recorded one (750 rankings). Exploratory, `dev` only: `suggest-retry` minus `mindslice` is +0.012 English, 0.000 Chinese. Engine frozen for the `holdout-3` read, source digest `f8e62ecdcb2ea9683593c61959e81f81394c1db8605c2afbe19ff35e9f1236de` |
| 2026-11-07 | `holdout-3` queries written by the blind agent; amendment above (same-team reading), before any scoring | Nothing scored on `holdout-3` |
| 2026-11-07 | Aliased corpus written by the blind agent (88 cards, 539 aliases, 5-7 per card); `check` confirms only aliases lines differ and `validate()` is clean. Both new parts frozen (digests above) | Nothing scored on `holdout-3` or with `aliases` |
| 2026-11-07 | Before the read, the CI regression test ranked `holdout-3` in memory and errored on missing recorded entries, printing no score | Nothing seen. The test now skips splits with no recorded floor |
