# Scorer validation (agent_test.md 7.1, 7.2, 7.4)

No language model is involved in anything on this page. It checks the value-based scorer against the
card-level numbers of `evals/external` and the runner against the harness's own arms, before any LLM run.
Generated tables: [`gate1.md`](gate1.md) (scripted agents), [`scorer_validation_tier1.md`](scorer_validation_tier1.md)
and [`scorer_validation_external.md`](scorer_validation_external.md) (value-based vs card-level, per group).

## 1. The runner reproduces `evals/external` exactly

`flat` and `oracle` in `evals/agent` re-ingest each haystack session by session with `evals/external`'s own
card rules (`corpus.add_files`, `harness._apply_lineage`, `Workspace.write`), then ask each question at its
benchmark position. Scored **card-level** on the configuration of
[`external/results/summary.md`](../../external/results/summary.md) (MEME `filler32k`, every
MemoryAgentBench context), they reproduce its Mode B table to the third decimal in every group:

| Group | Metric | summary.md flat / lineage | evals/agent flat / oracle (card-level) |
| --- | --- | --- | --- |
| mab-sh/conflict (208) | stale-first | 0.779 / 0.000 | 0.779 / 0.000 |
| mab-sh/conflict | stale@10 | 0.962 / 0.000 | 0.962 / 0.000 |
| mab-sh/conflict | current@10 | 0.966 / 0.966 | 0.966 / 0.966 |
| meme/Cas-hop1 (100) | stale-first | 0.600 / 0.000 | 0.600 / 0.000 |
| meme/Cas-hop1 | stale@10 / current@10 | 0.960 / 0.940 (flat) | 0.960 / 0.940 |
| meme/Cas-hop2 (64) | stale-first / stale@10 / current@10 | 0.172 / 0.766 / 0.969 (flat) | 0.172 / 0.766 / 0.969 |
| meme/Abs-hop1, hop2 | stale@10 (flat) | 0.990, 0.900 | 0.990, 0.900 |
| meme/Del (100) | stale@10 (flat) | 0.990 | 0.990 |
| meme/Tr (98) | history-named@10 | 0.718 / 0.929 | 0.718 / 0.929 |

(LongMemEval contributes no stale value string, so the pooled 442-question row of summary.md isn't
re-scored here; it is not part of tiers smoke or 1.)

## 2. Value-based vs card-level on the same pages

Value-based judgments (6.1) on the same first pages agree with card-level within a few questions per group.
Tier 1 (MEME `nofiller` 95 episodes, MemoryAgentBench 32k), pooled as for the lines:

| Arm | Metric (MEME Cascade + MAB conflicts) | Value-based | Card-level |
| --- | --- | --- | --- |
| flat | stale-first | 0.430 (n 200) | 0.436 (n 202) |
| flat | stale@10 | 0.940 | 0.936 |
| oracle | stale-first / stale@10 | 0.005 / 0.010 | 0.000 / 0.000 |
| flat / oracle | current@10 | 0.965 / 0.965 (n 202) | 0.965 / 0.965 |
| flat / oracle | history-named@10 (MEME Tracking) | 0.902 / 1.000 (n 92) | 0.889 / 1.000 (n 93) |

The value-based pool for G3 also holds MemoryAgentBench's 22 non-conflict questions (current@10 0.969,
n 224); card-level has no current card for them. Two questions drop out of the value-based stale pool
because their stale value is never stated verbatim (section 3, "matchable").

Every disagreement falls in one of three classes (all are listed, with question ids, in the generated tables):

1. **Paraphrased stale card (value-based misses it).** MEME's annotation format differs from the dialogue:
   the value "pickup basketball Saturdays" is said as "pickup basketball *on* Saturdays", "meal kit
   (Kelvimeal)" as "a meal kit service called Kelvimeal". Tier 1: 4 flat Deletion questions.
2. **Stale and current value identical.** `pl_030`'s dependent ("my commute is about 10 min") and its
   if-then rule ("…my commute will be around 10 min") state the same value, so by value nothing is stale
   (1 Cascade question).
3. **Unannotated mentions (value-based finds more).** A value stated by a card the annotations don't tie to
   it: a 2-hop dependent restating the 1-hop value (`sw_044`: "the test command is quorix spec --run all");
   the same person in another role (`sw_004`: "VP Taehyun Kim"); assistant chatter ("electric cars",
   "dairy-free"); a value inside a compound ("bike" in "road bike", `pl_026`); a second MemoryAgentBench
   subject sharing the anchor words ("The capital of United Kingdom of Great Britain and Ireland is London").
   Tier 1: 1 oracle stale-first, 1 oracle MAB stale@10, 2 oracle Deletion stale@10, and 14 flat Tracking
   questions where chatter rounds name an earlier vehicle (so flat's history-named@10 is higher by value).

### Whole-workspace metrics: the oracle's ceiling

`retired`, `lost` and `forgotten` look at every active card, not just the page, so class 3 weighs more:

| Tier 1 | flat | oracle |
| --- | --- | --- |
| `retired` (302 matchable updates) | 0.000 | 0.904: 18 of 163 Tracking steps, 10 of 95 root changes and 1 of 44 conflicts fail |
| `lost` (2,866 matchable current values) | 0.000 | 0.000 |
| `forgotten` (76 matchable deletions) | 0.000 | 0.921: 6 fail |

The oracle's lineage is turn-level: it supersedes the round that states a value, not later rounds that
mention it in passing ("Do you find that the compact size of your **Therwyn Compact** makes it easier…",
"…low-sugar to help manage my **pre-diabetes**"). Those rounds stay active and unwarned, so by value they are
stale. Likewise a deleted partner's name survives in a dependent ("I bought **James** a watch"), which Mode B
keeps (it only flags it with `missing_baselines`). These are real stale statements in the workspace, not
matching errors, but they mean **0.904 (`retired`) and 0.921 (`forgotten`) are what perfect annotation-level
lineage scores**, the reference for G2 and G5. An agent that rewrites history into its own cards can exceed
them; `agent-overlay`, which can't edit `@history`, has to supersede those rounds too.

Flat's `retired` and `forgotten` are 0 by construction: the request round itself ("My partner is James.
Please remove that from your memory.") states the value.

## 3. Scorer choices fixed here (before any LLM run)

| Choice | Rule | Why, and what it changes on flat / oracle |
| --- | --- | --- |
| Normalization | NFKC, typographic quotes straightened, casefold, whitespace collapsed; values also lose surrounding punctuation (not brackets) | 6.1's rule plus Unicode forms; "The Quorath Codex (book)" keeps its bracket |
| Whole-word match | a value may not continue a longer word ("paris" is not in "Parisien") | Tier 1 pooled metrics move by at most one question against plain substring (flat stale-first 0.430 vs 0.425; oracle forgotten 0.921 vs 0.908) |
| MemoryAgentBench subject anchors | a value counts only on a line that also has the fact's subject words (prefix words in at most 1% of the context's facts, never the values' own words) | Without it, "basketball" or "London" on any of hundreds of unrelated fact cards would be stale; with it, value-based equals card-level on all 44 Tier 1 conflicts for flat |
| Matchable values | a value counts only if its own flat card (the round or fact that conveys it) states it | 263 of 2,866+263 MEME plain values are never said verbatim (annotation formats such as "(book)", "2x/week"); no arm could state them, so they would count as `lost` for every arm, flat included. Excluded and counted |
| Before-change questions | scored for `current@10` as separate groups (`meme/before-*`), not pooled | They have no stale value; they set the `lost` question point |

## 4. Gate 1: scripted agents through the four MCP tools

On all of Tier 1 (96 haystacks; `python -m evals.agent offline --tier 1` and `gate`):

| Pair | Units compared | Disagreements |
| --- | --- | --- |
| `scripted-flat` vs `flat` | 865 questions (all groups), 302 updates, 2,866 values, 76 deletions | **0** |
| `scripted-oracle` vs `oracle` | same | **0** |
| `scripted-overlay` vs `oracle` | same | 12 `current@10` (11 MEME Aggregation "list everything" questions, 1 before-change Absence question); **0** on every pooled metric |

MemoryAgentBench runs in 10-fact batches (PLAN.md, section 2); Gate 1 was run again after that change, with
the same result (batch boundaries only move the points where `retired` is judged).

`scripted-overlay` writes far fewer cards (only those carrying lineage, copied from `@history`), so BM25
statistics shift slightly and ranks 9-10 of multi-value questions reshuffle; no pooled metric moves. The same
checks run in CI on the synthetic datasets (`tests/test_agent_eval.py`).
