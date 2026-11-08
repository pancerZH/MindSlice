# Agent-in-the-loop lineage test: report

**Status (2026-11-08): built, validated, smoke tier run, plan re-frozen with a four-cell tier 1; tier 1
running.** All six cells would need about 93% of a weekly Gemini quota with 81% left, so before any tier-1
call the matrix was cut to the three arms on `gemini-4-argon-medium` and `agent-policy` on
`gemini-3.8-flash-medium`. **Flash `agent-default` and Flash `agent-overlay` are excluded**: Flash reads 8-10
times Argon's context per session, Flash `agent-overlay` alone would have taken about 42% of the six-cell
budget while hitting the call cap in 20 of 46 MemoryAgentBench batches, and the two kept questions (prompt
and architecture on the main model; model scaling under the policy) don't need them ([PLAN.md](PLAN.md),
section 7). The decision used cost and cap telemetry only. After the first 329 tier-1 sessions the quota
readings showed the four cells still wouldn't fit (Argon sessions cost about 0.028% of the week each), so
**MemoryAgentBench 32k was dropped from tier 1** before any tier-1 record was read: the lines are MEME's
(95 episodes, 1,136 questions). **No line (G1-G5) has been read yet**; nothing
below is a result of the test. The smoke tier is for plumbing and is never scored for lines (agent_test.md 5, 8.2).

## 1. The runner and the scorer, before any LLM call

- **Value export.** Every question of the compilers now carries normalized value strings (`stale`,
  `current`, `history`, `deleted`); MEME also exports its fact timeline, MemoryAgentBench each judged fact's
  subject anchors (`evals/external/datasets.py`; tests in `tests/test_external_eval.py`).
- **The runner reproduces `evals/external` exactly.** Scored card-level on the configuration of
  `external/results/summary.md`, `flat` and `oracle` re-ingested session by session match its Mode B table to
  the third decimal in every group ([results/scorer_validation.md](results/scorer_validation.md)).
- **Value-based vs card-level** on the same first pages agree within a few questions per group (tier 1,
  pooled: flat `stale-first` 0.430 vs 0.436, `stale@10` 0.940 vs 0.936; oracle 0.005 vs 0.000). Every
  disagreement falls in three classes: a paraphrased stale card ("pickup basketball *on* Saturdays"),
  stale and current values that are the same string, and mentions the annotations don't tie to the value
  (chatter rounds, "bike" in "road bike", a second subject sharing the anchor words).
- **The oracle's ceiling.** Judged over every active card, the annotations' own lineage reaches `retired`
  0.904 and `forgotten` 0.921 on tier 1, not 1: later rounds that mention an old value in passing ("…the
  compact size of your Therwyn Compact…") stay active and unwarned, and a deleted partner's name survives in
  a dependent card. G2 and G5 are read against these.
- **Gate 1 passed** on all of tier 1 (96 haystacks): `scripted-flat` vs `flat` and `scripted-oracle` vs
  `oracle` disagree on 0 of 865 questions, 302 updates, 2,866 current values and 76 deletions;
  `scripted-overlay` vs `oracle` on 12 unpooled `current@10` questions and nothing else
  ([results/gate1.md](results/gate1.md)). The same checks run in CI on synthetic data
  (`tests/test_agent_eval.py`, 203 tests in all).

## 2. The Antigravity CLI over real MCP stdio

Each session is a fresh `agy --print` conversation in a new working directory, with a custom agent whose
body is the arm's system prompt verbatim, the CLI's default prompt sections and built-in tools dropped, the
four MindSlice tools declared `eager` behind a logging, capped proxy around `python -m mindslice mcp`, and a
`PreToolUse` hook that denies anything else. Over the 466 smoke sessions that finished:

| Check | Result |
| --- | --- |
| Non-MCP tool calls that ran | 0 (7 attempts, all on Flash, none ran) |
| Traced MindSlice calls = proxy log, in order | 466 of 466 (7 calls the CLI itself rejected, such as a `search` without `query`, retried by the model) |
| Isolation | Asked, right after a scored session, what its context held from earlier conversations, a fresh conversation answered NONE (2.9k input tokens: prompt and tool schemas) |
| Failed haystacks, provider retries | 0, 0 |
| Sessions without DONE | Only those stopped at the call cap |

Plumbing found and fixed in the smoke tier (all in the ledger, PLAN.md section 8): MCP tools behind the
CLI's lazy `call_mcp_tool` made Flash write the call as text (fixed with eager tools); `list_resources` was
callable (fixed with the gate); **MemoryAgentBench's 50-fact batches can't fit the 40-call cap**: 9 of 10
batches hit it on Flash and 0.72-0.77 of the judged values went unwritten, so batches are now 10 facts.
No prompt wording and no line changed.

## 3. What the smoke tier showed (plumbing only, not results)

Five MEME episodes and one MemoryAgentBench context, so intervals are wide and nothing here is read against
a line ([results/smoke.md](results/smoke.md) has every table):

- **Every arm writes lineage.** Writes with `supersedes` / `extends`: Flash 177 / 16 (`agent-default`),
  179 / 20 (`agent-policy`), 132 / 23 (`agent-overlay`); Argon 23 / 22, 176 / 17, 216 / 36.
- **Different strategies.** On MemoryAgentBench, Flash and Argon `agent-policy` write about one card per
  fact (about 550 creates over the smoke tier, MEME included); Argon `agent-default` instead keeps a few topical cards and rewrites them each batch
  (157 `replace`, conflicts resolved in place: "…is Pius XII (updated from Ursula K. Le Guin)"), which the
  value rule counts as retired.
- **Flash `agent-overlay` runs out of calls.** It reads `@history` one card at a time and hit the 40-call cap
  in 20 of 46 MemoryAgentBench batches, the batches where its `retired` drops (0.597 on conflicts vs at least
  0.968 for every other arm and model). Argon `agent-overlay` never came near the cap (at most 22 calls).
- **Cost differs by an order of magnitude between models**: per MEME session Flash reads 194k-473k tokens of
  context, Argon 32k-65k (fewer steps, little thinking), at similar wall time (72-218 s).

## 4. What remains

1. Choose the tier-1 schedule (PLAN.md section 7): for example Argon's three arms and the variance repeats
   (about 10% of a week) and Flash `agent-default` and `agent-policy` (about 45%) now, Flash
   `agent-overlay` (about 40%) after the weekly reset; or the whole tier across the reset with a runner that
   waits out an exhausted quota instead of retrying into it (not built: the current retries give up after
   about 7.5 minutes and mark the haystack failed).
2. Run tier 1 (`python -m evals.agent agy --tier 1 --run tier1 ...`; it refuses to start if anything in
   `results/freeze.json` changed), then the variance repeats.
3. Audit (`python -m evals.agent audit --run tier1`, then verdicts in `results/audit/`), then read G1-G5 and
   write this report's results.
