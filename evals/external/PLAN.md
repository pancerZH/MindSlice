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

## Ledger

| Date | Run | What it informed |
| --- | --- | --- |
| 2026-11-07 | Data pinned; compilers, checks and this plan written; harness tested on synthetic data only | Nothing searched on benchmark data. Harness digest at freeze: `70bb3a1022d4d8a5b50b234f374912810101d1a59ac3bd9a863ed90d20d3438f` (`run.json` records the one used) |
| 2026-11-07 | Run 1, every dataset, frozen harness | A1-A4 **miss** (as expected). B1, B4, B5, B7-B10 **pass**, B11 **gap confirmed**, C1-C3 **confirmed**. **B2, B3 and B6 failed**; diagnosed as wrong check expectations, not engine faults: (B6) the count included MEME's before-change searches, made while the deleted cards still existed (162 sightings, none after a deletion); (B2) in `sw_019` and `sw_037` the expected `unrebased_extensions` included a card the episode deletes; (B3) in those two episodes the 2-hop middle entity is the one deleted, so the dependent's chain no longer reaches the root and `read()` correctly reports `missing_baselines` instead (B7 passes on exactly those cards). Also found while reading: `no-rule` fails on 10 Absence questions because MEME declares a replacement rule for their target (the middle of a 2-hop chain) while labeling them "Uncertain"; this is a data note, not a line. The miss analysis ("no judged card matches any query word") was uninformative, since filler words match every card |
| 2026-11-07 | Check and diagnostics fixes, then run 2 (harness `592abe69…`) | Checks: B6 counts after-change searches only; B2's expectation excludes deleted cards; B3 (and the end-to-end read flag) also accepts `missing_baselines`. Records gained first-page `scores` and, for flat misses, each query word's share of cards and whether a judged card holds it. The miss analysis became the exploratory **distinctive-word** reading (a word in under 10% of the haystack's cards; threshold chosen after run 1). **All 11,568 first pages (results, lineage markers, coverage, unmatched terms) are identical to run 1**, so no ranking changed |
| 2026-11-07 | Summary fixes, re-rendered from run 2's records with `report` (summarized by `39401459…`, recorded in `run.json`) | Found while diagnosing a MEME Cascade row: the ablation paired each lineage record with the flat record of the same question id, and MEME's `filler32k` and `nofiller` share ids, so MEME rows had compared against `nofiller`'s flat pages (now keyed by dataset; a test covers it). MemoryAgentBench's session level was dropped (its facts form one list, so it was trivially 1.0). **Final verdicts:** A1-A4 miss; B1-B10 pass; B11 gap confirmed; C1 0.620 [0.572, 0.665], C2 0.595 [0.550, 0.638], C3 +0.007 [0.000, 0.016], all **confirmed**. Nothing in the engine changed |
