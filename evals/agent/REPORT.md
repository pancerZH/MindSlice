# Agent-in-the-loop lineage test: report

**Tier 1 is complete (2026-11-08).** Four cells (all three arms on `gemini-4-argon-medium`, `agent-policy`
on `gemini-3.8-flash-medium`) wrote memory for 95 MEME `nofiller` episodes each through the Antigravity CLI
over real MCP stdio: 1,900 sessions, plus 300 for three variance repeats of `agent-policy` on Argon. No
haystack failed. The frozen setup is [PLAN.md](PLAN.md); every table is in
[results/tier1.md](results/tier1.md), with a short version in [results/summary.md](results/summary.md).

## Verdicts

**By the pre-registered rule, every cell's lines are reported as unreliable** (agent_test.md 6.3; PLAN.md
section 6): in the audit, more than 20% of the `lost` cases were matching errors in every cell (60-100%),
and so were 35% of `agent-overlay`'s `retired` failures. The lines are shown below as descriptive numbers,
with the audit's corrections beside them, not as confirmed or missed claims.

| Line | Line value | Argon `agent-default` | Argon `agent-policy` | Argon `agent-overlay` | Flash `agent-policy` |
| --- | --- | --- | --- | --- | --- |
| G1 `stale-first` cut, flat minus agent | ≥ 0.30 | 0.321 [0.244, 0.397] | 0.327 [0.256, 0.404] | 0.321 [0.250, 0.397] | 0.321 [0.250, 0.397] |
| G2 `retired` | ≥ 0.70 | 0.833 [0.787, 0.876] | 0.857 [0.814, 0.895] | 0.934 [0.903, 0.961] | 0.756 [0.702, 0.806] |
| G2 audit-corrected | | 0.857 | 0.876 | 0.957 | 0.795 (from a sample) |
| G3 `current@10`, agent minus flat | ≥ −0.05 | +0.019 [−0.013, 0.051] | +0.032 [0.006, 0.063] | +0.032 [0.006, 0.063] | −0.013 [−0.057, 0.032] |
| G4 `lost` | ≤ 0.05 | 0.012 [0.008, 0.016] | 0.007 [0.004, 0.010] | 0.002 [0.000, 0.004] | 0.079 [0.069, 0.090] |
| G4 audit-corrected | | 0.001 | 0.001 | 0.001 | 0.000 (from a sample) |
| G5 `forgotten` | ≥ 0.90 | 1.000 [1.000, 1.000] | 0.987 [0.961, 1.000] | 0.961 [0.908, 1.000] | 0.987 [0.961, 1.000] |
| Raw verdicts (not read: unreliable) | | G1 point pass; G2-G5 confirmed | G1 point pass; G2-G5 confirmed | G1 point pass; G2-G5 confirmed | G1, G3 point pass; G2, G5 confirmed; G4 miss |

References on the same MEME episodes and scorer: `flat` `stale-first` 0.327, `retired` 0, `forgotten` 0;
`oracle` (the annotations' lineage) `stale-first` 0.006, `retired` 0.891, `lost` 0, `forgotten` 0.921.
The audit judged every `retired` failure and `lost` case of the three Argon cells (all populations were
under 50), so their corrected values are exact; Flash's are from the fixed 50-case samples.
**G1 can't be confirmed on MEME alone**: flat's `stale-first` is 0.327, so the largest possible cut is 0.327
and the oracle's own is 0.321 (a point pass too). The 0.30 line was set for a pooled tier with
MemoryAgentBench (flat 0.62 pooled in `evals/external`); dropping MemoryAgentBench left it barely reachable.
Every agent cell matches the oracle's cut.

## What the agents did

1. **They retire stale facts about as well as the annotations' lineage.** On MEME's Cascade questions an
   unwarned stale card ranks first on 0-0.6% of pages (flat 33%; oracle 0.6%) and is on the first page on
   about 2% (flat 94%). Over the whole workspace, `retired` is 0.76-0.93 (audit-corrected 0.80-0.96) against
   the oracle's 0.891, whose turn-level lineage misses later rounds that mention an old value in passing.
   `agent-overlay` retires the most (0.934; it wrote 1,195 cards with `supersedes`), above the oracle.
2. **Mostly by rewriting cards with the history kept.** On 64-91% of Argon's Cascade pages (21% for Flash)
   an unwarned card states both the old and the new value, which the value rule counts as not stale. A fixed
   sample of 40 first-ranked such cards (10 per cell, seed 20261106; an exploratory check made after the lines
   were produced) were all correctly updated: the new value as current, the old one as history ("formerly",
   "switched from") or as a search alias. None was a conditional card left unchanged after its condition
   fired.
3. **They rarely hide a true fact.** Raw `lost` is 0.002-0.079, but the audit found almost all of it to be
   matching errors: the agent restates MEME's annotation formats in its own words ("meal kit (kelvimeal)" as
   "Kelvimeal Meal Kit", "every thursday 2pm" as "Every Thursday at 2pm"), or keeps a verbatim error log with
   escaped line breaks. The real losses (10 of the 108 audited cases) are facts no active card holds: a
   superseding card that didn't restate a fact of the card it replaced (`agent-overlay`'s board-game card over
   the brunch round), a superseded planned purchase, a hobby never recorded.
4. **The current fact stays findable.** Pooled `current@10` is 0.96-1.00 (flat 0.968): Argon's cells are at or
   above flat, Flash 0.013 below.
5. **They forget on request.** `forgotten` is 0.96-1.00, above the oracle's 0.921 (Mode B keeps dependents
   that name the deleted value).
6. **The weak spot: dependents whose premise changed without a replacement.** On MEME's Absence questions
   (a dependent becomes "uncertain" when its root changes and no if-then rule replaces it), a stale
   dependent is on the first page, unwarned, in 83% of questions for Argon `agent-default`, 58% for
   `agent-policy` and 66% for `agent-overlay` (flat 100%; oracle 0%, which flags it through `extends`).
   Flash scores 10.5%, but part of that is its paraphrasing hiding the stale value from the matcher (not
   audited).

## The questions the matrix kept

Paired by unit, 95% intervals (results/tier1.md, "Paired comparisons"):

| Comparison | `retired` | `lost` | `current@10` | `forgotten` |
| --- | --- | --- | --- | --- |
| `agent-policy` minus `agent-default` (Argon) | +0.023 [−0.012, 0.058] | −0.005 [−0.009, −0.001] | +0.013 [0.000, 0.032] | −0.013 [−0.040, 0.000] |
| `agent-overlay` minus `agent-policy` (Argon) | **+0.077 [0.039, 0.120]** | −0.005 [−0.008, −0.002] | 0.000 | −0.026 [−0.079, 0.026] |
| Argon minus Flash (`agent-policy`) | **+0.101 [0.058, 0.147]** | −0.072 [−0.082, −0.063] | **+0.044 [0.019, 0.076]** | 0.000 [−0.040, 0.040] |

- **Prompt.** The policy paragraph adds little on top of the shipped tool descriptions: `retired` +0.023 (the
  interval includes 0), and Absence stale dependents go from 83% to 58%. The shipped `write` description and
  `INSTRUCTIONS` already carry most of the procedure.
- **Architecture.** Mounting the raw history read-only and having the agent write only lineage
  (`agent-overlay`) retires the most (+0.077 over `agent-policy`), at the cost of more context (30M tokens over
  the tier against 17M). Its remaining failures are mostly `@history` rounds it didn't supersede.
- **Model.** Argon beats Flash on `retired` (+0.101) and `current@10` (+0.044) while reading about a seventh of
  the context (17M against 115M tokens): Flash takes more steps (14.6 tool calls per session against 9.2) and
  thinks more. The `lost` difference is the matcher's (Flash paraphrases more), not harm.
- **Run-to-run variance** (`agent-policy` on Argon, 20 episodes, four runs): `retired` 0.870-0.907 (SD 0.018),
  `lost` 0.005-0.009, `stale-first` 0 in every run, `current@10` and `forgotten` 1 in every run. The two
  differences marked above are well outside this spread.

## Telemetry

| Cell | Tool calls / session (max) | Writes: create / replace / append / delete | With `supersedes` / `extends` | Cap hits | Non-MCP calls run (denied) | Context tokens (uncached + cache read) |
| --- | --- | --- | --- | --- | --- | --- |
| Argon `agent-default` | 9.9 (30) | 1,863 / 419 / 79 / 93 | 251 / 662 | 0 | 0 (0) | 6.9M + 11.1M |
| Argon `agent-policy` | 9.2 (23) | 1,985 / 37 / 37 / 95 | 324 / 553 | 0 | 0 (0) | 6.7M + 10.2M |
| Argon `agent-overlay` | 11.9 (41) | 933 / 333 / 1 / 21 | 1,195 / 845 | 1 | 0 (1) | 8.9M + 20.8M |
| Flash `agent-policy` | 14.6 (34) | 2,000 / 46 / 29 / 97 | 306 / 613 | 0 | 0 (16) | 47.1M + 67.9M |

Every session ran as a fresh `agy --print` conversation in a new working directory; the four MindSlice tools
were the only ones that ran (the 17 other attempts were denied by the gate), and every traced tool call matched
the MCP proxy's log. Median session wall time was 84-105 s. The quota gate paused new sessions three times
(five-hour bucket under 12%) for 6, 206 and 168 minutes; tier 1 and the repeats took 12.6 hours of wall clock
and about 65% of a weekly Gemini quota (81% to 16%, including the dropped MemoryAgentBench sessions).

## How the run got here (ledger in PLAN.md)

- **Before any LLM call** (Phase 1): value export in the compilers; a value-based scorer that reproduces
  `evals/external`'s card-level Mode B numbers exactly and agrees with them value by value within a few
  questions per group ([results/scorer_validation.md](results/scorer_validation.md)); Gate 1 passed on all of
  tier 1 ([results/gate1.md](results/gate1.md)).
- **Smoke tier** (three arms, two models; [results/smoke.md](results/smoke.md)): MCP tools declared eager (with
  the CLI's lazy dispatcher, Flash wrote the call as text), a pre-tool gate, and MemoryAgentBench batches cut
  from 50 to 10 facts (at 50 the 40-call cap bound 9 batches in 10).
- **Before any tier-1 call:** the matrix was cut to four cells on the smoke tier's cost and cap telemetry
  (Flash `agent-default` and Flash `agent-overlay` dropped: Flash `agent-overlay` alone would have taken 42%
  of the six-cell budget and hit the cap in 20 of 46 batches). Re-frozen.
- **During tier 1, before any tier-1 record was read:** quota readings showed Pro-priced Argon sessions cost
  about 0.03% of the week each, so MemoryAgentBench 32k (231 batches per cell) was dropped and Flash
  `agent-policy` ran before the variance repeats. Re-frozen; the 97 MemoryAgentBench sessions that had run are
  kept unscored.
- **Audit before the lines:** every verdict was recorded before results/tier1.md was generated. The audit
  judged each case on the workspace as it was at the judgment point, rebuilt by replaying the logged writes
  (checked to reproduce the final workspaces exactly), not on the final files.

## Limits

- **The value matcher is the bottleneck.** It reproduces card-level judgments on the harness's own cards (the
  scorer validation), but agents paraphrase: it overcounts `lost` badly and, through MEME's shared software
  vocabulary ("Synthari Modules" is not the framework Synthari), overcounts stale cards a little. A matcher
  that accepts the annotation formats' variants (a bracketed qualifier as optional, unit and date formats,
  verbatim text across line breaks) and checks entity context would make the lines readable; per the
  protocol, using it means a new tier or holdout, not re-reading this one.
- **MEME only.** The lines are claims about MEME's conversational updates; MemoryAgentBench's fact-list
  conflicts were dropped for quota, and LongMemEval is tier 2.
- **One run per cell** except the variance repeats; two models from one provider; the CLI adds its own framing
  around the system prompt and tool declarations, which isn't visible to us.
- **Same author.** The runner, scorer, audit and this report were written by the agent that ran the test; the
  lines were kept at the specification's values, and the audit rule was applied as written.

## What next

Per agent_test.md section 10, with the caveat that the lines are unreliable as measured: agents do write usable
lineage end to end (retirement at or above the oracle's, no measurable harm after the audit, current facts
findable, deletions honored). Two concrete follow-ups:

1. **Flag dependents when a premise changes.** Absence questions are where agents fail: they keep a dependent
   as current after its basis changed with no stated replacement. `extends` exists for exactly this; the
   `write` description could say so more directly (write dependents with `extends`; when a card you extend is
   superseded, re-check what extends it), tested on a new tier.
2. **A paraphrase-tolerant scorer, then a fresh tier** (for example MEME `filler32k` with MemoryAgentBench 64k),
   so G1-G5 can actually be read; MemoryAgentBench 32k could also run after the weekly reset as an addendum.
