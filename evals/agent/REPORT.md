# Agent-in-the-loop lineage test: report

**Tier 1 is complete (2026-11-08).** Four cells (all three arms on `gemini-4-argon-medium`, `agent-policy`
on `gemini-3.8-flash-medium`) wrote memory for 95 MEME `nofiller` episodes each through the Antigravity CLI
over real MCP stdio: 1,900 sessions, plus 300 for three variance repeats of `agent-policy` on Argon. No
haystack failed. The frozen setup is [PLAN.md](PLAN.md). Tables:
- [results/tier1.md](results/tier1.md): frozen matcher, as pre-registered;
- [results/tier1-v2.md](results/tier1-v2.md): matcher v2, post-hoc;
- [results/tier1-v3.md](results/tier1-v3.md): matcher v3, post-hoc.

There is a short version in [results/summary.md](results/summary.md).

**Confirmatory run: done** (PLAN.md section 9). `agent-policy` on Argon, MemoryAgentBench 32k (231 batches of 10
facts, 2026-11-08 16:11Z-23:57Z), scored with matcher v2 as registered and v3 as registered secondary, which
agree on every number. **G1-G4 confirmed:**

| Line | Line value | Agent | `flat` | Verdict |
| --- | --- | --- | --- | --- |
| G1 `stale-first` cut, flat minus agent (44 conflicts) | ≥ 0.30 | 0.795 [0.659, 0.909] | `stale-first` 0.795 (agent 0.000) | **confirmed** |
| G2 `retired` (44) | ≥ 0.70 | 0.909 [0.818, 0.977] | 0 | **confirmed** |
| G3 `current@10`, agent minus flat (66) | ≥ −0.05 | 0.000 [0.000, 0.000] | 0.970 (agent 0.970) | **confirmed** |
| G4 `lost` (63 values) | ≤ 0.05 | 0.000 [0.000, 0.000] | 0 | **confirmed** |

`oracle`: `stale-first` 0.000, `retired` 0.955.

By the audit rule as registered, this run's lines are still **reported as unreliable**:
- 3 of its 4 `retired` failures are matching errors. MemoryAgentBench's subject anchors can be one generic word ("capital", "state"), so other subjects' facts match: England's capital for the United Kingdom's, the US head of government for its head of state.
- The fourth failure is real: the General Motors card still lists Buick Regal among its products.

But the errors only count real passes as failures, and none of the 15 sampled passes missed a stale card. So the raw values are bounds, and all four verdicts hold: corrected `retired` is 0.977.

How the agent did it: one card per fact (2,309 creates), 837 of them with `supersedes`. 18.4 tool calls per
session (max 31), 0 cap hits, 0 non-MCP calls, 4 tool errors, `DONE` in every session. 92 s median per
session; 5.3M uncached + 10.1M cached tokens in, 0.6M out. Two sessions retried once after a provider error.
Tables: [results/confirm-mab32k-v2.md](results/confirm-mab32k-v2.md) (and `-v3`); audit:
`results/audit/confirm-mab32k-v2/`.

**Qwen tier 1** (PLAN.md section 10): `qwen3.8-flash-next-iq3_s` (3-bit IQ3_S) on a local Strata server,
through `strata.py`. `agent-policy` is done: 95/95 episodes, no failed haystack, 7.1 h, scored with matcher v3.
`agent-overlay` is running.

| Line | Line value | Qwen `agent-policy` | Argon `agent-policy` | Flash `agent-policy` |
| --- | --- | --- | --- | --- |
| G1 `stale-first` cut | ≥ 0.30 | 0.301 [0.224, 0.385] point pass | 0.327 point pass | 0.327 point pass |
| G2 `retired` | ≥ 0.70 | 0.566 [0.505, 0.623] **miss** (corrected 0.601) | 0.730 point pass | 0.676 miss |
| G3 `current@10` diff | ≥ −0.05 | +0.032 [0.006, 0.063] confirmed | +0.032 confirmed | +0.032 confirmed |
| G4 `lost` | ≤ 0.05 | 0.004 [0.002, 0.007] confirmed | 0.002 confirmed | 0.004 confirmed |
| G5 `forgotten` | ≥ 0.90 | 0.609 [0.511, 0.707] **miss** | 0.978 confirmed | 0.978 confirmed |
| Audit (6.3, v3): `retired` / `lost` matching errors | ≤ 20% | 4/50 · **4/13** (0 of 15 passes missed): unreliable by the rule (`lost`) | | |

Paired by unit, Qwen minus Argon: `retired` −0.164 [−0.231, −0.103], `forgotten` −0.370 [−0.467, −0.272], `stale@10`
+0.211 [0.147, 0.276]. Qwen minus Flash: `retired` −0.110 [−0.171, −0.050], `forgotten` −0.370 [−0.478, −0.272].

The `lost` errors only raise `lost`, so G4 holds, and G2 misses whatever the errors (corrected 0.601).

What the local model does differently:

1. **It doesn't forget everything it's asked to.** `forgotten` is 0.61, against 0.98 for both Gemini models. In a
   sample of 12 failures, 8 are other cards that keep stating the deleted value as current; they are dependents
   or links that weren't cleaned up ("They still take the bus to work"). The other 4 are its own notes about the
   conversation, which quote the request together with the value ("My relationship status is in a
   relationship. Please remove that from your memory.").
2. **It keeps one card per value and leaves old ones active**, more than Flash. Many failures are present-tense
   links to them: "secrets live in [[project/secret-manager-selvex]]", "team lead [[team/lead-sarah-chen]]".
   A stale card is on the first page of 21% of Cascade questions; on Argon it's 0%.
3. **It does warn dependents.** 952 of its writes use `extends`. Every dependent card in the audited passes that
   still names an old premise is `warned`.
4. **It corrupts invented names.** Most of its real losses are names copied wrong: "Selvaria" for Xelvoria, "The
   Vondrehl Pot" for The Ondreth Pot, "Vorentel SUV".
5. **Plumbing.** 12.5 tool calls per session, 0 cap hits, 0 non-MCP calls, and every call matched the proxy's log.
   135 of 475 sessions end with a summary instead of `DONE`. Of 81 tool errors, 30 are stale `if_match` values.
   Another 22 are argument names outside the schema (`address`, `body`, ...). The server answers those with a
   raw `TypeError`, not a validation error, even though the schemas say `additionalProperties: false`; 8 more
   inputs raise a `KeyError`. Those are engine robustness gaps, recorded and not changed. 4.1M uncached plus
   28.8M cached prompt tokens, 1.9M out; 47 s per session median, all on the local GPU.

Tables: [results/tier1-qwen-v3.md](results/tier1-qwen-v3.md); audit: `results/audit/tier1-qwen-v3/`.


## Verdicts

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

## What the agents did (matcher v3 and the audits)

1. **Stale facts get retired; the architecture matters most.** On MEME's Cascade questions a stale card
   ranks first on 0-0.6% of pages (flat 33%; oracle 0.6%). Over the whole workspace, `agent-overlay` retires
   the most (0.922, above the oracle's 0.875, whose turn-level lineage misses later rounds that mention an old
   value in passing), then `agent-default` 0.779, `agent-policy` 0.730, Flash 0.676.
2. **Half of `agent-policy`'s failures are links.** In 37 of its 76 failures (49%) the old value appears only in
   a link whose target card is named after it ("Related resource: [[subscriptions/xelvoria]]"). The share is
   34% for `agent-default`, 16% for Flash, and 0 for `agent-overlay`. Without the link-only failures,
   `agent-policy` (0.861) and `agent-default` (0.854) are level. The policy prompt's habit of cross-linking related
   cards leaves names of old values behind when the value changes. (Measured by re-judging every failure's
   offending cards with `[[...]]` links removed, on v2's failures, which are v3's apart from one
   `agent-overlay` case; descriptive, not a line.)
3. **Rewriting cards with the history kept.** A fixed sample of 40 first-ranked Cascade cards that state both
   the old and the new value (10 per cell, seed 20261106; judged by hand, exploratory) were all correctly
   updated: the new value as current, the old one as history ("formerly", "switched from") or as a search
   alias.
4. **They rarely lose a true fact.** Every case the matchers call lost was judged by hand. 34 are real, out of
   3,047 judged values per cell (`agent-default` 10, `agent-policy` 5, `agent-overlay` 8, Flash 11). The real
   losses are mostly entity conflation:
   - a club membership merged into a "social meetup" card and then replaced by a potluck group;
   - a hobby replaced by a sport;
   - a commute duration folded into the commute-method card and retired with it;
   - a fact superseded by something MEME never changed ("living with parents" over the condo);
   - a partner card deleted in the same session as the relationship status;
   - a goal kept only as past ("Prior to being married, the user had a financial goal of saving for a
     wedding");
   - a fact never recorded.
5. **The current fact stays findable.** Pooled `current@10` is 1.000 in every agent cell (flat 0.968).
6. **Premise changes without a replacement: flagged in prose, not in lineage.** On MEME's Absence questions, a
   dependent becomes uncertain when its root changes and no rule replaces it. Every matcher overcounts stale
   dependents here: on Argon, frozen 58-83%, v2 35-42%, v3 6-23%. The 87 hand-judged pages show why. The Argon
   agents notice the change and write it into the card ("Code Review Assignee: Subject to Change Under New Team
   Lead Jihoon Ryu", "no longer their current project"), but in words, not with `extends`. So the card isn't
   `warned` at retrieval, and a reader sees the flag only by reading the card.

   Truly stale dependents on the first page, estimated from every v3 flag and the audits: about 3%
   (`agent-default`), 1% (`agent-policy`), 2% (`agent-overlay`) and 5% (Flash). Flash's are plain present-tense
   cards left unchanged ("The user has a fixed 9-to-5 work schedule, which depends on their studies...").
   Argon's known ones are one episode in all three cells (`pl_041`: the agent asserts the exercise routine
   "remains yoga 2x/week" after its premise changed) and an old connection string listed as live
   infrastructure.
7. **They forget on request.** `forgotten` is 0.946-0.989, above the oracle's 0.924 (Mode B keeps dependents
   that name the deleted value).

## The questions the matrix kept (matcher v3)

Paired by unit, 95% intervals ([results/tier1-v3.md](results/tier1-v3.md), "Paired comparisons"):

| Comparison | `retired` | `lost` | `current@10` | `forgotten` |
| --- | --- | --- | --- | --- |
| `agent-policy` minus `agent-default` (Argon) | −0.050 [−0.100, 0.004] | −0.002 [−0.004, 0.000] | 0.000 | −0.011 [−0.033, 0.000] |
| `agent-overlay` minus `agent-policy` (Argon) | **+0.192 [0.146, 0.242]** | 0.000 [−0.002, 0.003] | 0.000 | −0.033 [−0.098, 0.022] |
| Argon minus Flash (`agent-policy`) | +0.053 [0.000, 0.107] | −0.002 [−0.004, −0.000] | 0.000 | 0.000 [−0.033, 0.033] |

- **Prompt.** The policy paragraph doesn't help on top of the shipped tool descriptions. If anything,
  `retired` is lower (−0.050, interval reaching +0.004), and the gap is the link-only failures of finding 2.
  The frozen matcher's +0.023 came from its false passes.
- **Architecture.** Mounting the raw history read-only and having the agent write only lineage
  (`agent-overlay`) retires clearly more (+0.192 over `agent-policy`), with no link-only failures, at the cost of
  more context (30M tokens over the tier against 17M).
- **Model.** Argon retires a little more than Flash (+0.053, interval touching 0) while reading about a seventh
  of the context (17M against 115M tokens): Flash takes more steps (14.6 tool calls per session against 9.2) and
  thinks more. The `lost` gap that the earlier matchers showed (−0.072 frozen, −0.008 v2) was mostly Flash's
  paraphrasing: with v3 it is −0.002 (11 real losses against 5). `current@10` ties at 1.000.
- **Run-to-run variance** (`agent-policy` on Argon, 20 episodes, four runs, v3): `retired` 0.733-0.800 (SD
  0.030), `lost` 0.002-0.003, `stale-first` 0, `current@10` and `forgotten` 1 in every run. The architecture
  difference is far outside this spread. The prompt and model differences are about the size of it.

## Telemetry

| Cell | Tool calls / session (max) | Writes: create / replace / append / delete | With `supersedes` / `extends` | Cap hits | Non-MCP calls run (denied) | Context tokens (uncached + cache read) |
| --- | --- | --- | --- | --- | --- | --- |
| Argon `agent-default` | 9.9 (30) | 1,863 / 419 / 79 / 93 | 251 / 662 | 0 | 0 (0) | 6.9M + 11.1M |
| Argon `agent-policy` | 9.2 (23) | 1,985 / 37 / 37 / 95 | 324 / 553 | 0 | 0 (0) | 6.7M + 10.2M |
| Argon `agent-overlay` | 11.9 (41) | 933 / 333 / 1 / 21 | 1,195 / 845 | 1 | 0 (1) | 8.9M + 20.8M |
| Flash `agent-policy` | 14.6 (34) | 2,000 / 46 / 29 / 97 | 306 / 613 | 0 | 0 (16) | 47.1M + 67.9M |

Every session ran as a fresh `agy --print` conversation in a new working directory. The four MindSlice tools
were the only ones that ran (the 17 other attempts were denied by the gate), and every traced tool call matched
the MCP proxy's log. Median session wall time was 84-105 s. The quota gate paused new sessions three times
(five-hour bucket under 12%) for 6, 206 and 168 minutes. Tier 1 and the repeats took 12.6 hours of wall clock
and about 65% of a weekly Gemini quota (81% to 16%, including the dropped MemoryAgentBench sessions).

## How the run got here (ledger in PLAN.md)

- **Before any LLM call** (Phase 1): value export in the compilers; a value-based scorer that reproduces
  `evals/external`'s card-level Mode B numbers exactly and agrees with them value by value within a few
  questions per group ([results/scorer_validation.md](results/scorer_validation.md)); Gate 1 passed on all of
  tier 1 ([results/gate1.md](results/gate1.md)).
- **Smoke tier** (three arms, two models; [results/smoke.md](results/smoke.md)):
  - MCP tools declared eager (with the CLI's lazy dispatcher, Flash wrote the call as text);
  - a pre-tool gate;
  - MemoryAgentBench batches cut from 50 to 10 facts (at 50, the 40-call cap bound 9 batches in 10).
- **Before any tier-1 call:** the matrix was cut to four cells on the smoke tier's cost and cap telemetry. Re-frozen.
- **During tier 1, before any tier-1 record was read:** MemoryAgentBench 32k was dropped for quota and Flash
  `agent-policy` ran before the variance repeats. Re-frozen.
- **Audit before the lines:** every verdict was recorded before results/tier1.md was generated. Each case was
  judged on the workspace as it was at the judgment point, rebuilt by replaying the logged writes.
- **Re-score (post-hoc):** matcher v2 built from the audit's error classes. Five tier-1 verdicts were corrected
  where v2 disagreed and the worksheet had hidden the evidence. v2 was frozen and the confirmatory run
  pre-registered before its first call. Tier 1 was then re-scored offline and audited both ways, and the
  Absence pages were audited by sample (`results/audit/tier1-v2/`).
- **Matcher v3 (post-hoc):** built in new files, so v2's registered digest still holds, from the v2 and Absence
  audits. It was checked on `flat`/`oracle` and on fresh labels; the order of its changes is in the ledger.
  One tier-1 verdict was corrected because the same line had been judged both ways. v3 was frozen and
  registered as the confirmatory run's secondary scorer before any of that run's records was read, then
  audited on Absence pages after the freeze (`results/audit/tier1-v3/`).

## Limits

- **v2 and v3 are post-hoc for tier 1.** They were built from tier 1's audits, so their tier-1 numbers are
  fitted, even though every flagged case was then judged by hand. Most label agreement is in-sample. The fresh
  check of v3 (23 cases, then 25 after the freeze) is small. The confirmatory run is the out-of-sample check for
  both.
- **The audit is one-sided where it's cheapest.** Values both matchers keep, and pages both call clean, were
  not audited. The passes and flips samples (15 and 20 per cell) bound the miss rate only loosely.
- **MEME only** for tier 1. The lines are claims about MEME's conversational updates. MemoryAgentBench's
  fact-list conflicts are the confirmatory run, and LongMemEval is tier 2.
- **One run per cell**, except the variance repeats; two models from one provider. The CLI adds its own
  framing around the system prompt and tool declarations, which isn't visible to us.
- **Same author.** The runner, scorer, matcher, audits and this report were written by the agent that ran the
  test. The lines were kept at the specification's values, and the audit rule was applied as written.

## What next

1. **Make premise changes visible to retrieval.** Argon agents already notice when a dependent's premise
   changes; they write it in prose. The `write` description could make that lineage instead: write dependents
   with `extends`, and when a card you extend is superseded, re-write what extends it. Then the card is `warned`,
   and a reader that doesn't open it is protected too.
2. **Prune links on supersede.** Link-only staleness is half of `agent-policy`'s failures. The server, or the
   instructions, could report the cards that link to a superseded card, so the agent can update them in the same
   session.
3. **A card-level status rule (v4), read on a fresh tier.** The Absence overcount left in v3 comes from cards
   whose title or summary says the value is former or changing, and which quote the old statement in a body
   line. Per the protocol, a new matcher is read on a tier it hasn't seen (for example MEME `filler32k`), not
   on this one.
