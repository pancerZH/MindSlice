# External benchmark plan

Written on 2026-11-07, after the data was pinned and the compilers and checks were written and tested on
synthetic data, and **before any benchmark question was searched**. The method follows
[`evals/retrieval/PLAN.md`](../retrieval/PLAN.md): rules fixed in advance, intervals over questions, and a
ledger of which run informed which decision.

## What is measured, and what is not

MindSlice's engine, as committed at `16223dc` (engine source digest
`a48eae418a9054fe0d1c0a5eadb0b89b464378dab849f0b2e317ccd3bc5990fb`, the same engine `evals/retrieval` last
read), on four published memory benchmarks. **No language model is called anywhere**: ingestion is a fixed
compiler, queries are the benchmark questions verbatim, and scoring compares returned card addresses and
response fields with the datasets' annotations.

- **Mode A, retrieval.** `search(question, k=10)` with defaults on flat cards (no lineage): Recall@5,
  Recall@10, MRR@10, nDCG@5 and All@10 against the evidence turns or sessions. Also whether `coverage` and
  `unmatched_terms` separate unanswerable questions from answerable ones.
- **Mode B, lineage.** The same cards, with `supersedes`, `extends` and deletions compiled from the
  annotations and written through `Workspace.write`. Whether `read()` and `search()` expose that lineage
  (forwarding, `unrebased_extensions`, `baseline_superseded_by`, `missing_baselines`), and how first pages
  change against flat cards.

Not measured: answer accuracy (that needs a reader model), and above all **whether an agent would write
this lineage**. Mode B's lineage comes from gold annotations, so it is an upper bound on what an agent's
writes could give, and its structural checks test the engine's mechanism, not memory policy.

## The data

Pinned in [`sources.py`](sources.py) by revision and SHA-256, fetched outside the repository, never committed.

| Dataset | File | Revision | License | Haystacks | Questions |
| --- | --- | --- | --- | --- | --- |
| LongMemEval-S (cleaned) | `longmemeval_s_cleaned.json` | HF `98d7416c` | MIT | 500 (one per question) | 500 (30 abstention) |
| LoCoMo | `locomo10.json` | GitHub `3eb6f2c5` | CC BY-NC 4.0 | 10 conversations | 1,986 (446 adversarial) |
| MEME, `filler32k` (the default setting) | `meme_filler32k.json` | HF `e14c4e68` | CC BY 4.0 | 100 episodes | 1,188 (494 before, 694 after the change) |
| MEME, `nofiller` (evidence sessions only) | `meme_nofiller.json` | HF `e14c4e68` | CC BY 4.0 | 100 episodes | 1,188 |
| MemoryAgentBench, Conflict Resolution | `Conflict_Resolution-00000-of-00001.parquet` | HF `7ea06698` | MIT | 4 single-hop contexts (6k to 262k) | 293 labeled of 400 |

MemoryAgentBench ships only Parquet; [`parquet.py`](parquet.py) is a minimal standard-library reader. Its
decoded rows match pyarrow's (SHA-256 `fe79015f…`, recorded in `sources.py` and verified by `check`).

### Found while compiling, before any search

- **LongMemEval-S.** Evidence sessions are named `answer_…`, so session ids never reach a card (paths are
  opaque). Sessions are listed out of date order in 211 of 500 haystacks; they are ingested by date. Of the
  72 non-abstention knowledge-update questions, all have two evidence sessions; date order agrees with the
  `_1`/`_2` suffix in 71 (`618f13b2` disagrees; date order decides); 70 have `has_answer` turns in both
  sessions and get lineage. Every answerable question has `has_answer` turns, but 45 of their evidence
  sessions have none, so card-level judgments leave those sessions out (session level keeps them). The 21
  questions with no `has_answer` turn are all abstention questions.
- **LoCoMo.** 8 evidence ids name no turn (dropped); 8 questions are left without evidence (unscored).
- **MEME.** All 2,334 gold facts are conveyed in user turns, one per turn. 5 questions target entities with
  no conveyed fact (`pl_010` and `pl_015` Tracking on `partner`, three before-change questions): unscored.
  2 if-then rules have no stored dependent value. 2 episodes (`sw_019`, `sw_037`) delete an entity that
  other facts depend on, which exercises `missing_baselines`.
- **MemoryAgentBench.** No evidence annotations exist (`keypoints` and `previous_events` are empty). Labels
  are derived from the answer (below): 293 of 400 single-hop questions get one, 107 don't (the best subject
  match isn't unique), 208 form a clean conflict (an earlier fact with the same wording up to the object,
  none later), 80 have no conflicting fact, and 5 have a later conflicting fact, so their gold answer is not
  the latest fact (data inconsistency; kept for Mode A, left out of Mode B). Multi-hop questions are not
  used: their intermediate hops can't be labeled from the answer.

## Compilation (fixed now)

One rule set for every dataset ([`corpus.py`](corpus.py)):

| Field | Rule |
| --- | --- |
| Path | Opaque, chronological: `s007` (session), `s007/r002` (round), `s007/t013` (turn); zero-padded so address order, the engine's last tie-break, is time order |
| Title, tags | The card's speakers, in order of appearance ("User and Assistant", "Caroline") |
| Summary | The card's first line of dialogue (the first user line where the dataset has roles), cut to 240 characters, leading Markdown removed |
| Body | `- Date: …`, then `- Speaker: text` per turn in full; image captions as `- Speaker shared an image: …` |
| Safety | `[[` is written `[ [`, so dialogue can't create links; files are exactly what `write(op="create")` writes (tested) |

Granularities: LongMemEval and MEME `session` and `round` (a user turn plus the assistant turns after it);
LoCoMo `session` and `turn` (LoCoMo's evidence is per turn, and both speakers are people); MemoryAgentBench
one card per numbered fact. Each haystack gets a fresh workspace with everything in `@overlay`.

**Judgments** (a card is judged when it holds an evidence turn; all judged cards count equally):

| Dataset | Evidence |
| --- | --- |
| LongMemEval-S | Sessions: `answer_session_ids`. Cards: `has_answer` turns |
| LoCoMo | `evidence` dialogue ids, and their sessions |
| MEME | The turns conveying the target entities' gold facts. Cascade and Absence: every fact along the dependency chain up to the root, the change included. Before-change questions: the target's values stored by then (no rules) |
| MemoryAgentBench | The fact ending with an answer alias whose remaining words share the longest run with the question, when unique |

**Mode B lineage** ([`datasets.py`](datasets.py)), applied in order through `Workspace.write`:

| Annotation | Write |
| --- | --- |
| A later value of the same entity (MEME Tracking steps and the root change; LongMemEval's newer evidence turn; MemoryAgentBench's latest fact) | `create` with `supersedes = [previous value's card]` |
| A fact determined by another entity (MEME `dependency_source`) | `create` with `extends = [source's current value card]` |
| An if-then rule (MEME `is_if_then`) | `create` with `extends = [the dependent's current value card]` |
| A deletion request (MEME `type = "delete"`) | `op="delete"` on every stored value card of the entity; the request itself is not stored |

MEME's before-change questions are asked right after their session (`position_after_session`), in both modes.

## Metrics

Retrieval metrics are `evals/retrieval/metrics.py`'s with binary relevance: Recall@5, Recall@10, MRR@10
(first judged card), nDCG@5, and All@10 (every judged item on the page), at **card** level (the ranked
cards) and **session** level (the ranked cards' sessions, first occurrence kept). Intervals: 95% percentile
bootstrap over questions (2,000 replicates, seed 20261106); differences are paired.

**Abstention.** AUROC of two signals between answerable and unanswerable questions, with a bootstrap that
resamples within each class: `coverage_max` (the best `coverage` on the first page) and matched share
(1 minus unmatched query words over query words). 0.5 means no separation.

**Mode B state metrics** for questions about current state (MEME Cascade, Absence and Deletion after the
change; LongMemEval knowledge updates with lineage; MemoryAgentBench conflicts):

- `stale@10`: a card holding a superseded or pre-change value is on the first page **unwarned**, with
  `status = "active"` and no `baseline_superseded_by`.
- `stale-first`: an unwarned stale card ranks above every current card.
- `current@10`: the share of current-value cards on the first page (MEME Cascade: the replacement rule).
- `value-leak@10` (Deletion): a card other than the deletion request still states the deleted value.
- `history@10` (Tracking): share of the value history among the results; `history-named@10` also counts
  `matched_via_superseded`.

## Lines and verdicts, fixed now

Verdict rules as in `evals/retrieval`: **confirmed** (interval's lower bound at or above the line),
**point pass** (point estimate at or above, lower bound below) and **miss**. Structural lines pass only at
100%; a failure is an engine or compiler bug until shown otherwise. A miss stays a miss: nothing in the
engine changes because of these results.

| Line | Claim | Statistic | Line | Expected now |
| --- | --- | --- | --- | --- |
| A1 | LongMemEval-S, round cards: `coverage` separates abstention questions | AUROC `coverage_max` | 0.90 | miss: abstention questions reuse the haystack's words |
| A2 | Same, `unmatched_terms` | AUROC matched share | 0.90 | miss, though the asked-about noun is sometimes absent |
| A3 | LoCoMo, turn cards: `coverage` separates adversarial questions | AUROC `coverage_max` | 0.90 | miss, near 0.5: they swap the speaker, not the words |
| A4 | Same, `unmatched_terms` | AUROC matched share | 0.90 | miss, near 0.5 |
| B1 | `read(old root value)` forwards to the change card | all MEME episodes | 100% | pass |
| B2 | ...and lists exactly its extensions in `unrebased_extensions` | all episodes | 100% | pass |
| B3 | `read(dependent)` names the root change in `baseline_superseded_by` | Cascade and Absence, 1 and 2 hops | 100% | pass (the closure covers 2 hops) |
| B4 | Cascade: the replacement rule is in the dependent's `extensions` | Cascade | 100% | pass |
| B5 | Deleted cards raise `not_found` | all deletions | 100% | pass |
| B6 | Deleted cards never appear in search results | all questions | 100% | pass |
| B7 | A card extending a deleted card reports `missing_baselines` | `sw_019`, `sw_037` | 100% | pass |
| B8 | Tracking: the `supersedes` chain rebuilds the full history in order | Tracking | 100% | pass |
| B9 | Tracking: `read(first value)` forwards to the latest along that chain | Tracking | 100% | pass |
| B10 | `read(stale)` forwards to the current card | LongMemEval updates, MemoryAgentBench conflicts | 100% | pass |
| B11 | Search previews flag 2-hop dependents | Cascade and Absence, hop 2, when on the page | – | **known gap**, read from the code before running: previews compute `baseline_superseded_by` over direct baselines only, while `read()` follows the closure |
| C1 | Without lineage, stale outranks current | `stale-first`, flat, pooled | 0.20 | confirmed: lexically, the old and new facts look alike |
| C2 | Lineage cuts that | `stale-first`, flat minus lineage, pooled, paired | 0.20 | confirmed, less MEME 2-hop (B11) |
| C3 | Lineage costs current-fact recall at most 0.02 | `current@10`, lineage minus flat, pooled, paired | −0.02 | confirmed: a replacement inherits its predecessor's best score |

C1 to C3 pool MEME Cascade (both hops), LongMemEval knowledge updates and MemoryAgentBench conflicts.
**Mode A has no lines.** No earlier MindSlice reading of these benchmarks exists to set them from, and
published numbers use other chunking, other BM25 implementations and often LLM-written keys, so they
are not comparable. This run becomes the baseline that future engine changes are compared against.

**Known biases, stated now.** The same agent wrote the engine's evaluation harnesses, these compilers and
these lines, and read the engine's code first (B11 says so). The benchmarks' questions and annotations
were written independently of MindSlice, which is the point of this evaluation. But card templates are a
choice: a different summary rule would move Mode A. That is why the rule is fixed above and applied to
every dataset alike.

## Engine `ac7928a`: amended lines (2026-11-07)

`ac7928a` makes `search()` previews carry `read()`'s baseline notices over the whole `extends` closure:
`baseline_superseded_by` at any depth, and `missing_baselines` when a reference on the chain no longer
resolves (engine source digest `2d682415d4d98292e926e16f48fb8b53803d2823307a0703f24d3be7c170e1b8`). The
lines above stay as the record of `16223dc`. For this engine and later ones:

- **A preview warns** when `status` is not `active`, or it carries `baseline_superseded_by` **or
  `missing_baselines`**. This changes `stale@10`, `stale-first` and the end-to-end preview flag. At `16223dc`
  no preview carried `missing_baselines`, so its numbers are the same under either definition.
- **B11 becomes a structural line**: search previews flag every 2-hop dependent that is on the page, by
  either notice. 100%, like B1-B10.
- **C2** is expected confirmed with no MEME 2-hop exception.

Stated plainly: while making the fix, an in-memory run (nothing written to `results/`) had already shown
87 of 89 previews flagged by `baseline_superseded_by`, the other 2 (`sw_019`, `sw_037`) carrying
`missing_baselines`, and every page's ranking unchanged. So these amendments were written after seeing that
run, not before it. They change definitions to match the engine's two documented signals, not thresholds.

## Mode C: write-time supersession candidates (rules fixed 2026-11-07, before any probe)

**Question.** Mode B's gains need an agent to write `supersedes`, and without it the stale fact wins
(C1). The same thing that makes the stale fact win, that old and new statements share their words, might
let the engine *find* the old card when the new one is written and name it to the agent. Is a lexical
candidate list at write time precise enough to offer? No LLM is involved, and the engine is unchanged:
the harness calls `search()` the way a `write()` implementation would, just before each write.

**Writes probed.** Mode B ingestion, unchanged (same datasets, granularities and order: LongMemEval-S
round cards, MEME `filler32k` round cards, MemoryAgentBench fact cards).

- **Positive**: every card written with a non-empty `supersedes` (LongMemEval's newer evidence, MEME
  updates and root changes, MemoryAgentBench's latest facts). Its *predecessors* are its `supersedes`
  targets. Probed just before its `write()`, so the workspace holds everything written up to then.
- **Plain**: cards with no lineage, a deterministic sample: a card is kept when
  `int(sha256("neg/<haystack>/<path>")[:8], 16) % m == 0`, with m = 8 (LongMemEval), 5 (MEME) and 13
  (MemoryAgentBench): 2,000 to 2,100 of LongMemEval's 16,939, MEME's 9,102 and MemoryAgentBench's 25,472
  plain cards (Mode B ingests only the haystacks with lineage: 70, 100 and 4). Probed just before its
  session's files are added.
- **Extends**: every card written with `extends` and no `supersedes` (MEME dependents and rules). They
  replace nothing but are close to their baseline by construction: the case where a wrong hint would
  hurt most (a false `supersedes` hides a valid card). Reported, no line.

**Probe.** `search(query, k=5)` with defaults, where the query is the card's text as written minus its
title and its `Date:` line (both are harness templates: the speakers' names, and a session date no agent
would restate as content). Two query variants, chosen on `dev` below: `full` (summary and body) and
`summary` (summary only). Candidates are the top 3 results; a candidate is **hinted** when its `coverage`
(the engine's IDF-weighted share of the query it matches) is at least a threshold t.

**Split.** A write is `dev` when `int(sha256("split/<haystack>/<path>")[:8], 16)` is even, `holdout`
otherwise, for all three groups.

**Selection on `dev`, fixed now.** Over both variants and t in {0.00, 0.05, ..., 0.95}: the (variant, t)
with the highest positive recall (a predecessor is hinted) subject to a plain-write fire rate (any
candidate hinted) at or below 0.10. Ties: lower fire rate, then higher t. If no pair qualifies, H2a and
H2b are misses by rule, and H1 uses the variant with the higher `dev` R@3.

**Lines, read once on `holdout`** (95% bootstrap over writes, 2,000 replicates, seed 20261106; verdicts as
above, and for H2b, where lower is better, **confirmed** when the upper bound is at or below the line):

| Line | Claim | Statistic | Line | Expected now |
| --- | --- | --- | --- | --- |
| H1 | The predecessor is findable lexically | R@3 (no threshold), pooled positives | 0.80 | uncertain: MemoryAgentBench's facts differ by one word, MEME's updates often reword the value |
| H2a | A thresholded hint finds it | positive recall at the `dev` (variant, t) | 0.60 | uncertain |
| H2b | ...and stays quiet on unrelated writes | plain-write fire rate at the same (variant, t) | 0.20 | likely, if the threshold exists |

Also reported, no lines: per-dataset R@1 and R@3, recall and fire rate, the `extends` group's fire rate
and how often its hint names its own baseline, and mean hinted cards per write.

**What would follow (the decision stays the user's).** H1, H2a and H2b hold: an optional write-time
`similar_active` list is worth building and testing with agents ([`evals/agent_test.md`](../agent_test.md)).
H1 holds but H2 doesn't: candidates exist but no threshold separates them, so leave it to the skill's
"search first". H1 misses: lexical matching can't find predecessors often enough; noticing supersession
is the agent's job, and the agent test is the only measure.

**Known biases.** Round cards hold a whole exchange, so the query carries the assistant's reply as well as
the user's new fact: a harder case than an agent's focused card. MemoryAgentBench's conflicts are
templated and differ by their object, which favors lexical matching. Same author as above.

## Ledger

| Date | Run | What it informed |
| --- | --- | --- |
| 2026-11-07 | Data pinned; compilers, checks and this plan written; harness tested on synthetic data only | Nothing searched on benchmark data. Harness digest at freeze: `70bb3a1022d4d8a5b50b234f374912810101d1a59ac3bd9a863ed90d20d3438f` (`run.json` records the one used) |
| 2026-11-07 | Run 1, every dataset, frozen harness | A1-A4 **miss** (as expected). B1, B4, B5, B7-B10 **pass**, B11 **gap confirmed**, C1-C3 **confirmed**. **B2, B3 and B6 failed**; diagnosed as wrong check expectations, not engine faults: (B6) the count included MEME's before-change searches, made while the deleted cards still existed (162 sightings, none after a deletion); (B2) in `sw_019` and `sw_037` the expected `unrebased_extensions` included a card the episode deletes; (B3) in those two episodes the 2-hop middle entity is the one deleted, so the dependent's chain no longer reaches the root and `read()` correctly reports `missing_baselines` instead (B7 passes on exactly those cards). Also found while reading: `no-rule` fails on 10 Absence questions because MEME declares a replacement rule for their target (the middle of a 2-hop chain) while labeling them "Uncertain"; this is a data note, not a line. The miss analysis ("no judged card matches any query word") was uninformative, since filler words match every card |
| 2026-11-07 | Check and diagnostics fixes, then run 2 (harness `592abe69…`) | Checks: B6 counts after-change searches only; B2's expectation excludes deleted cards; B3 (and the end-to-end read flag) also accepts `missing_baselines`. Records gained first-page `scores` and, for flat misses, each query word's share of cards and whether a judged card holds it. The miss analysis became the exploratory **distinctive-word** reading (a word in under 10% of the haystack's cards; threshold chosen after run 1). **All 11,568 first pages (results, lineage markers, coverage, unmatched terms) are identical to run 1**, so no ranking changed |
| 2026-11-07 | Summary fixes, re-rendered from run 2's records with `report` (summarized by `39401459…`, recorded in `run.json`) | Found while diagnosing a MEME Cascade row: the ablation paired each lineage record with the flat record of the same question id, and MEME's `filler32k` and `nofiller` share ids, so MEME rows had compared against `nofiller`'s flat pages (now keyed by dataset; a test covers it). MemoryAgentBench's session level was dropped (its facts form one list, so it was trivially 1.0). **Final verdicts:** A1-A4 miss; B1-B10 pass; B11 gap confirmed; C1 0.620 [0.572, 0.665], C2 0.595 [0.550, 0.638], C3 +0.007 [0.000, 0.016], all **confirmed**. Nothing in the engine changed |
| 2026-11-07 | Engine fix `ac7928a` (B11), checked with an in-memory run against run 2's records, nothing written | Every one of the 11,568 first pages has the same ranking and scores. Previews flag 87 of the 89 hop-2 dependents by `baseline_superseded_by`; the other 2 (`sw_019`, `sw_037`) carry `missing_baselines`, which the harness did not yet count. Led to the amendments above |
| 2026-11-07 | Run 3: engine `ac7928a` (`2d682415…`), harness `08ca1621…` with the amended definitions, recorded at `a90e19a` | **B11 pass** (89 / 89). **C2** 0.620 [0.572, 0.665] **confirmed**: under lineage, `stale-first` is 0.000 (was 0.025) and pooled `stale@10` 0.000 (was 0.111). A1-A4, B1-B10, C1 and C3 unchanged. In `checks.jsonl` only the 89 hop-2 end-to-end rows changed |
| 2026-11-07 | Mode C rules written (the section above, SHA-256 `b326b43e5d09aca7de95076127e54cb7d2793693b30440e27c4d1a962e5cf5cd` as first written), before its code existed | Nothing probed on benchmark data |
| 2026-11-07 | Mode C amendment, before any probe: counted the writes (cards only, nothing searched) | Mode B ingests only haystacks with lineage, so LongMemEval has 16,939 plain cards, not ~120,000: m = 60 would sample 306, not the ~2,000 the rule meant. m changed to 8. Positive writes: 70 LongMemEval, 307 MEME, 205 MemoryAgentBench; MEME `extends` writes: 541 |
| 2026-11-07 | Mode C code (`hints.py`, the `hints` subcommand) written and tested on synthetic data only; harness `d0584239…` | Nothing probed on benchmark data. Mode A and B code paths unchanged (`run.py` only gains the subcommand) |
| 2026-11-07 | Mode C `dev` (274 positive, 2,868 plain, 283 extends writes) | **Selection by rule: `full`, coverage ≥ 0.30** (recall 0.540, plain fire 0.063). Dev R@3 0.748 (`full`). Seen, not acted on: `extends` writes fire 0.855 and the hint names their own baseline in 0.548; LongMemEval R@3 is 0.353. Nothing changed before the holdout read |
| 2026-11-07 | Mode C `holdout`, once, with `dev`'s selection (308 positive, 2,942 plain, 258 extends writes) | **H1 miss** (R@3 0.685 [0.633, 0.734]). **H2a miss** (0.506 [0.451, 0.562]). **H2b confirmed** (0.062 [0.053, 0.070]). By the rule above: lexical matching does not find predecessors often enough to offer a write-time hint; noticing supersession stays the agent's job, measured by `evals/agent_test.md`. By dataset (R@3): MemoryAgentBench 0.980, MEME 0.613, LongMemEval 0.222. Exploratory, after the verdict: the `summary` query gives LongMemEval 0.500 and pooled 0.701 (still under the line); at the selected setting the hint fires on 215 of 258 `extends` writes, and in 120 of those its top card is the card being extended, so a "may supersede" hint would invite exactly the harmful error. The engine is unchanged |
| 2026-11-07 | Run 4: run 3 repeated with the final harness (`d0584239…`, which adds Mode C), so `run.json` matches the code | `summary.md` and `checks.jsonl` byte-identical to run 3. In `per_query.jsonl` (not committed) only the order of `gold` lists differs (they come from sets, whose order varies between processes); every ranking, score and warning is identical |
