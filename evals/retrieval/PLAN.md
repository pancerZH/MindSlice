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
