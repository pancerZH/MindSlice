# Agent-in-the-loop lineage test: decision ledger

[REPORT.md](REPORT.md) gives the results. This file explains how the protocol got there: why the
pre-registered matcher's lines are not read, how matchers v2 and v3 were built and checked, and how cost and
quota re-shaped the frozen matrix. The binding, timestamped record is the ledger in [PLAN.md](PLAN.md)
(section 8); every decision below is in it, with what informed it. Nothing here changes a number in the report.

## 1. Before the lines

- **Before any LLM call** (Phase 1): value export in the compilers; a value-based scorer that reproduces
  `evals/external`'s card-level Mode B numbers exactly and agrees with them value by value within a few
  questions per group ([results/scorer_validation.md](results/scorer_validation.md)); Gate 1 passed on all of
  tier 1 ([results/gate1.md](results/gate1.md)).
- **Smoke tier** (three arms, two models; [results/smoke.md](results/smoke.md)):
  - MCP tools declared eager (with the CLI's lazy dispatcher, Flash wrote the call as text);
  - a pre-tool gate;
  - MemoryAgentBench batches cut from 50 to 10 facts (at 50, the 40-call cap bound 9 batches in 10).
- **Audit before the lines:** every verdict was recorded before results/tier1.md was generated. Each case was
  judged on the workspace as it was at the judgment point, rebuilt by replaying the logged writes.

## 2. Cost and quota re-freezes

The plan froze six cells (three arms on two Gemini models); tier 1 ran four. Every change below was made on
cost, cap and quota telemetry only, before any tier-1 record was read, and each one re-froze `results/freeze.json`
(PLAN.md sections 1 and 7, ledger).

- **Four cells, not six (before any tier-1 call).** On the smoke tier, Flash read 8-10 times Argon's context
  per session (23-30 serial tool turns against 9-15). Flash `agent-overlay` alone would have taken about 367M
  tokens, some 42% of the six-cell budget, while hitting the 40-call cap in 20 of 46 MemoryAgentBench batches,
  so a large part of its run would have measured the cap. The six cells needed about 93% of a week's Gemini
  quota by tokens (about 130% by sessions). The matrix kept what its two questions need: the progression
  `agent-default` -> `agent-policy` -> `agent-overlay` on Argon, and `agent-policy` on Flash for model scaling.
- **Flash before the variance repeats (tier 1, 03:50Z; the user's decision).** The first quota reading showed
  an Argon session costs about 0.027% of the week (Pro-priced tokens), so the matrix needed about 85% of the week
  with 75.5% left. The repeats were deferred, then run after the Flash cell. No rule changed.
- **MemoryAgentBench 32k dropped from tier 1 (03:53Z; the user's decision).** The remaining Argon chains (about
  600 batches, 17% of the week) and Flash's (231, 8%) left the plan short of quota (about 84% needed, 72% left)
  and set a 6.5-hour critical path. The three partial chains moved to `tier1-dropped/`, unscored; 43 finished
  MEME haystacks were kept. MemoryAgentBench 32k was later run on its own as the pre-registered confirmatory run (PLAN.md
  section 9).
- **The quota gate.** No session starts while the five-hour bucket is under 12% or the weekly one under 5%.
  In tier 1 it paused new sessions three times (five-hour bucket under 12%) for 6, 206 and 168 minutes.
  Tier 1 and the repeats took 12.6 hours of wall clock and about 65% of a weekly Gemini quota (81% to 16%,
  including the dropped MemoryAgentBench sessions).
- **The Qwen tier ran on a local GPU** (`qwen3.8-flash-next-iq3_s` on Strata, PLAN.md section 10): no quota, one
  session at a time, 7.1 h and 9.3 h for its two cells.

## 3. Matchers: frozen, v2, v3

### As pre-registered: unreliable

With the frozen matcher (`judge.py`), **every cell's lines are reported as unreliable** under the audit rule
(agent_test.md 6.3; PLAN.md section 6): more than 20% of the audited `lost` cases were matching errors in
every cell (60-100%), and so were 35% of `agent-overlay`'s `retired` failures. The frozen matcher asks whether
MEME's annotation string occurs verbatim in a card, and agents restate values in their own words. Those
numbers stay in [results/tier1.md](results/tier1.md) and are not read as verdicts.

### Re-scored with matcher v3 (post-hoc): readable in three cells of four

Two matchers were built after the audit, each from the error classes the audits before it found. Tier 1 was
re-scored offline from the logged writes (no model call).

- **v2** (`matcher2.py`):
  - a value is stated when its content words are, after light normalization (units, numbers, a bracketed type
    tag optional);
  - another entity's value that contains the old one is masked;
  - what a line marks as past ("previously", "switched from", "no longer") isn't presented as current;
  - search aliases aren't statements.
- **v3** (`matcher3.py`): v2, plus
  - times ("2:00 PM" = "2pm");
  - modal verbs as function words;
  - "-ies"/"-ly";
  - a true longest-common-subsequence for long verbatim values;
  - the past markers the audits found ("invalidates", "is subject to change", "depended on", "superseded by",
    "prior", "was removed"), scoped to their sentence.

Both are post-hoc for tier 1. v3 was checked on cases that no audit had judged and nobody used to build it.
Then it was frozen. Both were audited both ways: the 6.3 audit of what each flags (up to 50 `retired` failures
and 50 `lost` cases per cell), and samples of what each passes.

| Line | Line value | Argon `agent-default` | Argon `agent-policy` | Argon `agent-overlay` | Flash `agent-policy` | `oracle` |
| --- | --- | --- | --- | --- | --- | --- |
| G1 `stale-first` cut, flat minus agent | ≥ 0.30 | 0.327 [0.256, 0.404] point pass | 0.327 [0.256, 0.404] point pass | 0.321 [0.250, 0.397] point pass | 0.327 [0.256, 0.404] point pass | 0.321 |
| G2 `retired` | ≥ 0.70 | **0.779 [0.730, 0.826] confirmed** | 0.730 [0.676, 0.779] point pass | **0.922 [0.890, 0.950] confirmed** | 0.676 [0.619, 0.730] **miss** | 0.875 |
| G2 audit-corrected (both ways) | | 0.779 | 0.681 | 0.922 | 0.683 | |
| G3 `current@10`, agent minus flat | ≥ −0.05 | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | 0.000 |
| G4 `lost` | ≤ 0.05 | 0.004 [0.002, 0.007] confirmed | 0.002 [0.001, 0.004] confirmed | 0.003 [0.001, 0.005] confirmed | 0.004 [0.002, 0.007] confirmed | 0.001 |
| G4 audit-corrected | | 0.003 | 0.002 | 0.003 | 0.004 | |
| G5 `forgotten` | ≥ 0.90 | 0.989 [0.967, 1.000] confirmed | 0.978 [0.946, 1.000] confirmed | 0.946 [0.891, 0.989] point pass | 0.978 [0.946, 1.000] confirmed | 0.924 |
| Audit: `retired` / `lost` matching errors | ≤ 20% | 0/50 · 2/12 | 0/50 · **2/7** | 0/22 · 0/8 | 1/50 · 2/13 | |
| Audit: missed in 15 passes | | 0 | 1 | 0 | 0 | |
| By the 6.3 rule | | **reliable** | unreliable (`lost`) | **reliable** | **reliable** | |

`flat`: `stale-first` 0.327, `current@10` 0.968, `retired` 0, `forgotten` 0. Brackets are 95% bootstrap
intervals (2,000 replicates, seed 20261106), differences paired by unit. `lost` has 3,047 judged values. Every
flagged one was audited (populations 7-13), so its corrections are exact.

**How to read it.**

- **`retired` is measured reliably in every cell**: 0-2% matching errors among its failures and 0-1 missed
  stale card in 15 passes. Three cells pass the 6.3 rule outright, and their verdicts stand as confirmed or
  point passes.
- **Argon `agent-policy` fails the rule on `lost` by one value.** Its 2 errors are one value at two judgment
  points ("continuous deploy on merge", written "continuous deployment"). `lost` errors only go one way (a fact
  stated in a format the matcher doesn't normalize), so raw `lost` is an upper bound and G4 holds whatever the
  error share.
- **Argon `agent-policy`'s G2 is about at the line.** The point is 0.730, but one of its 15 sampled passes was a
  stale "Related: [[project/package-manager-veltrion]]" link the matcher misses. Corrected, that gives 0.681,
  from a single case (the miss share could be anywhere from about 0.2% to 32%).
- **Flash misses G2** (0.676, corrected 0.683). Its failures are real (1 matching error in 50): it often keeps
  one card per value (`entertainment/whispers-of-zarinthea`) and leaves the old one active, and its other cards
  keep linking to them in the present tense ("managed via [[tooling/dranith-stack]]").
- **G1 can't be confirmed on MEME alone**: flat's own `stale-first` is 0.327, so the largest possible cut is
  0.327, and the oracle's is 0.321. The 0.30 line was set for a pooled tier with MemoryAgentBench (flat 0.62
  pooled in `evals/external`). Every agent cell matches or beats the oracle's cut: a stale card ranks first on
  0-0.6% of Cascade pages (flat 33%).

**The matchers compared** (every hand verdict of every audit as ground truth: `python -m evals.agent.labels`):

| | Frozen | v2 | v3 |
| --- | --- | --- | --- |
| Stale-card cases (flagged and passed) | – | 288 / 291 | 289 / 291 |
| Fact cases (flagged lost and kept) | – | 150 / 179 | 173 / 179 |
| Page cases (Absence, and pages v3 cleared) | – | 11 / 87 | 59 / 87 |
| Cells reliable by the 6.3 rule | 0 / 4 | 2 / 4 | 3 / 4 |
| `flat` and `oracle` | card-level validated | pages as the frozen matcher | identical to v2 (0 of all units differ) |

Most of these labels are the audits v2 and v3 were built from. The fresh check:
- **Cleared pages:** 20 of 20 v3 cleared were right.
- **New flags:** the cases v3 newly flagged were wrong, from two causes:
  - First look: all 6 were wrong. Four came from the stop word "may" (a month) and the missing "prior" and "was
    removed", which were fixed.
  - Recorded sample: the other two came back, plus one right new loss. Both were the "from X to Y" resume rule,
    which was then removed (back to v2's behaviour).
- **After that**, v3 flags nothing that no audit has judged.

Details: [results/audit/tier1-v3/](results/audit/tier1-v3/) and the PLAN.md ledger.

**Why the numbers moved from the frozen matcher.** `retired` is lower under v2 and v3 in every cell (Argon
`agent-policy` 0.857 → 0.730). The frozen matcher had false passes, which its audit never sampled: it only saw
an old value written exactly as MEME annotates it, so "Thyrelion" in a card didn't count as
"thyrelion (anime)". The change is in MEME's `tracking` updates (23 more of them become matchable; retired on
them falls from 0.77-0.94 to 0.65-0.89), while root changes move by at most 0.06. `lost` falls from
0.002-0.079 (frozen) and 0.002-0.011 (v2) to 0.002-0.004 because paraphrases, times and verbatim texts now
count.

**What v3 still gets wrong.**

- Two value formats: "continuous deploy on merge" written as "continuous deployment", and "85% line coverage
  required" as "requires". Inflections other than "-ies"/"-ly" stay apart, because MEME's relationship statuses
  collide with ordinary words ("engaged" and an "engaging" book; "separated" and "separate" rooms).
- **Absence pages.** Many cards mark the change at card level ("Former Work Project: ...", "Changed After
  Moving ...", "Subject to Change") and then quote the user's earlier statement in a body line. v3 judges
  lines, so it counts them stale. Of the 25 Absence pages v3 still flags that no audit had judged (audited after
  its freeze), 22 are matching errors. A card-level rule (a title or summary that marks the value past governs
  the card) is the next fix. Per the protocol, it would be read on a fresh tier.
- Another entity's words (an auth middleware named like the token format; the same person in another role).

### What the matcher changes did to the findings

- **Prompt.** Under the frozen matcher, `agent-policy` minus `agent-default` on `retired` was +0.023; with v3 it is
  −0.050 [−0.100, 0.004]. The +0.023 came from the frozen matcher's false passes.
- **Model.** The `lost` gap between Argon and Flash (`agent-policy`) was −0.072 under the frozen matcher and
  −0.008 under v2; with v3 it is −0.002 (11 real losses against 5). It was mostly Flash's paraphrasing.
- **Absence pages.** Every matcher overcounts stale dependents there: on Argon, frozen 58-83%, v2 35-42%, v3
  6-23%. The 87 hand-judged pages show why: Argon agents write the change into the card in words ("Code Review
  Assignee: Subject to Change Under New Team Lead Jihoon Ryu"), which v3 still reads line by line. Truly stale
  dependents on the page, estimated from every v3 flag and the audits, are about 1-5% (REPORT.md, Error
  taxonomy).
- **Link-only failures** were measured by re-judging every failure's offending cards with `[[...]]` links
  removed, on v2's failures, which are v3's apart from one `agent-overlay` case (descriptive, not a line).

### Order of events

- **Re-score (post-hoc):** matcher v2 built from the audit's error classes. Five tier-1 verdicts were corrected
  where v2 disagreed and the worksheet had hidden the evidence. v2 was frozen and the confirmatory run
  pre-registered before its first call. Tier 1 was then re-scored offline and audited both ways, and the
  Absence pages were audited by sample (`results/audit/tier1-v2/`).
- **Matcher v3 (post-hoc):** built in new files, so v2's registered digest still holds, from the v2 and Absence
  audits. It was checked on `flat`/`oracle` and on fresh labels; the order of its changes is in the ledger.
  One tier-1 verdict was corrected because the same line had been judged both ways. v3 was frozen and
  registered as the confirmatory run's secondary scorer before any of that run's records was read, then
  audited on Absence pages after the freeze (`results/audit/tier1-v3/`).

## 4. Engine changes after every run was scored

Both are in the PLAN.md ledger with their replay checks. Neither changes a reported number.

- **`invalid_arguments`.** Qwen's tool errors included 22 argument names outside the schema (`address`,
  `body`, ...) answered with a raw `TypeError`, and 8 inputs that raised a `KeyError`. Tool calls are now checked
  against the input schema before they run. Of the 60,348 logged calls the engine had accepted, the check
  rejects none.
- **Impact reports and slot naming.** A `write()` that supersedes or deletes a card returns
  `affected_backlinks` / `affected_extensions`, and the shipped instructions ask agents to name cards by slot and
  update the listed cards in the same session (REPORT.md, What next). All 17,947 logged writes of the scored runs
  replay to the same outcomes and byte-identical overlays, and the 4,044 end-point search pages are identical.
  `INSTRUCTIONS` changed, so a new run needs a new freeze.
