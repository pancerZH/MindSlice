# Agent-in-the-loop lineage test: report

**Tier 1 is complete (2026-11-08).** Four cells (all three arms on `gemini-4-argon-medium`, `agent-policy`
on `gemini-3.8-flash-medium`) wrote memory for 95 MEME `nofiller` episodes each through the Antigravity CLI
over real MCP stdio: 1,900 sessions, plus 300 for three variance repeats of `agent-policy` on Argon. No
haystack failed. The frozen setup is [PLAN.md](PLAN.md). Tables: [results/tier1.md](results/tier1.md) (frozen
matcher, as pre-registered) and [results/tier1-v2.md](results/tier1-v2.md) (matcher v2, post-hoc); short
version in [results/summary.md](results/summary.md).

**Status of the confirmatory run** (PLAN.md section 9: `agent-policy` on Argon, MemoryAgentBench 32k, matcher
v2 frozen beforehand): running; its result will be added here.

## Verdicts

### As pre-registered: unreliable

With the frozen matcher (`judge.py`), **every cell's lines are reported as unreliable** under the audit rule
(agent_test.md 6.3; PLAN.md section 6): more than 20% of the audited `lost` cases were matching errors in
every cell (60-100%), and so were 35% of `agent-overlay`'s `retired` failures. The frozen matcher asks whether
MEME's annotation string occurs verbatim in a card, and agents restate values in their own words. Those
numbers stay in [results/tier1.md](results/tier1.md) and are not read as verdicts.

### Re-scored with matcher v2 (post-hoc): readable for `retired` in every cell

Matcher v2 (`matcher2.py`) was built from the audit's error classes: a value is stated when its content words
are, after light normalization (units, numbers, a bracketed type tag optional); another entity's value that
contains the old one is masked; what a line marks as past ("previously", "switched from", "no longer", ...)
isn't presented as current; search aliases aren't statements. It was validated on `flat` and `oracle` against
card-level judgments, frozen (digest in PLAN.md section 9), and tier 1 was re-scored offline from the logged
writes (no model call). Because v2 was fitted to tier 1's audit, this is post-hoc. It was then **audited both
ways**: the 6.3 audit of what it flags (up to 50 `retired` failures and 50 `lost` cases per cell), and the
other way, 15 updates it counts as retired per cell and 20 values the frozen matcher called lost that v2 keeps
(Flash; on Argon every such value had already been judged by hand).

| Line | Line value | Argon `agent-default` | Argon `agent-policy` | Argon `agent-overlay` | Flash `agent-policy` | `oracle` |
| --- | --- | --- | --- | --- | --- | --- |
| G1 `stale-first` cut, flat minus agent | ≥ 0.30 | 0.327 [0.256, 0.404] point pass | 0.327 [0.256, 0.404] point pass | 0.321 [0.250, 0.397] point pass | 0.327 [0.256, 0.404] point pass | 0.321 |
| G2 `retired` | ≥ 0.70 | **0.779 [0.730, 0.826] confirmed** | 0.730 [0.676, 0.779] point pass | **0.918 [0.886, 0.950] confirmed** | 0.676 [0.619, 0.730] **miss** | 0.875 |
| G2 audit-corrected (both ways) | | 0.779 | 0.681 | 0.918 | 0.683 | |
| G3 `current@10`, agent minus flat | ≥ −0.05 | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | +0.032 [0.006, 0.063] confirmed | 0.000 |
| G4 `lost` | ≤ 0.05 | 0.004 [0.002, 0.007] confirmed | 0.003 [0.001, 0.005] confirmed | 0.002 [0.001, 0.004] confirmed | 0.011 [0.007, 0.014] confirmed | 0.001 |
| G4 audit-corrected | | 0.003 | 0.002 | 0.002 | 0.004 | |
| G5 `forgotten` | ≥ 0.90 | 0.989 [0.967, 1.000] confirmed | 0.978 [0.946, 1.000] confirmed | 0.946 [0.891, 0.989] point pass | 0.978 [0.946, 1.000] confirmed | 0.924 |
| Audit: `retired` / `lost` matching errors | ≤ 20% | 0/50 · 2/12 | 0/50 · **4/9** | 0/23 · 0/7 | 1/50 · **22/33** | |
| Audit: missed in passes / wrong in flips | | 0/15 · – | 1/15 · – | 0/15 · – | 0/15 · 0/20 | |
| By the 6.3 rule | | **reliable** | unreliable (`lost`) | **reliable** | unreliable (`lost`) | |

`flat`: `stale-first` 0.327, `current@10` 0.968, `retired` 0, `forgotten` 0. Brackets are 95% bootstrap
intervals (2,000 replicates, seed 20261106), differences paired by unit. `lost` has 3,047 judged values, all
flagged ones were audited (populations 7-33), so its corrections are exact.

**How to read it.**

- **`retired` is now measured reliably in every cell**: 0-2% matching errors among its failures and 0-1
  missed stale card in 15 passes. Argon `agent-default` and `agent-overlay` pass the 6.3 rule outright, and
  their G2-G5 verdicts stand as confirmed or point passes.
- **Two cells fail the rule on `lost` alone.** These errors only go one way: v2 calls a fact lost when an
  active card states it in a format v2 doesn't normalize. So raw `lost` is an upper bound, and it is under 0.05
  in every cell. G4 holds whatever the error share; the other lines don't use `lost`. Strictly by the rule,
  those two cells' lines are still reported unreliable.
- **Argon `agent-policy`'s G2 is a point pass that the correction pushes under the line** (0.681): one of its 15
  sampled passes was a stale "Related: [[project/package-manager-veltrion]]" link that v2 misses. That
  correction rests on a single case (one of 15, so the miss share could be anywhere from about 0.2% to 32%).
  The honest reading is "about at the line".
- **Flash misses G2** (0.676, corrected 0.683): its failures are real (1 matching error in 50). It often keeps
  one card per value (`entertainment/whispers-of-zarinthea`) and leaves the old one active, and its other cards
  keep linking to them in the present tense ("managed via [[tooling/dranith-stack]]").
- **G1 can't be confirmed on MEME alone**: flat's own `stale-first` is 0.327, so the largest possible cut is
  0.327, and the oracle's is 0.321. The 0.30 line was set for a pooled tier with MemoryAgentBench (flat 0.62
  pooled in `evals/external`). Every agent cell matches or beats the oracle's cut: a stale card ranks first on
  0-0.6% of Cascade pages (flat 33%).

**Why the numbers moved from the frozen matcher.** `retired` is lower under v2 in every cell (Argon
`agent-policy` 0.857 → 0.730). The frozen matcher had false passes, which its audit never sampled: it only saw
an old value written exactly as MEME annotates it, so "Thyrelion" in a card didn't count as
"thyrelion (anime)". The change is in MEME's `tracking` updates (v2 makes 23 more of them matchable; retired on
them falls from 0.77-0.94 to 0.65-0.89), while root changes move by at most 0.06. `lost` falls from 0.002-0.079 to
0.002-0.011 because paraphrases now count.

**What v2 still gets wrong** (left as frozen; all of it found by the audits above):

- Time and wording formats: "11:00 PM to 5:30 AM" for `11pm-5:30am`, "every Thursday at 2:00 PM", "allows any
  team member to approve" (the value says "can approve"), "requires 85% line coverage", "releases continuously on
  merge".
- **Long values.** For MEME's verbatim texts (life philosophies, error logs), v2's in-order coverage is computed
  over the whole card. When a card's summary quotes an abridged version first, the greedy alignment anchors on
  it: a card quoting the full text word for word scores 0.61, while the quoting line alone scores 1.00. The
  same alignment fails on logs split into "Line 1:/Line 2:" bullets (0.72).
- Past markers it doesn't know: "affected by", "invalidates", "is subject to change now that", "depended on",
  past tense ("was about 20 minutes"), and "(superseded by ...)" written after the value. These matter most on
  Absence pages (finding 6 below).

None of these classes touches MemoryAgentBench, the confirmatory run's haystack: its values are short and
judged on lines with their subject anchors, where the long-value rule doesn't apply.

## What the agents did (matcher v2 and its audits)

1. **Stale facts get retired; the architecture matters most.** On MEME's Cascade questions a stale card
   ranks first on 0-0.6% of pages (flat 33%; oracle 0.6%). Over the whole workspace, `agent-overlay` retires
   the most (0.918, above the oracle's 0.875, whose turn-level lineage misses later rounds that mention an old
   value in passing), then `agent-default` 0.779, `agent-policy` 0.730, Flash 0.676.
2. **Half of `agent-policy`'s failures are links.** In 37 of its 76 failures (49%) the old value appears only in
   a link whose target card is named after it ("Related resource: [[subscriptions/xelvoria]]"). The share is
   34% for `agent-default`, 16% for Flash, and 0 for `agent-overlay`. Without the link-only failures,
   `agent-policy` (0.861) and `agent-default` (0.854) are level. The policy prompt's habit of cross-linking related
   cards leaves names of old values behind when the value changes. (Measured by re-judging every failure's
   offending cards with `[[...]]` links removed; descriptive, not a line.)
3. **Rewriting cards with the history kept.** A fixed sample of 40 first-ranked Cascade cards that state both
   the old and the new value (10 per cell, seed 20261106; judged by hand, exploratory) were all correctly
   updated: the new value as current, the old one as history ("formerly", "switched from") or as a search
   alias.
4. **They rarely lose a true fact.** Every case v2 calls lost was judged by hand. 33 are real, out of 3,047
   judged values per cell (`agent-default` 10, `agent-policy` 5, `agent-overlay` 7, Flash 11). The real
   losses are mostly entity conflation:
   - a club membership merged into a "social meetup" card and then replaced by a potluck group;
   - a hobby replaced by a sport;
   - a commute duration folded into the commute-method card and retired with it;
   - a fact superseded by something MEME never changed ("living with parents" over the condo);
   - a partner card deleted in the same session as the relationship status;
   - a fact never recorded.
5. **The current fact stays findable.** Pooled `current@10` is 1.000 in every agent cell (flat 0.968).
6. **Premise changes without a replacement: flagged in prose, not in lineage.** On MEME's Absence questions
   (a dependent becomes uncertain when its root changes and no rule replaces it), v2 still sees a stale
   dependent, unwarned, on the first page of 35-42% of Argon's questions (frozen matcher 58-83%; Flash 10.5%,
   flat 100%, oracle 0%). A post-hoc audit of 10 such questions per cell (seed 20261106; worksheets in
   `results/audit/tier1-v2/absence/`) found nearly all of Argon's to be matching errors: 9, 10 and 10 of 10.
   The card says the dependent is "subject to change now that Sarah Chen is the new team lead", "has changed
   (new duration not yet specified)", or "invalidates the ... Docker image". Flash's were 5 of 10: its genuine
   ones are plain present-tense cards ("The user has a fixed 9-to-5 work schedule, which depends on their
   studies...") left unchanged after the premise changed. So Argon does notice. But it records the
   uncertainty in words rather than with `extends`, so the card isn't `warned` at retrieval: a reader sees the
   flag only by reading the card. From the samples, about 4% (`agent-default`), about 0 (`agent-policy`,
   `agent-overlay`) and about 5% (Flash) of Absence questions have a truly stale dependent on the first page.
   These are rough estimates, from 10 cases each.
7. **They forget on request.** `forgotten` is 0.946-0.989, above the oracle's 0.924 (Mode B keeps dependents
   that name the deleted value).

## The questions the matrix kept (matcher v2)

Paired by unit, 95% intervals ([results/tier1-v2.md](results/tier1-v2.md), "Paired comparisons"):

| Comparison | `retired` | `lost` | `current@10` | `forgotten` |
| --- | --- | --- | --- | --- |
| `agent-policy` minus `agent-default` (Argon) | −0.050 [−0.100, 0.004] | −0.001 [−0.003, 0.001] | 0.000 | −0.011 [−0.033, 0.000] |
| `agent-overlay` minus `agent-policy` (Argon) | **+0.189 [0.139, 0.238]** | −0.001 [−0.003, 0.002] | 0.000 | −0.033 [−0.098, 0.022] |
| Argon minus Flash (`agent-policy`) | +0.053 [0.000, 0.107] | **−0.008 [−0.011, −0.004]** | 0.000 | 0.000 [−0.033, 0.033] |

- **Prompt.** The policy paragraph doesn't help on top of the shipped tool descriptions. If anything,
  `retired` is lower (−0.050, interval reaching +0.004), and the gap is the link-only failures of finding 2.
  The frozen matcher's +0.023 came from its false passes.
- **Architecture.** Mounting the raw history read-only and having the agent write only lineage
  (`agent-overlay`) retires clearly more (+0.189 over `agent-policy`), with no link-only failures, at the cost of
  more context (30M tokens over the tier against 17M).
- **Model.** Argon retires a little more than Flash (+0.053, interval touching 0) and loses fewer facts (−0.008;
  11 real losses against 5, the rest is v2's format misses on Flash's paraphrases). It does this while reading
  about a seventh of the context (17M against 115M tokens): Flash takes more steps (14.6 tool calls per
  session against 9.2) and thinks more. `current@10` ties at 1.000.
- **Run-to-run variance** (`agent-policy` on Argon, 20 episodes, four runs, v2): `retired` 0.733-0.800 (SD
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

## Limits

- **v2 is post-hoc for tier 1.** It was built from tier 1's audit, so its tier-1 numbers are fitted, even if
  every flagged case was then re-judged. Agreement with the 255 hand labels it was built from (254) is
  in-sample. The confirmatory run is the out-of-sample check.
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
3. **Matcher v3, only with a fresh tier.** Per-line coverage for long values; time, inflection and modal
   normalization; the past markers found on Absence pages. Per the protocol, a new matcher is read on a tier it
   hasn't seen (for example MEME `filler32k`), not on this one.
