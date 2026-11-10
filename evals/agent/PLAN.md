# Agent-in-the-loop lineage test: frozen plan

Frozen on 2026-11-07, **before the first tier-1 call**, after the runner and scorer were validated offline
(section 7 of [`../agent_test.md`](../agent_test.md)) and the smoke tier ran; **re-frozen on 2026-11-08,
still before any tier-1 call**, with tier 1 reduced to four cells (section 1, ledger). Everything here can be checked
mechanically: `python -m evals.agent freeze --check` compares the current code, prompts, CLI version and
haystack lists with [`results/freeze.json`](results/freeze.json), and a tier-1 run refuses to start if any
of them changed. The specification is `agent_test.md`; where this plan decides something the specification
leaves open, it says so.

**Frozen digests** (SHA-256; `freeze.json` has the rest):

| What | Value |
| --- | --- |
| Engine `mindslice/*.py` at `f0ba04a` (clean) | `fcc7ed17449a5aa770ad5d133278be55fa67b415ec2c49eaefd60c0a8edfd5a5` |
| Scorer: `evals/agent/{judge,plan,score,sessions}.py` + `evals/external/datasets.py` | `432973dc71d3b1f221d67c9affe657e2fb322cc58523cfb4b165c47b75a69d1c` |
| Runner: every file that runs or scores a session (`run.RUNNER_FILES` + `evals/external/{datasets,corpus,harness}.py`) | `e1567df5a8969bd21c7dfa292aed0b6f813b2f68f648b1d345e29725939a0b61` (re-freeze; was `1beb8014…` at the first freeze) |
| `agy --version` | `1.5.3` |
| Audit sample seed | `20261106` |

## 1. What runs

| | |
| --- | --- |
| Engine | `mindslice/` at commit `f0ba04a` (engine digest in `freeze.json`); unchanged from the smoke tier to the end of tier 1 |
| Agent arms | `agent-default` (4.2), `agent-policy` (4.2 + 4.3), `agent-overlay` (4.2 + 4.3 + 4.4) |
| **Tier-1 matrix** | **`agent-default`, `agent-policy` and `agent-overlay` on `gemini-4-argon-medium`; `agent-policy` on `gemini-3.8-flash-medium`**. Left out of tier 1: `agent-default` and `agent-overlay` on Flash (section 7). The smoke tier ran all six |
| Reference arms | `flat` (Mode A) and `oracle` (Mode B), re-scored with the same value-based scorer; offline |
| Models | `gemini-3.8-flash-medium` (Gemini 3.8 Flash, Medium) and `gemini-4-argon-medium` (Gemini 4 Argon, Medium), exact ids from `agy models` |
| Main model | `gemini-4-argon-medium` (the more capable one): it runs the variance repeats (8.4) |
| Client | Antigravity CLI `agy` 1.5.3, one fresh `agy --print` conversation per session (never `--continue` / `--conversation`) |
| Flags | `--model <id> --effort medium --agent mindslice-memory-keeper --output-format stream-json --dangerously-skip-permissions --disable-slash-commands`; the session message is passed as `--print=<message>` |
| Model parameters | The provider's defaults (temperature, max output tokens); effort `medium` (the model ids also name it). Nothing else is set |
| Tools | Real MCP over stdio (4.1, first bullet): `evals.agent.mcp_proxy`, a logging wrapper around `python -m mindslice -w <workspace> mcp`, writes straight to `@overlay` (no `--stage-writes`) |
| Call cap | 40 tool calls per session; the 41st is refused by the proxy and the CLI is stopped (the session ends; counted) |
| Session timeout | 1,800 s; a provider failure or timeout is retried on the same session after restoring `overlay/` (up to 3 retries, backoff 30 / 120 / 300 s); then the haystack is marked failed and stays in every denominator as failed |

### How the CLI is confined to the four tools

Each session runs in a new, empty working directory outside the repository holding only:

- `.agents/agents/mindslice-memory-keeper.md`: a custom main agent. Its body is the arm's system prompt,
  verbatim (section 2); its frontmatter is `mainAgent: true`, `subagent: false`,
  `excludeDefaultComponents: true`. The last drops the CLI's default prompt sections and its built-in tools
  (files, shell, browser, web).
- `.agents/plugins/mindslice-eval/mcp_config.json`: the MCP server (the proxy above) with its four tools
  declared `eager`, so the model gets `manifest`, `search`, `read` and `write` as functions with the shipped
  schemas and descriptions (named `mcp_mindslice-eval_mindslice_<tool>`), not through the CLI's lazy
  `call_mcp_tool` dispatcher (with it, Flash wrote the call as text and the turn failed: smoke ledger).
- `.agents/hooks.json`: a `PreToolUse` hook (`evals.agent.tool_gate`) that denies any call that isn't an
  MCP tool. Three framework tools remain declared after `excludeDefaultComponents` (`list_resources`,
  `read_resource`, `manage_task`; none touches files); the hook keeps them from running.

Checked per session from the `stream-json` trace: **non-MCP tool calls that ran** (must be 0), denied
attempts (reported), and that the traced MindSlice calls equal the proxy's `tools/call` log in order.
Before the smoke tier a fresh conversation was asked whether its context held anything from earlier
conversations (summaries, knowledge items, memories) right after a scored session: it answered `NONE`, with
2.9k input tokens (the system prompt and the tool schemas).

What the specification asks that this client can't give exactly: the CLI may add its own framing around the
system prompt and the tool declarations (not visible to us), and the MCP server's `instructions` reach the
model only through the system prompt, as 4.2 prescribes.

## 2. Prompts (verbatim from agent_test.md; SHA-256 of the UTF-8 text)

The system prompt of an arm is its parts joined by a blank line (`"\n\n"`). `INSTRUCTIONS` is
`mindslice/mcp_server.py`'s string.

| Part | SHA-256 |
| --- | --- |
| `INSTRUCTIONS` | `6d15c0ab673648d90bc1ce741e94a29e4cae79b641e05904c12d33e40fe3a542` |
| Task prompt (4.2) | `6139ec46c73c2612c2d79b585fa12cce8e7a552bff4267ab2e90707d522a7244` |
| Policy paragraph (4.3) | `57b4e310927d408330b23fb0701ff31e4c2296a4c9cdf964a8c32c0f9f509957` |
| Overlay addendum (4.4) | `cbde5dacde870f7d0d8f1d0b3a2337aeb46c0ce14198336e0c6baf791b5a014f` |
| System prompt, `agent-default` = INSTRUCTIONS + task | `4f2d6962e4725639d9da5224124ba2b11beb3c0435af2ac30058d784d13c320b` |
| System prompt, `agent-policy` = + policy | `a62dedfb304bc951928cec366a69c3805965efa6034eba59bf5c09e4e9e47177` |
| System prompt, `agent-overlay` = + policy + addendum | `5eb8cc0563acd799fcec912a9317863785bec5d15ce232b4988fd08ec9af6300` |

**Task prompt (4.2):**

> You are the long-term memory keeper for one user. You will be shown their conversations with an
> assistant, one session at a time, in the order they happened. Use the MindSlice tools to record what is
> worth remembering about the user for future conversations, and keep that memory accurate and up to date.
> You will not be asked questions about it. When you have finished with this session, reply with DONE.

**Policy paragraph (4.3):**

> Before you write, search for cards about the same thing. If the new information replaces something
> already recorded (a changed value, a new preference, a correction), write the new card with
> `supersedes` naming the old card's address, rather than leaving both active or deleting the old one,
> and restate anything in the old card that is still true. If it refines, adds an exception or an
> if-then rule to, or depends on something that stays true (a choice made because of an earlier
> preference or plan), write it with `extends` naming that card, so it is flagged if that card later
> changes. If you can't tell which, use `extends`: it hides nothing. If the user asks you to forget
> something, delete the cards that state it. Put each fact that can change on its own card, and keep its
> concrete values, names, dates, conditions and the user's own wording; the summary states the fact.

**Overlay addendum (4.4):**

> Every session is already stored verbatim in the read-only `@history` slice. Don't copy it: write to
> `@overlay` only to keep that history accurate. When a value changes, write a card with the new value
> that `supersedes` every card stating the old one, in `@history` or `@overlay`. When something depends
> on or adds a rule to an earlier fact, write a card restating it that `extends` the card holding that
> fact and `supersedes` the `@history` card it came from. When the user asks you to forget something,
> write a card that `supersedes` each `@history` card stating it and restates the rest of that card
> (you can still delete your own `@overlay` cards). In every replacement, restate any other fact from
> the old card that is still true.

**Session message (4.2):** `Session {i} of {n}, {date}:`, a blank line, the transcript (`Session {i} of {n}:`
when the dataset has no date, as MemoryAgentBench). The transcript is the turn lines of the round cards
(`Speaker: text`, continuation lines indented, `[[` as `[ [`); a MemoryAgentBench batch is
`Facts {a}-{b} of {N}, in the order they were stated:` and then the facts, one per line, without numbers.
`tests/test_agent_eval.py` checks every quoted text against agent_test.md.

**MemoryAgentBench batches hold 10 facts, not 50** (a change from 4.2, made in the smoke tier, which may
change transcript formatting and the call cap, 8.2). At 50, the batch can't fit the 40-call cap: 9 of 10
batches hit it for `agent-default` and `agent-policy` on Flash, which then wrote 114 and 156 of the 455
facts' cards and lost 0.77 and 0.72 of the judged current values; the metric measured the cap. The policy's
own procedure (search, read the old card, write) takes about 3 calls per fact, so 10 facts fit 40 calls. At
10, Argon never hit the cap (at most 27 calls in a batch) and neither did Flash's `agent-default` (at most
40); Flash's `agent-policy` hit it in 4 of 46 batches and Flash's `agent-overlay` in 20 of 46, where it
reads `@history` one card at a time. Those are the agent's own call budget, the case the cap exists for,
not the batch size: the cap stays at 40, and cap hits are reported per arm.

## 3. Data and tiers

Same files, compilers and question positions as `evals/external` (MEME's before-change questions right
after their session; everything else after the last session).

| Tier | Haystacks | Sessions | Reading volume |
| --- | --- | --- | --- |
| Smoke (never scored for lines) | MEME `nofiller` `pl_001`-`pl_005`; MemoryAgentBench `factconsolidation_sh_6k` | 25 + 46 batches | 0.027M tokens (chars / 4) |
| 1 | MEME `nofiller`, the other 95 episodes (below); MemoryAgentBench `factconsolidation_sh_32k` | 475 + 231 batches | 0.42M tokens |

Tier-1 MEME episodes: pl_006 to pl_050 (45) and sw_001 to sw_050 (50); the full list is in `freeze.json`.

**MemoryAgentBench 32k was dropped from tier 1** (ledger, 2026-11-08 03:53Z) after the run's first 329
sessions and before any tier-1 record was read: its 231-batch chains needed about a quarter of the week's
quota and set the critical path. Tier 1 is therefore the 95 MEME episodes (1,136 questions); every line
G1-G5 is computed on MEME alone, and its claims are MEME's. The 97 MemoryAgentBench sessions that ran are
kept, unread and unscored, in `tier1-dropped/` of the runs directory.

**Variance repeats (8.4).** `agent-policy` with the main model, 3 more times, on 20 MEME episodes drawn once
from the tier-1 list with `random.Random(20261106).sample` (sorted keys): pl_006, pl_007, pl_009, pl_012,
pl_017, pl_020, pl_023, pl_027, pl_033, pl_036, pl_040, pl_041, pl_045, pl_047, pl_049, sw_007, sw_030,
sw_035, sw_039, sw_041. Reported as the spread of each pooled metric over the four runs (tier 1 plus three
repeats), beside the lines.

## 4. Scoring (frozen code: `judge.py`, `plan.py`, `score.py`, `sessions.py`, `evals/external/datasets.py`)

Definitions are agent_test.md 6.1-6.2; the decisions below are this plan's, made on `flat` and `oracle`
only, before any LLM run ([`results/scorer_validation.md`](results/scorer_validation.md) has the evidence):

- **States.** The normalized value (NFKC, quotes straightened, casefolded, whitespace collapsed, surrounding
  punctuation stripped) occurs in the card's normalized title, aliases, summary or body, not continuing a
  longer word. **MemoryAgentBench:** only on a line that also holds every subject anchor word of the judged
  fact (its prefix words found in at most 1% of the context's facts, never the values' own words).
- **Matchable values.** A value counts only if its own flat card states it; the rest are excluded from that
  metric and counted. A question needs a matchable stale value for `stale@10`, and a matchable current value
  as well for `stale-first`.
- **Questions per metric.** `stale-first`: MEME Cascade (1- and 2-hop) and MemoryAgentBench conflicts.
  `stale@10`: the same (MEME Absence and Deletion reported as groups). `current@10`: MEME Cascade and every
  judged MemoryAgentBench question (share of the question's current values on the page). `retired`: every
  matchable update (MEME value changes: Tracking steps, root changes, others; MemoryAgentBench conflicts),
  right after its session, over every active card. `lost`: every matchable current value at every question
  point (MEME: before-change point and end; dependents and rules reported separately). `forgotten`: every
  MEME deletion with a matchable value, right after its session. `history-named@10`: MEME Tracking.
- **Intervals.** 95% percentile bootstrap over units, 2,000 replicates, seed 20261106; differences between
  arms paired by unit (question, update, value or deletion).
- **Reference ceilings** (tier 1, the same scorer): `oracle` scores `retired` 0.904 and `forgotten` 0.921,
  not 1: its turn-level lineage leaves later rounds that mention an old value active (scorer_validation.md,
  section 2). G2 and G5 are read against those.

## 5. Lines (final values, unchanged from agent_test.md 8)

Pooled over tier 1, for each of the four cells. Also reported, with no line, the paired differences that
answer the two questions the matrix keeps: `agent-policy` minus `agent-default` and `agent-overlay` minus
`agent-policy` on Argon (prompt and architecture), and Argon minus Flash under `agent-policy` (model), on
every pooled metric, paired by unit.

| Line | Claim | Statistic | Line |
| --- | --- | --- | --- |
| G1 | The agent's lineage cuts stale-first substantially | `stale-first`, flat minus agent, paired | ≥ 0.30 |
| G2 | The agent retires most stale facts | `retired` | ≥ 0.70 |
| G3 | Its memory keeps the current fact findable | `current@10`, agent minus flat, paired | ≥ −0.05 |
| G4 | It rarely hides a true fact | `lost`, all current values | ≤ 0.05 |
| G5 | It forgets on request | `forgotten` | ≥ 0.90 |

Verdicts as in `evals/external/PLAN.md`: **confirmed** (the 95% interval clears the line: its low end for
G1-G3 and G5, its high end for G4), **point pass** (only the mean does), **miss**. The lines were kept at the
specification's suggestions; the smoke tier's numbers were not used to set them.

## 6. Audit (6.3), before reading the lines

Per agent arm and model, a fixed random sample (`random.Random(20261106)`, records sorted by haystack, id and
point) of up to 50 `retired` failures and 50 `lost` cases, judged by opening the saved workspace files
(`python -m evals.agent audit`; worksheets in `results/audit/`). If more than 20% of either sample is a
matching error, that arm's lines are reported as unreliable instead of read.

## 7. Cost of tier 1 (measured on the smoke tier, 8.2) and how it is run

Per session, from the complete smoke tier (`python -m evals.agent project`; [`results/projection.json`](results/projection.json)).
"Context" is what the model read: uncached input plus cache reads, which the CLI reports separately.

| Arm, model | MEME session: wall, context | MAB batch (10 facts): wall, context | Tier 1 session-hours | Tier 1 context |
| --- | --- | --- | --- | --- |
| `agent-default`, Flash | 87 s, 194k | 96 s, 466k | 17.6 h | 200M |
| `agent-policy`, Flash | 90 s, 220k | 96 s, 467k | 18.1 h | 212M |
| `agent-overlay`, Flash | 218 s, 473k | 120 s, 617k | 36.5 h | 367M |
| `agent-default`, Argon | 86 s, 33k | 98 s, 47k | 17.6 h | 26M |
| `agent-policy`, Argon | 72 s, 32k | 107 s, 49k | 16.4 h | 26M |
| `agent-overlay`, Argon | 117 s, 65k | 80 s, 41k | 20.5 h | 40M |

Tier 1 is 475 MEME sessions and 231 MemoryAgentBench batches per cell. For all six cells that would be
127 session-hours and about 870M context tokens; the token multiple (context per token of dialogue read)
is 37-76 for Argon and 230-550 for Flash on MEME (Flash takes more steps and thinks more, and every step
re-sends the conversation).

**Quota.** The CLI's Gemini quota is a weekly and a five-hour fraction, "consumed proportionally to the cost
of the tokens" (Flash and Pro-class models share it). The smoke tier and its diagnostics (about 480 sessions,
about 130M context tokens) took the weekly bucket from 96% to 81% and the five-hour one from 94% to 34%. Six
cells would need about 93% of a week by tokens (about 130% by sessions), more than was left.

**The four-cell matrix (re-frozen before any tier-1 call).** Flash costs 8-10 times Argon's context per
session (23-30 serial tool turns against 9-15), and Flash `agent-overlay` alone would take 367M tokens (about
42% of the six-cell budget) while hitting the 40-call cap in 20 of 46 MemoryAgentBench batches, so a large
part of its run would measure the cap. The matrix keeps what the two questions need: the progression
`agent-default` -> `agent-policy` -> `agent-overlay` on the main model (about 93M tokens), and model scaling
under the standard policy (`agent-policy` on Flash, about 212M). It drops Flash `agent-default` and Flash
`agent-overlay`. The decision used the smoke tier's cost and cap telemetry only; no line, and no smoke metric
of those two cells, entered it. Expected: about 305M tokens, about a third of a week, roughly 1.5 five-hour
windows at the smoke tier's rate (Argon's tokens cost more than Flash's, so this is approximate).

**Schedule** (`python -m evals.agent tier1`, from `freeze.json`): the three Argon cells (their 231-batch
MemoryAgentBench chains first, the longest, then the MEME haystacks round-robin across arms), the three
variance repeats, then `agent-policy` on Flash; 12 haystacks at a time, a free worker taking the next item.
Session-hours: about 55 (Argon), 6 (repeats), 18 (Flash); the Flash MemoryAgentBench chain (about 6 h) starts
when the Argon items have all started, so the tier takes roughly 11 hours plus quota pauses.

**Quota gate.** No session starts while the Gemini five-hour bucket is under 12% or the weekly one under 5%
(`agy -p /usage`, which calls no model, re-read every minute). Every worker then waits for that bucket's
reset; sessions already running finish (12% leaves room for them: the smoke tier used about 0.1-0.5% of a
five-hour window per session). A session that fails while quota is low, or with a quota or rate-limit error,
is restored and run again after the wait without using one of its three retries (up to 12 such waits).
Pauses are logged (`tier1/quota.jsonl`) and reported. A stopped run resumes where it was: finished
haystacks are kept, an unfinished one starts over.

## 8. Ledger

| When | What | Informed by |
| --- | --- | --- |
| Phase 1 | Value export, scorer, runner, scripted agents; Gate 1 passed on all of tier 1 (0 disagreements for `scripted-flat` and `scripted-oracle`; `scripted-overlay` differs from `oracle` only on 12 unpooled `current@10` questions) | flat / oracle / scripted only |
| Phase 1 | Whole-word matching; MemoryAgentBench subject anchors (and their exclusion of value words); matchable values | flat / oracle disagreements with card-level |
| Smoke, before any scored session | Diagnostics on an empty workspace: with the CLI's lazy `call_mcp_tool`, Flash wrote the call as text and the turn failed ("malformed function call"); the four tools were then declared `eager` and the model listed exactly them plus `list_resources`, `read_resource`, `manage_task`. Isolation check (NONE) | plumbing |
| Smoke | A Flash `agent-overlay` session called `list_resources`: added the `PreToolUse` gate. In the smoke tier, 7 non-MCP attempts (all Flash: `list_resources` denied by the gate, and one misspelt tool name), none of which ran | plumbing |
| Smoke | MemoryAgentBench batch-50 runs hit the cap (section 2); batches set to 10 facts; the cap stays 40; Gate 1 re-run with 10-fact batches: unchanged. The remaining two batch-50 runs (Argon `agent-policy`, `agent-overlay`) were stopped to save quota; batch 10 was then run for every arm and model | plumbing (cap and transcript formatting, 8.2) |
| Smoke | The trace-vs-proxy check counted calls the CLI rejected before the server (missing `query`, a misspelt tool name: 7 calls) and one call still running when the CLI was stopped at the cap as mismatches; corrected (`agy.trace_check`), re-applied to every smoke session (`retrace`): 466 sessions, 0 mismatches | plumbing |
| Smoke | Token telemetry counts cache reads (Argon's per-step `input_tokens` excludes them); value records carry the entity (for the audit) | plumbing |
| Smoke | No prompt wording changed. No line changed | |
| Freeze | This plan and `results/freeze.json` committed before any tier-1 call; tier 1 paused for scheduling (section 7) | |
| Re-freeze, 2026-11-08 | Tier 1 reduced to four cells (section 7); `tier1` schedule and quota gate added (the runner code changed, so its digest); paired comparisons and the variance table added to the report. Lines, prompts, scorer and tiers unchanged | the smoke tier's cost and cap telemetry |
| Tier 1, 2026-11-08 03:50Z | **Order changed (user's decision): `agent-policy` on Flash runs before the variance repeats.** After 30 minutes the first quota reading showed Argon sessions cost about 0.027% of the week each (Pro-priced tokens: about as much as an average smoke session, not a tenth), so the matrix needs about 85% of the week with 75.5% left and 3-4 five-hour windows, not the 1.5 projected above from tokens. The repeats (about 8% of the week) were marked deferred in the running schedule, so no started work was lost, and run after the Flash cell. No rule changed | the quota gate's readings |
| Tier 1, 2026-11-08 03:53Z | **MemoryAgentBench 32k dropped from tier 1 (user's decision); re-frozen** (`tier1_dropped` in `freeze.json`; the tier definition and every rule unchanged). Reason: the remaining Argon chains (about 600 batches, about 17% of the week) and Flash's (231, about 8%) left the plan short of quota (about 84% needed, 72% left) and set a 6.5-hour critical path. Decided on logs and quota readings only: no tier-1 record had been read. The runner was stopped (12 partial haystacks, 9 of them MEME, restart from scratch); 43 finished MEME haystacks kept; the three partial MemoryAgentBench chains (97 sessions) moved to `tier1-dropped/`, unscored. Order from here: Argon cells, Flash `agent-policy`, variance repeats (the deferral markers removed) | the quota gate's readings |
| Tier 1 done, 2026-11-08 15:38Z | All four cells 95/95, the repeats 60/60, no failed haystack; three quota pauses (6, 206, 168 min) | |
| Audit, 2026-11-08 | Judged before results/tier1.md was generated. Two changes to the audit tooling, made during the audit and before any line was read: evidence is the workspace as it was at the judgment point (rebuilt by replaying the logged writes, which reproduces every final workspace checked), and inactive cards are marked. Verdict rules: a line presenting the old value as current is a correct `retired` judgment; one that marks it as past, or another entity's value that merely contains it, is a matching error; a `lost` value stated in other words by an active card is a matching error. Every cell has more than 20% matching errors in `lost`: lines reported unreliable | the worksheets |
| After the lines | Exploratory, not a line: a fixed sample of 40 first-ranked Cascade cards stating both the old and the new value, all correctly updated (REPORT.md) | |
| Re-score, 2026-11-08 | Matcher v2 built from the audit's error classes and validated (section 9). Five audit verdicts corrected when v2 disagreed with them: the worksheet showed only 3 lines per card (4 `retired` failures were real: a hidden line names the old value) and one `lost` case was judged without seeing that its card was inactive. Tier 1 re-scored with v2: post-hoc, reported apart | the tier-1 audit |
| Confirmatory run pre-registered | Section 9, before its first call | |
| Confirmatory run started, 2026-11-08 16:11Z | 231 batches, quota gate on | |
| v2 audit of tier 1, 2026-11-08 (post-hoc; v2 unchanged) | Both ways (`audit2.py`): 6.3 on v2's flagged cases (verdicts of the tier-1 audit kept for cases it had judged), plus 15 v2 passes per cell and 20 values the frozen matcher called lost that v2 keeps (Flash; on Argon all had been hand-judged). Verdict rules as in the tier-1 audit; a link or line that presents the old value as current (including "Related: [[card named after it]]") is a real failure. `retired`: 0-2% matching errors in every cell; `lost`: 17%, 44%, 0%, 67% (Argon default, policy, overlay; Flash), so Argon `agent-policy` and Flash stay unreliable by the rule. The report adds a two-way correction (`audit2.corrected`), not a line | the v2 worksheets |
| After the v2 lines | Exploratory, not lines: Absence pages audited by sample (10 per cell, seed 20261106; `results/audit/tier1-v2/absence/`), and `retired` failures split into link-only and prose by re-judging offenders with `[[...]]` links removed (REPORT.md) | |
| Matcher v3, 2026-11-08 (post-hoc for tier 1) | Built in new files (`matcher3.py`, `rescore3.py`; v2 and `rescore.py` untouched, digests checked) from the error classes of the v2 and Absence audits: time formats, modal verbs, "-ies"/"-ly", LCS coverage for long values, more past markers (sentence-scoped). Changes made while checking, in order: the stemmer was cut back to "-ies"/"-ly" after `oracle` showed collisions ("engaged"/"engaging"), and "have changed" was scoped to its sentence after `flat` showed a user's turn losing a fact; a first look at the cases v3 newly flagged (no audit had judged them) found all 6 wrong: 4 from "may" as a stop word (a month), and "prior" and "was removed" missing, which were fixed; the other 2 came back in the recorded sample. Then the recorded fresh sample, drawn again: every case v3 newly flagged and 20 of the pages it cleared (seed 20261106; `results/audit/tier1-v3/fresh/`): the cleared pages right (20/20), 2 of the 3 new flags wrong (the third, a new loss, right), both from one rule ("from X to Y" resumes as current), which was then removed (back to v2's behaviour). After that, v3 newly flags nothing no audit has judged, and is identical to v2 on `flat` and `oracle` (0 differing units). One tier-1 audit verdict corrected: the same line had been judged both ways (overlay `pl_043/update/4#1`, now a matching error, as the Absence audit had it) | the v2, Absence and fresh audits |
| v3 frozen, 2026-11-08 17:10Z | `results/freeze_v3.json`; registered as a secondary scoring of the confirmatory run (section 9a) before any of its records was read | |
| v3 audit, after its freeze (v3 unchanged) | Two-way 6.3 worksheets for v3 (`results/audit/tier1-v3/`), verdicts from the hand labels (`labels.py`); the populations are v2's but for one case each in `agent-overlay`, whose 5 new passes were judged (all correct). `retired` 0-2%, `lost` 17%, 29%, 0%, 15% matching errors: Argon `agent-policy` stays unreliable by the rule (one value at two points). Absence pages v3 still flags, unjudged: 25 audited (10 per cell, or all), 22 matching errors (cards that mark the change in their title or summary and quote the earlier statement in a body line) | the v3 worksheets |
| Strata smoke, 2026-11-08 18:25-19:15Z | `qwen3.8-flash-next-iq3_s` on the local Strata server through `strata.py` (OpenAI chat completions, real MCP stdio through `mcp_proxy.py`), MEME `pl_001`-`pl_005`, `--jobs 1`. `agent-policy`: 25 sessions, 0 failed, 11.6 calls per session (max 18), 0 cap hits, 0 non-MCP calls, every traced call = the proxy's log, 4 tool errors (an `if_match` on an absent card; 3 `write` calls with argument names the schema doesn't have, `related_note` and `address`, which the server answers with a `TypeError` although the schema says `additionalProperties: false`, an engine gap, not changed), 4 sessions ending with a summary instead of `DONE`; median 44 s per session, 3.8 min per episode. `agent-overlay`: 25 sessions, 0 failed, 13.6 calls (max 28), 0 cap hits, 1 tool error (a `read` of an absent card), 7 without `DONE`; median 54 s, 5.3 min per episode. No setting changed after the smoke tier | plumbing |
| Qwen tier 1 pre-registered | Section 10, `results/freeze_qwen.json`, before its first tier-1 call | |
| Confirmatory run done, 2026-11-08 23:57Z | 231/231 sessions, no failed haystack (two sessions retried once after a provider error). Re-scored with v2 (registered) and v3 (secondary): identical. Audit first (recorded and committed before the lines were generated): 4 `retired` failures, 3 matching errors (one-word anchors match another subject's fact), no `lost` case, 15 passes correct. G1-G4 confirmed; by the rule, reported unreliable (the errors only lower `retired`; corrected 0.977) | |
| Qwen `agent-policy` done, 2026-11-09 02:24Z | 95/95, no failed haystack, 7.1 h. Re-scored with v3 (and v2). Audit first (committed before the lines): `retired` 4/50 matching errors, `lost` 4/13, passes 0/15: unreliable by the rule (`lost`). G2 and G5 miss; `forgotten` failures checked by sample (exploratory): real. The report command gains `--add-arm` (the Gemini cells beside it) and the three section-10 comparisons | the v3 worksheet |
| Qwen tier 1 done, 2026-11-09 11:43Z | `agent-overlay` 95/95, no failed haystack, 9.3 h; the engine unchanged throughout. Audit first (committed before the lines): `retired` 1/50 matching errors, `lost` 0/3, 2 of 15 passes missed: reliable. G1, G2 and G5 miss; G3 and G4 confirmed | the v3 worksheet |
| Engine change, after every run was scored (user's request) | `mindslice/`: tool calls are checked against the tool's input schema for argument names before they run; a missing required argument or one the schema doesn't have gets a standard `InvalidArgumentsError` (code `invalid_arguments`) naming each, the allowed names and a hint (`write` takes the address as `id`), instead of a raw `TypeError`/`KeyError`; a `TypeError`, `KeyError` or `ValueError` from below the check comes back in the same shape. Values are not checked. Replay-safe: of the 60,348 logged calls the engine had accepted, in every run, the check rejects none (all 62 that had failed with a `TypeError`/`KeyError` now get `invalid_arguments`), so re-scoring and audit replays reproduce every run. The frozen engine digests in the freeze files are those of the runs | the Qwen smoke and tier-1 tool errors |
| Engine and guidance change, after every run was scored (user's request) | `mindslice/`: a `write()` that supersedes or deletes a card returns `affected_backlinks` / `affected_extensions` (the cards that still `[[link]]` to it or extend it, read from the index under the same `LOCK_EX`; nothing else is edited); the server's `INSTRUCTIONS` and `write` description ask the agent to name cards by durable slot (`team/lead`, not `team/lead-sarah-chen`) and to update or rebase the listed cards in the same session. Also: plain Markdown and legacy `---` YAML frontmatter are indexed without conversion (a new parser version re-indexes caches), any existing file name is addressable while new ids stay as strict as before, a mount alias falls back to the directory name, and `mount()` retires the `@overlay` copies of a packed slice. Replay-safe: every logged `write` of tier 1, the variance repeats, Qwen tier 1 and the confirmatory run (631 haystacks, 17,947 calls, 17,814 accepted) replayed through the engine before and after gives the same per-call outcome (error, `changed`, `sha256`) and byte-identical final `overlay/` trees, and the 4,044 end-point search pages on the saved workspaces are identical, so re-scoring and audit replays reproduce every run. `INSTRUCTIONS` changed, so the prompt digests in section 2 and the freeze files no longer match: they stay those of the runs, and any new run needs a new freeze. Exploratory, not a line: the reading cost per question on the saved workspaces (REPORT.md, "Against flat history and raw-history RAG") | REPORT.md "What next" 1-2 (link-only failures, prose premises) |
| Reader QA drafted, 2026-11-09 (section 11, not frozen) | Timing probe on the smoke episode `pl_001` only (never scored): 6 after-change questions of `flat` and `oracle` sent to the local Qwen with a draft prompt, plus determinism repeats; answers not graded. Found: 5-38 s per call, mostly reasoning; temperature 0 not deterministic on this server. No scored episode has been sent to a reader | the user's decision: Qwen-only reader for now, Argon if Qwen behaves badly |
| Reader QA dry-run, 2026-11-09 (section 11.6; smoke episodes only, never scored) | Harness `reader.py` built and tested; every rebuilt page equals the recorded one (256/256). Argon and Flash read all 8 cells (256 calls each), Qwen `flat` and `oracle` (64); then page version draft-2 (lineage targets quoted) on `flat` and `oracle` for all three. 1.25% of the weekly quota (the user allowed 5%). Directions only: `oracle` minus `flat` +0.06 to +0.25 on targets, 0.000 on controls; the readers agree on 248/256. The user had decided to wait for the weekly reset and read with Argon; Qwen measured at 9.2 s a call (17 h for a full run, not 58 h) | the dry-run |

## 9. Confirmatory run: MemoryAgentBench 32k with matcher v2 (pre-registered 2026-11-08, before its first call)

Tier 1's lines were unreliable under the audit rule: the frozen matcher (`judge.py`) counts an agent's own
wording as a lost fact (REPORT.md). Matcher v2 (`matcher2.py`) was then built from the audit's error classes,
validated on `flat` and `oracle` (MEME and MemoryAgentBench, against card-level judgments) and on the 255
hand-judged tier-1 cases (254 agree, in-sample), and **frozen** here
(`results/freeze_confirm.json`, digest `228d623eeeb7898b8ab128add51a092a475652591838e328af8b8091c62ff885`).
Re-scoring tier 1 with it is post-hoc. This run is not: v2 has never seen it.

| | |
| --- | --- |
| Cell | `agent-policy` on `gemini-4-argon-medium` (main model) |
| Haystack | MemoryAgentBench `factconsolidation_sh_32k` (dropped from tier 1, never scored): 2,310 facts, 231 batches of 10, 66 judged questions (44 conflicts) |
| Setup | Exactly tier 1's (same runner digest, prompts, `agy` 1.5.3 and flags, 40-call cap, quota gate) |
| Scoring | Matcher v2 as frozen; `flat` reference: the offline `flat` arm of the same haystack, re-scored with v2 |
| Not used | The 28 batches of this cell that ran before tier 1 dropped this haystack (`tier1-dropped/`, unread) |

**Lines** (the same values as section 5; MemoryAgentBench has no deletions, so no G5):

| Line | Statistic | Line |
| --- | --- | --- |
| G1 | `stale-first`, flat minus agent, paired (44 conflicts) | ≥ 0.30 |
| G2 | `retired` (44 conflicts) | ≥ 0.70 |
| G3 | `current@10`, agent minus flat, paired (66 questions) | ≥ −0.05 |
| G4 | `lost` (every judged current value) | ≤ 0.05 (upper bound for confirmed) |

Verdicts as in section 5. **Audit first** (6.3 with v2): up to 50 `retired` failures and 50 `lost` cases
(seed 20261106) judged on the workspace at the judgment point; more than 20% matching errors in either sample
and the lines are reported as unreliable. With 44 conflicts and 63 current values, the sample is the whole
population. The reference arms on this haystack under v2: flat `stale-first` 0.795, `current@10` 0.970;
oracle `stale-first` 0.000, `retired` 0.955.

### 9a. Matcher v3 as a secondary scoring (registered 2026-11-08 17:10Z, before any record of this run was read)

Matcher v3 (`matcher3.py`, applied through `rescore3.py`) fixes the error classes the v2 audits found
(REPORT.md, "Matcher v3"). It was built on tier 1 only and frozen in `results/freeze_v3.json` (digest
`604902208468affb9ca2fc8d386e453024e058b6a2137add8a7f4153e85848a9`). The confirmatory run is scored with v2
as registered above (**primary**) and with v3 (**secondary**): the same lines, the same `flat` reference
(`gate1-v3`), and the same audit rule (6.3 with v3, every flagged case; a case flagged by both matchers is
judged once). If the two disagree on a verdict, v2's is the registered one and v3's is reported beside it.

## 10. Tier 1 with a local model: `qwen3.8-flash-next-iq3_s` on Strata (pre-registered 2026-11-08, before its first tier-1 call)

A local, 3-bit quantized model on the same benchmark as the Gemini cells, to compare against
`gemini-4-argon-medium` and `gemini-3.8-flash-medium`. Frozen in `results/freeze_qwen.json` (the client's digest
and everything below; `python -m evals.agent strata --tier 1` refuses to start if it no longer matches).

| | |
| --- | --- |
| Cells, in order | `agent-policy`, then `agent-overlay` (all 95 episodes each; `agent-overlay` starts after `agent-policy` is complete) |
| Model and server | `qwen3.8-flash-next-iq3_s` (IQ3_S) on the local Strata server (RTX 5070 Ti, `n_ctx` 262,144, one slot), `--jobs 1` |
| Client | `strata.py`: a fresh `[system, user]` conversation per session; the four tools from `tools/list` through `mcp_proxy.py`; assistant turns sent back whole (`reasoning_content`, `tool_calls`) |
| Settings | temperature 1.0, top_p 0.95, top_k 20 (the server's defaults, sent explicitly); `max_tokens` 32,768 per turn; 80 model turns; the 40-call cap; 3,600 s per session; 3 retries after restoring `overlay/` |
| Haystacks | tier 1 as run: the 95 MEME `nofiller` episodes (MemoryAgentBench 32k out, as for the Gemini cells) |
| Prompts | section 2, unchanged (the same system prompts and session messages) |
| Scoring | matcher v3 as frozen (`results/freeze_v3.json`), references `flat` and `oracle` from `gate1-v3`; v2 also reported |
| Lines | G1-G5, section 5 |
| Audit | 6.3 with v3 before the lines are read: up to 50 `retired` failures and 50 `lost` cases per cell, and 15 passes (seed 20261106); more than 20% matching errors in either flagged sample and that cell's lines are reported as unreliable. A case the existing labels already judge (the same workspace can't recur, so in practice none) keeps its verdict |
| Comparisons, no line | Qwen `agent-policy` against Argon and Flash `agent-policy`, and Qwen `agent-overlay` minus Qwen `agent-policy`, paired by unit, on every pooled metric |
| Not scored | a cell that doesn't finish all 95 episodes (it is reported as incomplete, with its telemetry) |

**How it differs from the Gemini cells, by construction.** There's no CLI: the system prompt and the tool
declarations reach the model as given, where `agy` adds its own framing. `agy`'s CLI validates arguments
against the schemas before sending them; this client forwards every call whose arguments are a JSON object,
and the server's answer, an error included, is the model's feedback. A call to any other tool name, or with
arguments that aren't a JSON object, is answered by the client with an error and not forwarded, as the CLI
does. One run per cell, no variance repeats. Projected from the smoke tier: about 6 h for `agent-policy` and
8.5 h for `agent-overlay`.


## 11. Reader QA on the saved workspaces (DRAFT 2026-11-09: not frozen, not run on any scored episode)

**Status: draft for review, waiting for the Gemini weekly quota.** The lines are proposals for the user to set.
Nothing below is frozen until a `freeze_reader.json` is committed, and no target or control question of a scored
episode is sent to any reader before that. On 2026-11-09 the first estimate of a Qwen-only run (58 h, from a
6-call probe) was too long, so the user decided to wait for the Gemini weekly quota to reset (about 2026-11-13)
and read with Argon. A dry-run on the smoke episodes (11.6) then measured all three readers on the real harness;
it informs the final reader choice (11.2), which the freeze fixes.

End-to-end answer accuracy becomes the primary metric for future tiers. It tests whether lineage on the retrieved
page turns into correct answers where raw history fails: MEME's Cascade, Absence and Deletion questions after the
change. Matcher v3 stays frozen as a secondary, diagnostic score (no v4: it is English-specific and paraphrase
keeps beating it).

### 11.1 Design

| | |
| --- | --- |
| Reader | `gemini-4-argon-medium` through `agy` (effort medium), after the weekly reset: one fresh conversation per question, the reader prompt as the agent's system prompt, no MCP server, and every tool call denied by the `PreToolUse` gate (`evals/agent/reader.py`). Comparison readers, if 11.2 keeps them: `gemini-3.8-flash-medium` the same way; `qwen3.8-flash-next-iq3_s` on the local Strata server (temperature 0, seed 20261106, `cache_prompt` false, `max_tokens` 4,096) |
| Memories (8 arms) | The saved final workspaces of tier 1, so no new writer session: `flat` and `oracle` (`gate1-v3`), Argon `agent-default`, `agent-policy`, `agent-overlay`, Flash `agent-policy`, Qwen `agent-policy`, `agent-overlay` |
| Target questions (378 per arm) | MEME after the change, asked at the end point: Cascade 158 (hop 1: 95, hop 2: 63), Absence 125 (95, 30), Deletion 95 |
| Control questions (378 per arm) | The same questions before the change, asked at their own points, on each workspace rebuilt by replaying the logged writes to that point (the replay is exact: PLAN.md ledger, the engine change of 2026-11-09) |
| Page | The harness runs `search(question, k=10)` and gives the reader each hit's full card in rank order (title, summary, body with its `Date:` line), plus the lineage fields `search()` returns, as plain text (`status`, `superseded_by`, `matched_via_superseded`, `baseline_superseded_by`, `missing_baselines`). The same prompt for every arm; `flat` simply has no lineage fields |
| Answer | JSON `{"status": "current" \| "uncertain" \| "removed" \| "unknown", "value": "..."}`, schema-constrained where the server supports it. One retry after invalid JSON or a cut-off; still invalid counts as wrong and is reported |
| Grading (no LLM) | Cascade: `status` current and `value` matches the gold current value. Absence: `status` uncertain (MEME's gold: "Uncertain — previously ..."; `unknown` is reported apart). Deletion: `status` removed or unknown and `value` doesn't name the deleted value (MEME's gold: "No — explicitly removed"; `removed` alone also reported). Controls: `status` current and the value matches. A value matches when the normalized gold (NFKC, casefolded, punctuation and whitespace collapsed; also without a trailing parenthetical, as in `dermatologist (monthly)`) and the normalized answer contain one another, at 3 characters or more. Every `current` answer the rule rejects is listed and checked by hand before any line is read |
| Lines (proposed) | R1, the mechanism: `oracle` minus `flat` on the targets, paired, ≥ +0.20. R2, in practice: each Argon cell minus `flat` on the targets ≥ +0.10. R3, no harm: `oracle` and each agent cell minus `flat` on the controls ≥ −0.05. Verdicts as in section 5 |
| Reported, no line | Per category (Cascade hop 1 and 2, Absence hop 1 and 2, Deletion); the Qwen and Flash cells; agent cells against `oracle`; per question, QA against v3's page judgment (`stale-first`, `stale@10`) |
| Variance | Qwen at temperature 0 is not deterministic on this server (11.4). The `flat` and `oracle` target sets run a second time; the spread is reported, and the lines are read on the first run |
| Frozen at the freeze | The reader prompt verbatim, the page renderer, the grader, the question lists and their digests, the server build and model file digest, the arms' workspace digests |

What it can't show: a dense raw-history RAG baseline (the local server has no embeddings endpoint), or a strong
reader (unless 11.2 moves the run to Argon). The claim it can support is over `flat`: lexical, timestamped raw
chunks.

### 11.2 Reader choice and the stage-1 gate

**Argon is the primary reader**, run after the weekly quota resets; it is the reader the lines are read on.
Flash and Qwen are kept only as comparison readers, and only if the dry-run (11.6) shows them reading the
controls about as well as Argon. Their role is to show whether the lineage effect depends on the reader, so
they add no line. The choice is recorded in the ledger with the dry-run's numbers before the freeze.

The reader run keeps two stages. **Stage 1** sends only the control questions of `flat` and `oracle` (756
calls), plus 40 of them asked twice; a reader fails it with more than 5% invalid or cut-off answers, accuracy
below 0.80 on `oracle`'s or `flat`'s controls, or `status` agreeing on fewer than 36 of the 40 repeats. **Stage
2** runs only if the primary reader passes. If Argon fails, the run stops for review: no automatic switch, and
no target result read. (The earlier Qwen-to-Argon fallback is moot now that Argon is the primary reader; if Qwen
is kept as a comparison reader and fails stage 1, it is dropped and reported.)

### 11.3 Workspace-state judge (only if hand audits must be replaced)

A Qwen judge at temperature 0 with a structured verdict (does this card present this value as current?), with the
arm hidden. Its prompt is developed only on the 470 tier-1 update and value labels (`labels.py`: 291 and 179).
Once the prompt is frozen, it is tested on the 165 verdicts made after v3's freeze (the two Qwen audits, 146; the
confirmatory audit, 19), each judged twice. It is accepted if it agrees on at least 0.90 of them overall and 0.80
within each kind. Flip rate and agreement on Qwen-written cards are reported apart. Until it passes, audits stay
manual (6.3).

### 11.4 Timing probe (done 2026-11-09; smoke episode, never scored)

Smoke episode `pl_001`, `flat` and `oracle`: 6 after-change questions with a draft prompt. Prompts were 2.2-2.4k
tokens; the reader generated 217-3,108 tokens (mostly reasoning), taking 5-38 s per call (median about 34 s).
All 6 answers were valid JSON; they were not graded. The same request twice at temperature 0 gave different
reasoning, and once a different answer; with a fixed seed and the prompt cache off, the answer repeated but the
reasoning still differed. Throughput over Qwen tier 1's 6,472 logged calls: 736 prompt tokens/s and 88 generated
tokens/s (medians).

### 11.5 Time and quota (measured in the dry-run, 11.6)

Per call: Argon about 8.0 s (mean; median 7.2 s) and about 0.002% of a weekly Gemini quota (at most 0.004% even if
Flash had cost nothing); Flash about 9.3 s and about the same quota; Qwen 9.2 s (mean; median 5.5 s), on the local
GPU. The 30 s per Qwen call that 11.4's six-call probe suggested was an overestimate: the reader prompt draws far
shorter reasoning (median 297 generated tokens).

| Item | Calls | Time | Gemini quota |
| --- | --- | --- | --- |
| Freeze (prompt and page version, grader, question lists, digests) | – | about 1 h of agent work; the harness exists (`evals/agent/reader.py`, `tests/test_reader_eval.py`) | – |
| Argon, the full run: 8 arms × 756 questions, plus `flat` and `oracle` targets a second time | 6,804 | about 15 h one at a time; about 2 h at 8 sessions in parallel | about 14% of a week (at most about 27%); about half of one five-hour bucket |
| Qwen as a comparison reader on `flat` and `oracle` (targets and controls) | 1,512 | about 4 h locally | – |
| Qwen on everything, if it were the reader | 6,804 | about 17 h locally | – |
| Grading, hand check of rejected values, report | – | minutes of compute, about 2 h of writing | – |

The weekly bucket was at 4.87% after the dry-run and resets about 2026-11-13; the full Argon run fits in a fresh
week several times over.

### 11.6 Dry-run on the smoke episodes (2026-11-09; never scored, not lines)

Tables: [results/reader_dry_smoke.md](results/reader_dry_smoke.md); raw answers in
`$MINDSLICE_AGENT_RUNS/reader-dry-smoke/` (they hold dataset text and are not committed). The smoke episodes
`pl_001`-`pl_005` were never scored. For each of the 8 cells: 16 targets (Cascade 6, Absence 5, Deletion 5) and
16 controls, read by Argon and Flash; Qwen read `flat` and `oracle`. The run used 1.25% of the weekly quota
(the user allowed 5%). With 16 questions a cell, these are directions, not estimates:

- **The harness works.** Every rebuilt page equals the recorded one (256 of 256), every answer was valid JSON,
  and no reader tried a tool.
- **The readers barely differ.** Argon and Flash give the same verdict on 248 of 256 questions, and Qwen on 62
  of 64 against Argon. The memory decides the answer, not the reader.
- **Lineage helps on the targets and costs nothing on the controls.** `oracle` minus `flat` on the targets:
  Argon +0.188 (draft-1 page) and +0.250 (draft-2), Flash +0.125 and +0.188, Qwen +0.062 and +0.062; on the
  controls 0.000 for every reader. The gain is in Absence (5/5 against 3/5) and Deletion (5/5 against 4/5).
- **Agent-written memory reads best.** Argon's `agent-policy` and `agent-overlay` workspaces gave 16/16 on the
  targets with both Gemini readers; Qwen's `agent-policy` workspace 10/16, no better than `flat`. The write-side
  crossover shows up in answers.
- **Cascade is the weak spot on lineage pages, and the page showed why.** With lineage notes alone (draft-1), a
  dependent and its rule are flagged `baseline_superseded_by: <card>` but that card, the root change, isn't on
  the page, so readers answered `uncertain`. Quoting the named card under the note (draft-2) fixed one of
  Argon's three misses and one of Flash's four. The rest are a rule the reader didn't apply, and right values
  given as `uncertain` (graded wrong: committing to the new value is what Cascade asks).
- **`flat` fails by reading, not retrieval.** The gold value was on 15 of 16 of its target pages; readers took
  the stale value despite the dates.

**Proposed for the freeze (the user decides):** Argon as the only reader the lines are read on; page version
draft-2; Qwen as a free comparison reader on `flat` and `oracle` only; Flash dropped (it reads like Argon). The
lines R1-R3 stay the user's to set; the dry-run's direction is recorded here, before any scored episode is read.
The prompt is not tuned further on these five episodes.
