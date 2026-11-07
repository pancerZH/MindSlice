# MindSlice on external memory benchmarks: findings

Engine `16223dc` (unchanged by this work) on LongMemEval-S, LoCoMo, MEME and MemoryAgentBench, with **no
language model anywhere**: the benchmark dialogue is compiled into cards by fixed rules, the questions go to
`search(question, k=10)` verbatim, and `read()` / `search()` responses are scored against the datasets'
annotations. 11,568 first pages across about 1,600 workspaces; a rerun gives identical pages. Rules and
lines were fixed before any question was searched ([PLAN.md](PLAN.md)); every table is in
[results/summary.md](results/summary.md).

## In short

1. **Lexical search finds stated facts well, and paraphrased ones poorly.** When the question reuses the
   words of the evidence, recall is near complete: LongMemEval single-session user and assistant questions
   0.98-1.00, MEME exact recall 1.00, MemoryAgentBench 0.98 Recall@10. When it doesn't, recall collapses:
   LoCoMo multi-hop and open-domain questions 0.30 at turn level, MEME's "what do I do in my free time?" 0.40. Of the
   first-page misses, most share none of the question's distinctive words with the evidence (LoCoMo 242 of
   531, MEME 36 of 48).
2. **`coverage` and `unmatched_terms` do not reliably flag unanswerable questions** (A1-A4 miss). The best is
   LongMemEval's abstention set, AUROC 0.67-0.69: `unmatched_terms` is non-empty for 43% of abstention
   questions but also for 7% of answerable ones. On LoCoMo's adversarial questions it is chance (0.51-0.55).
3. **Without lineage, the stale fact usually wins.** Over 442 state questions, a superseded or pre-change
   fact outranks the current one on 62% of first pages (C1), because the old and new statements share their
   words. With lineage written from the annotations, that drops to 2.5% (C2), at no recall cost (C3).
4. **The engine's lineage mechanics hold at benchmark scale.** Every structural check passes (B1-B10, 1,333
   checks), including 2-hop dependency invalidation through `read()` and `missing_baselines` after a
   deleted dependency.
5. **Two limits show up.** Search previews don't flag 2-hop dependents (B11, read from the code beforehand):
   all the residual stale exposure under lineage is that case. And exact BM25 ties break by address, so the
   older card comes first: 103 of MemoryAgentBench's 162 stale-first pages are exact ties.

## What was run

| Dataset | Haystacks | Questions | Cards built | Evidence used |
| --- | --- | --- | --- | --- |
| LongMemEval-S (cleaned) | 500 | 500 (30 abstention) | 23,867 session, 122,487 round | `answer_session_ids`, `has_answer` turns |
| LoCoMo | 10 | 1,986 (446 adversarial) | 272 session, 5,882 turn | `evidence` dialogue ids |
| MEME `filler32k` / `nofiller` | 100 / 100 | 1,188 each (494 before, 694 after the change) | 10,050 / 2,603 round | `gold_facts` turns, dependency chains |
| MemoryAgentBench, single-hop conflicts | 4 (6k-262k) | 293 labeled of 400 | 25,677 fact | derived from the answer (no annotations exist) |

Mode A searches flat cards. Mode B adds `supersedes` (updates), `extends` (dependencies and if-then rules)
and `op="delete"` (deletion requests), compiled from the annotations and written through
`Workspace.write`, then checks the responses. The lineage is the annotations', not an agent's: Mode B
shows what the engine does with correct lineage, not whether an agent would write it.

## Mode A: retrieval

First answerable questions (LongMemEval without abstention, LoCoMo without adversarial, MEME after the change):

| Benchmark | Cards | Level | n | Recall@5 | Recall@10 | MRR@10 | nDCG@5 | All@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LongMemEval-S | round | card | 470 | 0.789 | 0.882 [0.858, 0.907] | 0.735 | 0.700 | 0.813 |
| LongMemEval-S | round | session | 470 | 0.925 | 0.942 [0.927, 0.958] | 0.914 | 0.892 | 0.875 |
| LongMemEval-S | session | session | 470 | 0.925 | 0.960 [0.946, 0.974] | 0.919 | 0.897 | 0.917 |
| LoCoMo | turn | card | 1,532 | 0.508 | 0.584 [0.561, 0.609] | 0.434 | 0.426 | 0.529 |
| LoCoMo | turn | session | 1,532 | 0.815 | 0.871 [0.856, 0.886] | 0.734 | 0.727 | 0.809 |
| LoCoMo | session | session | 1,532 | 0.834 | 0.913 [0.901, 0.925] | 0.749 | 0.744 | 0.865 |
| MEME `filler32k` | round | card | 692 | 0.577 | 0.661 [0.635, 0.686] | 0.800 | 0.607 | 0.383 |
| MEME `filler32k` | session | session | 692 | 0.689 | 0.833 [0.815, 0.852] | 0.823 | 0.674 | 0.643 |
| MEME `nofiller` | round | card | 692 | 0.659 | 0.769 [0.750, 0.789] | 0.875 | 0.685 | 0.468 |
| MemoryAgentBench | fact | card | 293 | 0.973 | 0.976 [0.956, 0.993] | 0.691 | 0.764 | 0.976 |

**Where it works.** Questions that restate the evidence:

| Group | Recall@10 |
| --- | --- |
| LongMemEval-S, single-session-assistant / single-session-user (round cards) | 1.000 / 0.984 |
| LongMemEval-S, knowledge-update (round cards) | 0.961 |
| MEME, exact recall (verbatim) | 1.000 |
| MEME, before-change questions (Cascade hop 1, Absence hop 1, Deletion) | 0.970 / 0.990 / 0.990 |
| MemoryAgentBench (entity names in both question and fact) | 0.976 |

**Where it doesn't.** Questions whose words aren't the evidence's, or that need several pieces of it:

| Group | Recall@10 | Why |
| --- | --- | --- |
| LoCoMo multi-hop / open-domain (turn cards) | 0.298 / 0.296 | Evidence spread over turns that each share few words with the question |
| MEME aggregation, "What do I do in my free time?" | 0.395 | The evidence says "hobby", "club", "I play"; never "free time" |
| MEME Absence hop 2 / Cascade hop 1, whole chain (All@10) | 0.100 / 0.040 | The rule, the dependency and the trigger rarely share a page |
| LongMemEval-S single-session-preference | 0.756 (MRR 0.426) | Preferences are implied, not named ("dinner suggestions" vs "my cherry tomatoes and basil") |

Bigger cards help lexical recall: whole-session cards beat turn cards at session level on LoCoMo (0.913
vs 0.871) and MEME (0.833 vs 0.756), since a session holds more of the question's words. The price is
precision for the reader: a session card is a whole conversation. Filler costs MEME about 0.11 Recall@10
(0.661 with it, 0.769 without).

### Vocabulary gaps

A query word counts as *distinctive* when fewer than 10% of the haystack's cards contain it (an
exploratory reading defined after run 1). A first-page miss is a *vocabulary gap* when no evidence card
contains any of the question's distinctive words, and *outranked* when one does but ten cards rank higher:

| Corpus | Misses | Vocabulary gap | Outranked (median rank) |
| --- | --- | --- | --- |
| LoCoMo, turn cards | 531 of 1,532 | 242 | 287 (26) |
| LongMemEval-S, round cards | 26 of 470 | 10 | 15 (15) |
| MEME `filler32k`, round cards | 48 of 692 | 36 | 7 (12) |
| MEME `nofiller`, round cards | 9 of 692 | 9 | 0 |
| MemoryAgentBench | 7 of 293 | 0 | 7 (86) |

Typical gaps, with the evidence turn:

- LoCoMo: "What is Caroline's **identity**?" → "The **transgender** stories were so inspiring!" (rank 320)
- LoCoMo: "What **fields** would Caroline be likely to **pursue** in her **educaton**?" → "I'm keen on
  **counseling** or working in mental health", "Gonna continue my **edu**" (rank 156; note the typo)
- LongMemEval: "How long have I been working in my current **role**?" → "my 3 years and 9 months
  **experience in the company**" (rank 74)
- MEME: "What do I do in my **free time**?" → "My **hobby** is guitar", "I'm part of a hiking **club**" (rank 13)

These are synonym and paraphrase gaps, which no lexical engine bridges. In MindSlice that is the job of
card authoring (titles, summaries, `aliases`): the retrieval evaluation's `holdout-3` measured +0.16 nDCG@5
from skill-written aliases on its vocabulary-gap queries. This harness compiles templates, not authored
cards, so it shows the gap without that remedy.

## Abstention signals

| Corpus | AUROC `coverage_max` | AUROC matched share | `unmatched_terms` non-empty (answerable / unanswerable) |
| --- | --- | --- | --- |
| LongMemEval-S, round cards (470 / 30) | 0.671 [0.564, 0.770] | 0.688 [0.598, 0.777] | 6.8% / 43.3% |
| LoCoMo, turn cards (1,540 / 446) | 0.512 [0.481, 0.541] | 0.553 [0.528, 0.577] | 23.1% / 34.5% |
| MEME, Absence and Deletion vs the rest (464 / 230) | 0.218 [0.187, 0.252] | 0.285 [0.259, 0.312] | 47.8% / 3.9% |

- **LongMemEval abstention** questions ask about something never mentioned ("What is the name of my
  hamster?", when the user has a cat). `unmatched_terms` is non-empty for 43% of them (it returns
  `["hamster"]` there), and for 7% of answerable ones: a useful hint for an agent, not a classifier.
- **LoCoMo adversarial** questions swap the person ("What did Caroline realize after her charity race?",
  when it was Melanie's race), so every word matches and lexical signals see nothing.
- **MEME's Absence and Deletion** questions are short and name the entity directly, so they match *better*
  than average (inverted AUROC). Their "unanswerability" is about time, not words. Lexical signals can't
  see it; lineage can (next section).

## Mode B: lineage

### The mechanism, checked against the compiled lineage

| Line | Check | Result |
| --- | --- | --- |
| B1, B2 | `read(old root value)` forwards to the change card and lists exactly its dependents as `unrebased_extensions` | 100 / 100 each |
| B3 | `read(dependent)` names the root change in `baseline_superseded_by`, at 1 and 2 hops (the `extends` closure); or `missing_baselines` when the chain runs through a deleted card | 291 / 291 (2 via `missing_baselines`) |
| B4 | Cascade: the replacement rule is in the dependent's `extensions` | 162 / 162 |
| B5-B7 | Deleted cards raise `not_found`, never appear in later searches, and their dependents report `missing_baselines` | 101 / 101, 100 / 100, 3 / 3 |
| B8, B9 | Tracking: `supersedes` rebuilds the history in order; `read(first)` forwards along it | 98 / 98 each |
| B10 | Knowledge updates and conflicts: `read(stale)` forwards to the current card | 280 / 280 |
| B11 | Search previews flag 2-hop dependents | 0 of 89 on the page (**known gap**) |

End to end, starting from the question's first page as an agent would (MEME, after the change):

| Group | Dependent or rule on page | Flagged in the preview | Flagged after `read()` | Rule reachable |
| --- | --- | --- | --- | --- |
| Cascade, hop 1 (100) | 0.970 | 0.970 | 0.970 | 0.970 |
| Cascade, hop 2 (62) | 1.000 | **0.000** | 1.000 | 1.000 |
| Absence, hop 1 (100) | 0.990 | 0.990 | 0.990 | n/a |
| Absence, hop 2 (29) | 0.931 | **0.000** | 0.931 | n/a |

The one-search-one-read pattern gives an agent the signals MEME's Cascade and Absence tasks need: "your
basis changed, and here is the declared replacement" versus "your basis changed, and nothing replaces it".
[The MEME paper](https://arxiv.org/abs/2605.12477) reports these two tasks as the hardest for the memory
systems it tested. With 2-hop dependents, the signal appears only after `read()`.

### Lineage versus flat cards

Same cards, same questions:

| Group | Metric | Flat | Lineage |
| --- | --- | --- | --- |
| **Pooled** (442: MEME Cascade, LongMemEval updates, MemoryAgentBench conflicts) | stale outranks current | 0.620 [0.572, 0.665] | 0.025 [0.011, 0.041] |
| | stale fact on page, unwarned | 0.934 | 0.111 |
| | current fact on page (Recall@10) | 0.959 | 0.966 |
| LongMemEval knowledge updates (70) | stale outranks current | 0.586 | 0.000 |
| MemoryAgentBench conflicts (208) | stale outranks current | 0.779 | 0.000 |
| MEME Cascade, hop 1 / hop 2 | stale outranks current | 0.600 / 0.172 | 0.000 / 0.172 |
| MEME Absence, hop 1 / hop 2 | stale fact on page, unwarned | 0.990 / 0.900 | 0.000 / 0.900 |
| MEME Deletion (100) | deleted value still on page | 0.800 | 0.040 |
| MEME Tracking (100) | history among results | 0.718 | 0.309 |
| | history named on the page (results + `matched_via_superseded`) | 0.718 | 0.929 |

- **Lexical ranking can't tell old from new.** The stale and current statements share their words, so the
  order comes down to length normalization, and on exact ties to the address. Paths are chronological, so
  the older card wins: 103 of MemoryAgentBench's 162 stale-first pages are exact score ties.
- **`supersedes` fixes it completely where it applies**: hits on the old card redirect to the replacement,
  which keeps the best score of the group.
- **All remaining exposure is 2-hop** (MEME hop 2: 0.172 and 0.900 are unchanged). Neither card involved is
  superseded; only the baseline of a baseline is, and previews look one hop deep (B11).
- **Deletion is per card.** Deleting the fact's cards removes 95% of the leaks. Of the 4 pages left, two
  are coincidences (an assistant suggesting "dairy-free pancakes", a "bus" in a filler session). The other
  two matter: the dependent card restates the deleted value as its basis ("…determined by the fact that our
  CI is orinthal-build.yml"). `read()` flags it with `missing_baselines` (B7), but its text still says it.
- **Supersession trades visible history for recency.** Tracking's earlier values leave the result list but
  stay on the page as `matched_via_superseded` (0.93, more than flat's 0.72) and in the `supersedes` chain (B8).

## Dataset issues found along the way

- **MEME** labels 10 Absence questions "Uncertain" although it declares a replacement rule for their target
  (the target is also the middle of a 2-hop chain, e.g. "If my health condition changes, my exercise routine
  will be yoga 2x/week"). Five questions target entities with no conveyed fact.
- **MemoryAgentBench** has no evidence annotations. In 5 single-hop questions, the gold answer is the
  *earlier* of two conflicting facts, against the benchmark's own latest-fact rule. For 107 questions, the
  fact holding the answer can't be singled out from the question's wording.
- **LongMemEval-S** names evidence sessions `answer_…` (an id that must never reach an index). One
  knowledge-update pair is dated against its `_1`/`_2` order. Sessions are out of date order in 211
  haystacks.
- **LoCoMo** has 8 evidence ids that name no turn.

## What this does not show

- **Answer accuracy.** That needs a reader model; these are retrieval and structure measurements.
- **Whether an agent writes good lineage.** Mode B's lineage is the annotations'. In practice the
  bottleneck is an agent noticing that a new statement supersedes an old one; this harness gives the
  oracle for that, not the agent.
- **Authored cards.** Titles, summaries and aliases here are templates. Authored cards would change Mode A
  (aliases did on the retrieval evaluation).
- **Comparisons with published systems.** They chunk, weight and key differently, often with LLM-written
  memory. Read these numbers against future MindSlice versions on this harness.

## Possible engine follow-ups (not made; each needs its own evaluation)

1. **Closure in previews.** Compute `baseline_superseded_by` over the `extends` closure in `search()`
   previews, as `read()` does. That would remove all remaining stale exposure here (0.111 → 0, by B11's
   arithmetic), at some cost per result.
2. **Recency on exact ties.** Exact BM25 ties currently fall to precedence, then address, which favours the
   older card when paths are chronological. Ordering ties by `mtime_ns`, newest first, would flip most of
   MemoryAgentBench's stale-first pages without lineage. It is a ranking change, so it needs a fresh
   holdout first, as `evals/retrieval/PLAN.md` requires.
3. **Nothing for vocabulary gaps in the engine.** By the design's own split, that belongs to authoring
   (aliases, the `slice-builder` skill) and to the agent rephrasing after `unmatched_terms`.
