# Agent-in-the-loop lineage test: report

Can an LLM agent that writes memory through MindSlice's four MCP tools keep stale facts behind current ones
without hiding true ones? Three runs, all scored by a deterministic harness against lines frozen before the
first call. The frozen setup is [PLAN.md](PLAN.md). How the protocol got here (the matcher post-mortems, and
the cost and quota re-freezes) is in [decision_ledger.md](decision_ledger.md). Generated tables are in
[results/](results/), with a short version in [results/summary.md](results/summary.md). (Where PLAN.md or the
frozen matcher modules cite this report's "Re-score" or "Matcher v3" sections, that material is now in the
decision ledger, section 3.)

## In short

1. **Out of sample, with a strong model, the design holds.** On MemoryAgentBench 32k, Argon `agent-policy`
   confirmed all four pre-registered lines: a stale fact ranks first on none of its 44 conflict pages (flat: 0.795),
   0.909 of stale facts are retired, and no true fact is lost.
2. **The same architecture helps one model and hurts another.** Mounting the raw history read-only, with the
   agent writing only lineage (`agent-overlay`), retires the most stale facts on Argon (+0.192 over
   `agent-policy`) and the fewest on a local 3-bit Qwen (−0.174).
3. **Agents keep the current fact findable** (`current@10` 0.994-1.000; flat 0.968) **and rarely lose one**
   (`lost` at most 0.004 in every cell).
4. **What goes wrong is mostly links and unflagged premises:** links to cards named after an old value, old
   per-value cards left active, raw rounds never superseded, and premise changes written in prose. After scoring,
   the engine and its guidance were changed to address all but the raw rounds (unmeasured).
5. **Answers, from the comparison reader so far.** Reading the same pages, the local Qwen answers
   0.76 of the after-change questions correctly from `oracle`'s memory and 0.48 from `flat`'s
   (+0.283, interval 0.222 to 0.341), with no cost before the change. The pre-registered lines are read
   on Argon, after the weekly Gemini reset; no dense raw-history RAG baseline has been run.

## The problem

MindSlice keeps current facts ahead of stale ones only if someone writes lineage. On four published memory
benchmarks ([`evals/external`](../external/REPORT.md)), with every turn as a card and no lineage, a stale fact
outranks the current one on 62% of first pages (442 state questions) and sits unwarned on 93%. With the
annotations' lineage, both drop to 0. The engine can't infer that lineage itself: a lexical hint at write time
finds the predecessor among the top 3 for only 0.685 of writes, and fires on most cards that merely extend a
baseline. So everything between 0.62 and 0 depends on the agent. This test measures where real agents land
([agent_test.md](../agent_test.md), the specification).

## Design

**Arms.** For each haystack, a fresh workspace and a fresh agent per session.

| Arm | Memory writer |
| --- | --- |
| `flat` | Every round (or fact) as a template card, no lineage: raw-history retrieval through the same search |
| `oracle` | The same cards plus the annotations' lineage |
| `agent-default` | An LLM agent with the MCP server as shipped and a neutral task prompt |
| `agent-policy` | The same, plus a lineage policy paragraph (search first; `supersedes`, `extends`, `delete`) |
| `agent-overlay` | The `flat` cards mounted read-only as `@history`; the agent writes only lineage into `@overlay` |

**Runs.**

| Run | Data | Cells | Status |
| --- | --- | --- | --- |
| Tier 1 | MEME `nofiller`, 95 episodes (1,136 questions) | `agent-default`, `agent-policy`, `agent-overlay` on `gemini-4-argon-medium`; `agent-policy` on `gemini-3.8-flash-medium`; 1,900 sessions plus 300 for three variance repeats | done 2026-11-08 |
| Confirmatory | MemoryAgentBench 32k (231 batches of 10 facts) | `agent-policy` on Argon | done 2026-11-08, pre-registered |
| Qwen tier 1 | Tier 1's episodes | `agent-policy` and `agent-overlay` on `qwen3.8-flash-next-iq3_s` (3-bit IQ3_S, local Strata server) | done 2026-11-09, pre-registered |

Each session is one fresh conversation (the Antigravity CLI, or `strata.py` for Qwen) over real MCP stdio.
Only the four MindSlice tools can run, with a cap of 40 calls. The agent never sees questions or answers.
At each question point the harness, not the agent, runs `search(question, k=10)` on the agent's workspace and
judges the page and the whole workspace by value strings.

**Lines** (PLAN.md section 5), pooled per cell, with 95% bootstrap intervals (2,000 replicates, seed
20261106; differences paired by unit). **Confirmed** means the interval clears the line, **point pass** that
only the mean does.

| Line | Statistic | Line |
| --- | --- | --- |
| G1 | `stale-first` (an unwarned stale card ranks above every current card), flat minus agent | ≥ 0.30 |
| G2 | `retired`: after an update, no active, unwarned card in the workspace still states the old value | ≥ 0.70 |
| G3 | `current@10` (a card on the page states the current value), agent minus flat | ≥ −0.05 |
| G4 | `lost`: a current value no active card states any more | ≤ 0.05 |
| G5 | `forgotten`: after a deletion request, no active card states the value | ≥ 0.90 |

**Reliability.** Before reading the lines, a fixed sample of up to 50 `retired` failures and 50 `lost` cases per
cell is judged by hand. If more than 20% are matching errors, the cell's lines are reported as unreliable
(agent_test.md 6.3). Under that rule, the pre-registered matcher's tier-1 lines were unreliable in every cell. The
numbers below use **matcher v3**, which was built from tier 1's audits (so it is post-hoc for the Gemini tier-1
cells), then frozen before the confirmatory run (its registered secondary scorer, which gives the same numbers as
the registered v2) and before Qwen tier 1. The post-mortems are in [decision_ledger.md](decision_ledger.md), section 3.

## Out-of-sample results

### MemoryAgentBench 32k: confirmatory run

Pre-registered in PLAN.md section 9: `agent-policy` on Argon, 2026-11-08 16:11Z-23:57Z, scored with matcher v2
as registered and v3 as registered secondary, which agree on every number. **G1-G4 confirmed:**

| Line | Line value | Agent | `flat` | Verdict |
| --- | --- | --- | --- | --- |
| G1 `stale-first` cut, flat minus agent (44 conflicts) | ≥ 0.30 | 0.795 [0.659, 0.909] | `stale-first` 0.795 (agent 0.000) | **confirmed** |
| G2 `retired` (44) | ≥ 0.70 | 0.909 [0.818, 0.977] | 0 | **confirmed** |
| G3 `current@10`, agent minus flat (66) | ≥ −0.05 | 0.000 [0.000, 0.000] | 0.970 (agent 0.970) | **confirmed** |
| G4 `lost` (63 values) | ≤ 0.05 | 0.000 [0.000, 0.000] | 0 | **confirmed** |

`oracle`: `stale-first` 0.000, `retired` 0.955. By the audit rule as registered, the lines are still reported
as unreliable: 3 of the 4 `retired` failures are matching errors, because MemoryAgentBench's subject anchors can
be one generic word ("capital", "state"; England's capital matched for the United Kingdom's). The fourth is real
(the General Motors card still lists Buick Regal). The errors only count real passes as failures, and none of
15 sampled passes missed a stale card, so the raw values are bounds and every verdict holds (corrected `retired`
0.977).

The agent wrote one card per fact (2,309 creates, 837 with `supersedes`) in 18.4 tool calls per session (max
31), with 0 cap hits, 4 tool errors and `DONE` in every session. Tables:
[results/confirm-mab32k-v2.md](results/confirm-mab32k-v2.md) (and `-v3`); audit: `results/audit/confirm-mab32k-v2/`.

### Qwen tier 1: a weaker model, same frozen protocol

Pre-registered in PLAN.md section 10 and scored with the frozen v3; both cells ran all 95 episodes with no failed
haystack (7.1 h and 9.3 h).

| Line | Line value | Qwen `agent-policy` | Qwen `agent-overlay` |
| --- | --- | --- | --- |
| G1 `stale-first` cut | ≥ 0.30 | 0.301 [0.224, 0.385] point pass | 0.256 [0.179, 0.327] **miss** |
| G2 `retired` | ≥ 0.70 | 0.566 [0.505, 0.623] **miss** (corrected 0.601) | 0.392 [0.335, 0.452] **miss** (corrected 0.352) |
| G3 `current@10` diff | ≥ −0.05 | +0.032 [0.006, 0.063] confirmed | +0.025 [0.006, 0.051] confirmed |
| G4 `lost` | ≤ 0.05 | 0.004 [0.002, 0.007] confirmed | 0.001 [0.000, 0.002] confirmed |
| G5 `forgotten` | ≥ 0.90 | 0.609 [0.511, 0.707] **miss** | 0.315 [0.228, 0.413] **miss** |
| Audit: `retired` / `lost` errors · missed in 15 passes | ≤ 20% | 4/50 · **4/13** · 0: unreliable (`lost`) | 1/50 · 0/3 · 2: **reliable** |

`agent-policy`'s `lost` errors only raise `lost`, so G4 holds; G2 and G5 miss whatever the errors. Tables:
[results/tier1-qwen-v3.md](results/tier1-qwen-v3.md); audit: `results/audit/tier1-qwen-v3/`.

### For context: tier 1 on Gemini (v3, post-hoc)

| Cell | G1 cut | G2 `retired` | G3 diff | G4 `lost` | G5 `forgotten` | 6.3 rule |
| --- | --- | --- | --- | --- | --- | --- |
| Argon `agent-default` | 0.327 point pass | **0.779 confirmed** | +0.032 confirmed | 0.004 confirmed | 0.989 confirmed | reliable |
| Argon `agent-policy` | 0.327 point pass | 0.730 point pass (corrected 0.681) | +0.032 confirmed | 0.002 confirmed | 0.978 confirmed | unreliable (`lost`, one value) |
| Argon `agent-overlay` | 0.321 point pass | **0.922 confirmed** | +0.032 confirmed | 0.003 confirmed | 0.946 point pass | reliable |
| Flash `agent-policy` | 0.327 point pass | 0.676 **miss** | +0.032 confirmed | 0.004 confirmed | 0.978 confirmed | reliable |
| `oracle` | 0.321 | 0.875 | 0.000 | 0.001 | 0.924 | |

G1 can't be confirmed on MEME alone: flat's own `stale-first` is 0.327, so no arm can cut more (the line was set
for a pooled tier with MemoryAgentBench). Every agent cell matches or beats the oracle's cut. The policy paragraph
doesn't help on top of the shipped tool descriptions (`agent-policy` minus `agent-default`: `retired` −0.050
[−0.100, 0.004]). Argon retires a little more than Flash (+0.053, interval touching 0) while reading about a
seventh of its context (17M against 115M tokens). Run-to-run variance (`agent-policy` on Argon, 20 episodes, four runs): `retired` 0.733-0.800 (SD
0.030). Full table, audit corrections and how to read them: [decision_ledger.md](decision_ledger.md), section 3;
[results/tier1-v3.md](results/tier1-v3.md).

## Against flat history and raw-history RAG

### What is measured: the page and the workspace, against flat

The usual alternative to a memory engine is RAG over the raw history: keep every turn, retrieve it with dense
embeddings and a reranker. [Bao et al. (2026)](https://arxiv.org/abs/2610.30755) find retrieval over raw history
ahead of LLM-transformed memory stores on these benchmarks. `flat` is raw-history retrieval with MindSlice's own
search: every round a card, no lineage. Against it, on the
same MEME questions (pooled, v3; MemoryAgentBench in the last column):

| | `flat` | `oracle` | Argon `agent-policy` | Argon `agent-overlay` | Qwen `agent-policy` | Qwen `agent-overlay` | MAB 32k: flat / Argon `agent-policy` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `stale-first` (stale card ranked first) | 0.327 | 0.006 | 0.000 | 0.006 | 0.026 | 0.070 | 0.795 / 0.000 |
| `stale@10` (unwarned stale card on the page) | 0.936 | 0.006 | 0.000 | 0.019 | 0.211 | 0.551 | |
| `current@10` (current fact on the page) | 0.968 | 0.968 | 1.000 | 1.000 | 1.000 | 0.994 | 0.970 / 0.970 |

These say what a reader would be handed, not what it would answer.

### Reader QA: the comparison reader so far (Qwen); the lines wait for Argon

Pre-registered and frozen in PLAN.md section 11 (`results/freeze_reader.json`). A reader gets the full top-10 cards
`search()` returns (dates and lineage notes included) and answers in a fixed JSON form, graded without an LLM;
answers the value rule rejects are judged by hand before anything is printed. The lines R1-R3 are read on Argon
after the weekly Gemini reset. The local Qwen has read `flat` and `oracle` as a comparison reader, with no line
([results/reader_qa_qwen.md](results/reader_qa_qwen.md)):

| 95 MEME episodes, 378 questions per set | `flat` | `oracle` | `oracle` − `flat` |
| --- | --- | --- | --- |
| Targets (Cascade, Absence, Deletion after the change) | 0.479 | 0.762 | **0.283 [0.222, 0.341]** |
| Controls (the same questions before it) | 0.966 | 0.974 | 0.008 [0.000, 0.018] |

The gain is in Absence (hop 1: 81/95 against 29/95) and Cascade hop 1 (76/95 against 44/95); Cascade hop 2 gains
less (32/63 against 24/63), and Deletion goes the other way (77/95 against 83/95): `flat` keeps the user's "please
forget" turn, which the reader honours, while `oracle` has deleted the topic and Qwen sometimes answers from an
unrelated card instead of saying it doesn't know. No dense raw-history RAG arm has been run (the local server offers
no embeddings).

### Reading cost and retrieval: what the comparison has to account for

- **Tokens.** The context totals below (Telemetry) price a benchmark replay's write side: a separate keeper agent
  re-reads each transcript in a fresh conversation and re-sends prompt, tool schemas and history at every step
  (a multiple of 37-76 per token of dialogue for Argon, 230-550 for Flash, on the smoke tier). Reading, which is
  what a working agent pays per question, is bounded by the engine. Measured on the saved final workspaces (exact
  MCP tool text, tokens estimated as characters ÷ 4, exploratory):

  | Memory | `search(k=10)`, median (p90) | `read()` of the top result, median (p90) |
  | --- | --- | --- |
  | Argon `agent-policy`, MEME (663 end-point questions) | 2,406 (3,489) | 561 (1,130) |
  | Argon `agent-overlay`, MEME | 2,070 (2,650) | 464 (1,207) |
  | Argon `agent-policy`, MemoryAgentBench 32k (66 questions; 2,309 cards, about 274k tokens) | 2,313 (2,683) | 294 (420) |
  | Full text of the top 10 raw rounds (`@history`, same MEME workspaces) | 2,536 (2,925) | |

  About 3k tokens per question whatever the memory's size, the same order as pasting the top 10 raw rounds.
  MindSlice doesn't read fewer tokens than raw retrieval; its page differs (the table above). It spends more on
  writing: 9-18 model tool calls per session in these runs, where raw-history RAG only embeds each turn.
- **Lexical, not dense.** `search()` is BM25 over SQLite FTS5. It is near complete when the question reuses the
  evidence's words (Recall@10 1.000 / 0.984 on LongMemEval single-session questions, 1.000 on MEME exact recall,
  0.976 on MemoryAgentBench in `evals/external`) and weak on implicit paraphrase (LoCoMo multi-hop and
  open-domain 0.298 / 0.296; "What do I do in my free time?" 0.395 when the evidence says "hobby"). That is the
  case dense retrievers and rerankers are built for, and where raw-history RAG should recall more; nothing here
  measures by how much.

## The architecture crossover: Argon and Qwen

Paired by unit, 95% intervals (v3):

| Comparison | `retired` | `forgotten` | `stale@10` |
| --- | --- | --- | --- |
| `agent-overlay` minus `agent-policy`, Argon | **+0.192 [0.146, 0.242]** | −0.033 [−0.098, 0.022] | +0.019 [0.000, 0.045] |
| `agent-overlay` minus `agent-policy`, Qwen | **−0.174 [−0.242, −0.107]** | **−0.293 [−0.435, −0.163]** | +0.340 [0.237, 0.442] |
| Qwen minus Argon (`agent-policy`) | −0.164 [−0.231, −0.103] | −0.370 [−0.467, −0.272] | +0.211 [0.147, 0.276] |
| Qwen minus Flash (`agent-policy`) | −0.110 [−0.171, −0.050] | −0.370 [−0.478, −0.272] | +0.199 [0.128, 0.269] |
| Argon minus Flash (`agent-policy`) | +0.053 [0.000, 0.107] | 0.000 [−0.033, 0.033] | |

- **Why it flips.** `agent-overlay` asks for one skill only, finding every raw round that states an old value
  and superseding it, and it never asks the agent to extract. Argon does that well: it retires more than the
  oracle (0.922 against 0.875, whose turn-level lineage misses later rounds that mention an old value in passing)
  and leaves no link-only failures. Qwen writes lineage often (829 `supersedes`, 1,214 `extends`) but misses many
  of those rounds. User turns such as "I live in Thornvale Crossing" or "this depends on the fact that I'm single"
  stay active and unwarned after the fact changes (`stale@10` 0.551).
- **The comparison is asymmetric in one way.** The Argon cells' v3 numbers are post-hoc (v3 was built from their
  audits); Qwen's were scored with the same frozen v3 after it was registered. Both crossover intervals are far
  from zero, and v3's `retired` judgments have 0-8% matching errors in every MEME cell.
- **What `agent-overlay` costs and can't do.** It takes more context (30M against 17M tokens over tier 1 on
  Argon; 11.9 against 9.2 tool calls per session; on Flash the smoke tier projected 367M tokens with the call cap
  hit in 20 of 46 MemoryAgentBench batches, so that cell never ran). Forgetting hides rounds but doesn't erase
  them: a superseded `@history` round stays on disk, reachable with `follow_supersedes=false`, until a human edits
  the slice. `supersedes` retires whole rounds, so a round's other facts survive only if the replacement restates
  them (`lost` 0.001-0.003). And something outside the agent has to append each transcript to the history slice.

**Reading.** Mounting raw history under an agent-written lineage overlay is the best configuration measured for
a strong model and the worst for a weak one. Which to ship depends on the model behind it.

## Error taxonomy

From the audits and hand-judged samples (v3). Each class is what a reader would be handed wrong, with where it
was measured and what, if anything, now answers it. "After scoring" changes are unmeasured.

| Class | Looks like | Where, how much | Answer |
| --- | --- | --- | --- |
| Link to a card named after an old value | "Related resource: [[subscriptions/xelvoria]]" | Argon `agent-policy`: 37 of 76 `retired` failures (49%); `agent-default` 34%, Flash 16%, `agent-overlay` 0. Without them, `agent-policy` 0.861 and `agent-default` 0.854 | After scoring: `write()` returns `affected_backlinks`; guidance names cards by slot (`team/lead`) |
| One card per value, old one left active | Flash `entertainment/whispers-of-zarinthea`; Qwen "team lead [[team/lead-sarah-chen]]" | Flash `retired` 0.676; Qwen `agent-policy` `stale@10` 0.211 (Argon 0.000) | Same as above |
| Raw round never superseded | "I live in Thornvale Crossing" stays active | Qwen `agent-overlay`: `retired` 0.392, `stale@10` 0.551 | None in the engine; model-dependent |
| Premise change in prose, not lineage | "Code Review Assignee: Subject to Change Under New Team Lead Jihoon Ryu" | MEME Absence: truly stale dependents on the page about 1-3% (Argon cells), 5% (Flash) | After scoring: `affected_extensions` and rebase guidance |
| Forgetting left incomplete | Dependents still stating the deleted value ("They still take the bus to work"); notes quoting the request with the value | Qwen `forgotten` 0.609 / 0.315 (sample of 12 `agent-policy` failures: 8 dependents or links, 4 own notes); Gemini 0.946-0.989 | After scoring: `affected_*` on delete; erasing a `@history` round needs a human |
| Entity conflation | A club membership merged into a "social meetup" card, then replaced by a potluck group | 34 real losses over the four Gemini cells, of 3,047 judged values per cell (10, 5, 8, 11) | None |
| Corrupted invented names | "Selvaria" for Xelvoria, "The Vondrehl Pot" for The Ondreth Pot | Most of Qwen `agent-policy`'s real losses | None |
| Tool plumbing | Stale `if_match` values; argument names outside the schema | Qwen `agent-policy`: 30 and 22 of 81 tool errors, plus 8 `KeyError`s; 135 and 98 of 475 sessions end without `DONE` | After scoring: a standard `invalid_arguments` error |
| Matching errors (the scorer's, not the agent's) | A value written in another format; a card that marks a change in its title but quotes the old statement in a body line | 22 of 25 unaudited Absence pages v3 still flags; one-word anchors on MemoryAgentBench | A card-level rule (v4), read on a fresh tier ([decision_ledger.md](decision_ledger.md)) |

What agents get right is as consistent: in a fixed sample of 40 first-ranked Cascade cards that state both old
and new values (exploratory), all 40 present the new value as current and the old one as history ("formerly", "switched
from") or as a search alias. Every dependent in Qwen's audited passes that still names an old premise is
`warned`.

## Limits

- **v3 is post-hoc for the Gemini tier-1 cells**, built from their audits; most of its label agreement is
  in-sample. The confirmatory run and Qwen tier 1 are its out-of-sample checks.
- **The audit is one-sided where it's cheapest.** Values both matchers keep, and pages both call clean, were not
  audited; the passes and flips samples (15 and 20 per cell) bound the miss rate only loosely.
- **MEME only** for tier 1, MemoryAgentBench for the confirmatory run; LongMemEval (tier 2) is not run.
- **One run per cell**, except the variance repeats; two Gemini models from one provider and one local model.
  The CLI adds its own framing around the system prompt and tool declarations, which isn't visible to us.
- **Answers so far from the comparison reader only**; the lines wait for Argon. No dense baseline (above).
- **Same author.** The runner, scorer, matchers, audits and this report were written by the agent that ran the
  test. The lines were kept at the specification's values, and the audit rule was applied as written.

## What next

1. **Make premise changes visible to retrieval.** Argon agents notice when a dependent's premise changes but
   write it in prose. *Partly done after scoring (unmeasured):* a supersede now returns the extensions to rebase,
   and the shipped `write` description says to rebase or retire each one in the same session.
2. **Prune links on supersede.** *Done after scoring (unmeasured):* a `write()` that supersedes or deletes a card
   returns `affected_backlinks` and `affected_extensions`, and the shipped `INSTRUCTIONS` ask the agent to update
   them in the same session and to name cards by durable slot. Measuring it needs a fresh tier and a new freeze
   (`INSTRUCTIONS` changed).
3. **A card-level status rule (v4), read on a fresh tier** (for example MEME `filler32k`), not on this one.
4. **Reader QA against flat**, drafted in PLAN.md section 11 (not frozen): Argon reads the saved workspaces after
   the weekly quota resets, on the 378 Cascade, Absence and Deletion questions after the change plus their 378
   before-change twins, graded without an LLM. A dry-run on the five smoke episodes (never scored) checked the
   harness and gave directions only: lineage pages beat flat on the targets and tie on the controls, and the three
   readers barely differ ([results/reader_dry_smoke.md](results/reader_dry_smoke.md)). A dense raw-history RAG arm
   needs an embedding model the local server doesn't offer.

## Telemetry

| Cell | Tool calls / session (max) | Writes: create / replace / append / delete | With `supersedes` / `extends` | Cap hits | Non-MCP calls run (denied) | Context tokens (uncached + cache read) |
| --- | --- | --- | --- | --- | --- | --- |
| Argon `agent-default` | 9.9 (30) | 1,863 / 419 / 79 / 93 | 251 / 662 | 0 | 0 (0) | 6.9M + 11.1M |
| Argon `agent-policy` | 9.2 (23) | 1,985 / 37 / 37 / 95 | 324 / 553 | 0 | 0 (0) | 6.7M + 10.2M |
| Argon `agent-overlay` | 11.9 (41) | 933 / 333 / 1 / 21 | 1,195 / 845 | 1 | 0 (1) | 8.9M + 20.8M |
| Flash `agent-policy` | 14.6 (34) | 2,000 / 46 / 29 / 97 | 306 / 613 | 0 | 0 (16) | 47.1M + 67.9M |
| Qwen `agent-policy` | 12.5 | – | – | 0 | 0 | 4.1M + 28.8M (local GPU) |
| Qwen `agent-overlay` | 14.0 | – | 829 / 1,214 | 0 | 0 | 6.1M + 41.2M (local GPU) |
| Argon `agent-policy`, MemoryAgentBench 32k | 18.4 (31) | 2,309 / – / – / – | 837 / – | 0 | 0 | 5.3M + 10.1M |

Every session ran as a fresh conversation in a new working directory. The four MindSlice tools were the only ones
that ran (the 17 other attempts in tier 1 were denied by the gate), and every traced tool call matched the MCP
proxy's log. Median session wall time was 84-105 s on Gemini (92 s on MemoryAgentBench).
