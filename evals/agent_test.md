# Agent-in-the-loop lineage test: plan

**Status: planned, not run.** Nothing here has been executed with a language model. This document is the
specification for whoever arranges the runs. Section 8 lists what must be fixed and recorded before the
first scored run.

## 1. Why this test

MindSlice keeps current facts ahead of stale ones only if someone writes the lineage. On four published
benchmarks ([`external/REPORT.md`](external/REPORT.md)):

| Setting | Stale fact outranks the current one (pooled, 442 questions) | Stale fact on the page, unwarned |
| --- | --- | --- |
| Flat cards, no lineage (Mode A) | 0.620 | 0.934 |
| Lineage from the annotations (Mode B, an oracle) | 0.000 | 0.000 |

Mode C showed that the engine can't find the superseded card lexically at write time (the predecessor is in
the top 3 for 0.685 of writes; a hint would also fire on most cards that merely *extend* a baseline). So the
gap between 0.620 and 0.000 depends entirely on the agent. **This test measures where a real agent lands
between the two**, and what its mistakes cost.

Questions, in order of importance:

1. **Does the agent retire stale facts?** When the user states a new value, does the old one stop being
   presented as current (`supersedes`, `delete`, or a rewrite)?
2. **Does it avoid harm?** Wrong `supersedes` or deletes hide facts that are still true. MEME's dependents
   and if-then rules are the trap: they are lexically close to their baseline but replace nothing.
3. **End to end:** with the agent's memory, how often does `search(question)` put a stale fact first, and is
   the current fact still on the first page?
4. **Deletion:** after "please forget X", is X gone from active memory?

Answer accuracy (a reader model answering from memory) is optional and comes after (section 9).

## 2. Design in one paragraph

For each haystack, a fresh workspace and a fresh agent. The agent reads the haystack's sessions **in
chronological order, one session per conversation** (nothing carries over between sessions except
MindSlice itself), and maintains memory with the four MCP tools. It never sees questions, answers or
annotations. At each point where the benchmark asks a question, the harness, not the agent, runs
`search(question, k=10)` on the agent's workspace and scores the first page **deterministically**, with the
same definitions as Mode B. The two existing arms (flat, oracle) are re-scored with the same value-based
scorer, so all arms are compared on the same questions with the same rules.

## 3. Arms

| Arm | Memory writer | Cost |
| --- | --- | --- |
| `flat` | The harness's template cards, no lineage (Mode A) | none (exists) |
| `oracle` | Template cards plus the annotations' lineage (Mode B) | none (exists) |
| `agent-default` | An LLM agent with the MCP server as shipped (tool descriptions and server instructions) and the neutral task prompt (4.2) | LLM |
| `agent-policy` | Same, plus the lineage policy paragraph (4.3) | LLM |
| `agent-overlay` | The `flat` cards in a read-only `@history` slice; the agent writes only lineage cards into `@overlay`, with the policy paragraph and an addendum (4.4) | LLM |

Run the agent arms with **at least two models of different capability** (for example the current Sonnet
and Haiku; Opus if the budget allows) to see whether lineage-writing scales with the model. Record exact
model ids.

Three **scripted agents** validate the runner before any LLM run (section 7): `scripted-flat` writes each
round as a card through the tools, `scripted-oracle` replays the annotations' lineage through the tools,
and `scripted-overlay` replays the same lineage as `agent-overlay` cards (4.4). The first two must
reproduce the `flat` and `oracle` numbers; `scripted-overlay` must reproduce `oracle`'s.

## 4. The agent protocol

### 4.1 Tools

Expose exactly MindSlice's four MCP tools (`manifest`, `search`, `read`, `write`) with the shipped schemas
and descriptions (`mindslice/mcp_server.py`: `TOOLS`, `INSTRUCTIONS`). Either:

- **real MCP over stdio**: `python -m mindslice -w <workspace> mcp`, from an MCP-capable client; or
- **in process** (recommended for throughput): give the model `TOOLS` as its tool definitions, put
  `INSTRUCTIONS` in the system prompt as the server's instructions, and dispatch each call with
  `MCPServer(ws).call_tool(name, arguments)`. Return its result, errors included, to the model unchanged.

Writes go straight to `@overlay` (no `--stage-writes`). The workspace has one mount, `@overlay`, and starts
empty (`agent-overlay` adds a read-only `@history` slice, 4.4).

### 4.2 Neutral task prompt (`agent-default`), verbatim

System prompt: the MCP `INSTRUCTIONS` string, then:

> You are the long-term memory keeper for one user. You will be shown their conversations with an
> assistant, one session at a time, in the order they happened. Use the MindSlice tools to record what is
> worth remembering about the user for future conversations, and keep that memory accurate and up to date.
> You will not be asked questions about it. When you have finished with this session, reply with DONE.

First user message of each conversation:

> Session {i} of {n}, {date}:
>
> {transcript}

The transcript is exactly the turn lines the harness writes into card bodies (`make_card` in
`evals/external/corpus.py`): `{Speaker}: {text}` per turn (`User`, `Assistant`, or the dataset's names),
continuation lines indented, image captions as `{Speaker} shared an image: …`, `[[` written as `[ [`. For
MemoryAgentBench, which is one list of facts, each "session" is a batch of **50 consecutive facts**, one per
line in dataset order, headed `Facts {a}-{b} of {N}, in the order they were stated:`. The `{date}` is the
session's date as the harness's `Date:` line gives it, or omitted when the dataset has none.

### 4.3 Policy paragraph (`agent-policy` only), appended to the system prompt, verbatim

> Before you write, search for cards about the same thing. If the new information replaces something
> already recorded (a changed value, a new preference, a correction), write the new card with
> `supersedes` naming the old card's address, rather than leaving both active or deleting the old one,
> and restate anything in the old card that is still true. If it refines, adds an exception or an
> if-then rule to, or depends on something that stays true (a choice made because of an earlier
> preference or plan), write it with `extends` naming that card, so it is flagged if that card later
> changes. If you can't tell which, use `extends`: it hides nothing. If the user asks you to forget
> something, delete the cards that state it. Put each fact that can change on its own card, and keep its
> concrete values, names, dates, conditions and the user's own wording; the summary states the fact.

This is the runtime table and lineage rules of `skills/slice-builder/SKILL.md` ("Stage 2") in prose. The
shipped `write` description and `INSTRUCTIONS` define `supersedes`, `extends` and `delete` the same way,
so `agent-default` versus `agent-policy` measures the procedure (search first, choose an operation) and
the emphasis, not access to the definitions.

### 4.4 Lineage over mounted history (`agent-overlay`)

In the first two agent arms the agent is the only writer, so their scores mix two skills: what it keeps
(a writer that compresses dialogue into terse facts drops details and the words search needs, which
`current@10` and `lost` count) and the lineage it writes. On these four benchmarks,
[Bao et al. (2026)](https://arxiv.org/abs/2610.30755) find retrieval over raw history ahead of
LLM-transformed memory stores, and Mem0's LLM-decided updates and deletes rarely effective, with accuracy
higher when they are disabled. `agent-overlay` takes extraction out of the agent's hands: the raw history
is mounted where the agent can't change it, and the agent writes only lineage.

- **Workspace.** The `flat` cards (rounds for MEME and LongMemEval, one card per fact for
  MemoryAgentBench, as in Mode B) are files in `history.slice/`, mounted read-only as `@history` (role
  `baseline`). The harness adds session *i*'s cards before the agent's session *i* conversation (the
  engine re-indexes changed files before every call), so the agent can search the session it is reading.
  `@overlay` starts empty.
- **What the agent writes.** It can't edit `@history`, so its `@overlay` cards carry the lineage: for a
  changed value, a card stating the new value that supersedes every card stating the old one (in
  `@history`, and its own earlier copy); for a dependent decision or an if-then rule, a card restating it
  that extends the card holding its premise and supersedes the `@history` card it came from (otherwise
  that read-only copy stays active, unwarned, when the premise changes); for a request to forget, a card
  that supersedes each `@history` card stating the value and restates the rest of that card without it.
- **Prompt.** `agent-policy`'s system prompt, then this addendum, verbatim:

  > Every session is already stored verbatim in the read-only `@history` slice. Don't copy it: write to
  > `@overlay` only to keep that history accurate. When a value changes, write a card with the new value
  > that `supersedes` every card stating the old one, in `@history` or `@overlay`. When something depends
  > on or adds a rule to an earlier fact, write a card restating it that `extends` the card holding that
  > fact and `supersedes` the `@history` card it came from. When the user asks you to forget something,
  > write a card that `supersedes` each `@history` card stating it and restates the rest of that card
  > (you can still delete your own `@overlay` cards). In every replacement, restate any other fact from
  > the old card that is still true.

- **Reading it.** `oracle` has the same cards and the annotations' lineage, so `oracle` versus
  `agent-overlay` prices the agent's lineage alone, and `agent-overlay` versus `agent-policy` prices
  extraction (plus the addendum's extra instruction). The history can't be rewritten or deleted, so here
  `lost` comes only from a wrong `supersedes`: a `@history` card hidden behind a replacement that doesn't
  restate its value.
- **Limits.** `supersedes` acts on whole cards, so retiring one fact of a round that states two hides both
  unless the replacement restates the other (`lost` counts it). Forgetting is hiding, not erasure: a
  superseded `@history` card leaves search results and default `read()`, which `forgotten` counts, but its
  text stays on disk, reachable with `follow_supersedes=false` and named in `matched_via_superseded`.
  Erasing it takes a human edit of `history.slice/`; report `forgotten` for this arm with that caveat.
- **Scripted check.** `scripted-overlay` writes these cards from the annotations: each copies the
  `@history` card that states the new value, dependent or rule, with the annotations' lineage (`extends`
  naming the premise's current card, preferring an `@overlay` replacement); a forget card states only that
  the value was forgotten.

### 4.5 Limits and logging

- At most **40 tool calls per session**. Hitting the cap ends the session; count and report it.
- Model parameters: the provider's defaults unless a parameter is fixed in section 8 (record whatever is
  used: temperature, max output tokens, thinking or effort settings).
- Log every turn as JSONL: haystack, session, model request and response, each tool call with arguments and
  result, token usage, latency, errors. Keep the final `overlay/` directory of every workspace (it is plain
  Markdown) for auditing.
- If a call fails at the provider (rate limit, timeout), retry the same request; never skip a session. If
  a session still can't complete, mark the haystack failed and report it; don't drop it from the
  denominator silently.

## 5. Data and tiers

Same datasets, compilers and question positions as `evals/external` (MEME's before-change questions are
asked right after their session). LongMemEval's stale value isn't annotated as a string (only its turn), so
LongMemEval contributes the current-fact metric only (section 6).

Reading volume is the dialogue text the agent must see, estimated as characters ÷ 4 from the pinned files.
Actual input tokens are a multiple of it (system prompt and tool schemas on every call, tool results, and
the conversation re-sent at each step); **measure the multiple on the smoke tier** before budgeting the rest.

| Tier | Data | Haystacks | Sessions | Questions | Reading volume |
| --- | --- | --- | --- | --- | --- |
| Smoke (prompt and plumbing checks; never scored for lines) | MEME `nofiller` `pl_001`-`pl_005` (the 5 lowest ids); MemoryAgentBench 6k | 6 | 25 + 10 batches | 52 + 82 | about 0.03M |
| 1 (main) | MEME `nofiller`, the other 95 episodes; MemoryAgentBench 32k | 96 | 475 + 47 batches | 1,136 + 66 | about 0.40M |
| 2 (realism) | MEME `filler32k` (about 32k of unrelated chat per episode); LongMemEval-S knowledge updates; MemoryAgentBench 64k | 171 | 2,143 + 3,329 + 92 batches | 1,188 + 70 + 77 | about 12.5M |

MemoryAgentBench asks its questions after the whole context, so each context belongs to one tier. Tier 2's
MEME `filler32k` episodes include the 5 smoke episodes' evidence (with filler added); that's acceptable
because tier 2 is read only after tier 1.

Whole datasets for reference: MEME `nofiller` 100 episodes, 500 sessions, 0.39M; MEME `filler32k` 2,143
sessions, 3.85M; LongMemEval-S's 70 knowledge-update haystacks, 3,329 sessions, 8.55M (about 122k each);
MemoryAgentBench 6k / 32k / 64k / 262k contexts with 455 / 2,310 / 4,580 / 18,332 facts (10 / 47 / 92 / 367
batches; 82 / 66 / 77 / 68 labeled questions). Leave the 262k context out unless tier 2 is cheap.

## 6. Scoring

### 6.1 Value-based judgments

Agent cards don't correspond to dataset turns, so card-level judgments are by **value strings**:

- **MEME:** every gold fact has a `value`. Per question, the compiler's `meta` already names the stale and
  current units (`stale`, `current`, `history`, `deleted_values`); export each unit's value string alongside.
- **MemoryAgentBench:** the current value is the derived answer; the stale value is the object of the
  earlier conflicting fact (the compiler already aligns the two facts' wording up to the object).
- **LongMemEval:** the current value is the question's answer string; no stale string.

A card **states** a value when the normalized value (casefolded, whitespace collapsed, surrounding
punctuation stripped) is a substring of the normalized card text (title, summary, body, aliases). A card is
**stale** for a question when it states a stale value and not the current one (when a current one exists).
A card is **warned** exactly as in Mode B: `status` not `active`, or `baseline_superseded_by` or
`missing_baselines` in its preview.

### 6.2 Metrics

Computed for every arm, `flat` and `oracle` included, with the value-based judgments:

| Metric | Definition | Questions |
| --- | --- | --- |
| `stale-first` | An unwarned stale card ranks above every current card on `search(question, k=10)` | MEME Cascade, MemoryAgentBench conflicts |
| `stale@10` | An unwarned stale card is on the first page | same, plus MEME Absence |
| `current@10` | Some card on the first page states the current value | MEME Cascade, MemoryAgentBench, LongMemEval |
| `retired` | After the update's session, no active, unwarned card in the whole workspace is stale for it (not just on the page) | every annotated update: MEME updates and root changes, MemoryAgentBench conflicts |
| `lost` | A value that is current at question time and was stated before it is stated by no active card in the workspace (harm: over-eager supersede, delete or rewrite) | every current value at every question point, MEME dependents and rules reported separately |
| `forgotten` | After a deletion request, no active card states the deleted value | MEME Deletion |
| `history-named@10` | As Mode B's Tracking metric, value-based | MEME Tracking |

Also reported, with no lines: per session the tool-call count, the mix of `create` / `append` / `replace` /
`delete`, how many writes carry `supersedes` or `extends`, cards per haystack, input and output tokens, cost,
tool errors, sessions that hit the call cap, and failed haystacks.

Intervals as in `evals/external`: 95% percentile bootstrap over questions (or updates, or values), 2,000
replicates, seed 20261106; differences between arms paired by question.

### 6.3 Manual audit

Value matching misses paraphrases ("Therwyn Compact" written as "a compact car"). Before reading the lines,
audit a fixed random sample (seed 20261106) of 50 `retired` failures and 50 `lost` cases per agent arm by
opening the workspace files, and report the share where matching was wrong. If more than 20% of either
sample is a matching error, report the lines as unreliable instead of reading them.

## 7. Building the runner (before any LLM run)

Place it beside the existing harness (for example `evals/agent/`), reusing `evals/external`'s loaders,
transcript text and question positions:

1. **Value export** in the compilers (6.1), with tests on the synthetic datasets in
   `tests/test_external_eval.py`.
2. **Value-based scorer** (6.2), applied to Mode A and Mode B workspaces. Expect it to agree with the
   card-level numbers in [`external/results/summary.md`](external/results/summary.md) up to matching
   noise; document every disagreement.
3. **Agent runner** (section 4) with a pluggable "agent": a function from (system prompt, session message,
   tool dispatcher) to a finished session.
4. **Scripted agents**: `scripted-flat`, `scripted-oracle` and `scripted-overlay` (section 3) through the
   same tool interface. Acceptance: their metrics equal `flat`, `oracle` and `oracle` within matching noise
   on all of tier 1. This proves the plumbing (ordering, question timing, scoring) before any money is
   spent. Scripted agents run offline, so they also belong in CI on the synthetic datasets.
5. **LLM agent** adapter for the chosen provider, then the smoke tier.

## 8. Protocol and pre-registration

1. Build and validate (section 7). Fix the engine commit; nothing in `mindslice/` changes from the smoke
   tier to the end of tier 1.
2. **Smoke tier**: iterate on plumbing, transcript formatting and the call cap freely. Prompt wording may
   change here only for bugs (for example, the agent never replies DONE); log every change. Measure the
   token multiple and project the cost of tiers 1 and 2.
3. **Freeze**, in a committed `evals/agent/PLAN.md` before the first tier-1 call: the prompts (verbatim, with
   SHA-256), model ids and parameters, tiers and haystack lists, the scorer's code digest, the audit sample
   seed, and the lines below with their final values.
4. **Tier 1, once** per arm and model. Additionally repeat `agent-policy` with the main model 3 times on 20
   fixed MEME episodes to measure run-to-run variance; report it beside the lines.
5. Audit (6.3), then read the lines. A miss stays a miss; changes after the read need a new tier or a new
   holdout.
6. Tier 2 only after tier 1 is read, with the same frozen setup.

**Suggested lines** (pooled over tier 1, per agent arm and model; to be confirmed or revised at the freeze,
never after):

| Line | Claim | Statistic | Suggested line |
| --- | --- | --- | --- |
| G1 | The agent's lineage cuts stale-first substantially | `stale-first`, flat minus agent, paired | ≥ 0.30 (the oracle cuts about 0.6) |
| G2 | The agent retires most stale facts | `retired` | ≥ 0.70 |
| G3 | Its memory keeps the current fact findable | `current@10`, agent minus flat, paired | ≥ −0.05 |
| G4 | It rarely hides a true fact | `lost`, all current values | ≤ 0.05 (upper bound for "confirmed") |
| G5 | It forgets on request | `forgotten` | ≥ 0.90 |

Verdicts as in `evals/external/PLAN.md`: **confirmed** (the interval clears the line), **point pass**, or
**miss**; for G4, lower is better.

## 9. Optional: answer accuracy

After tier 1 is read: a reader model gets each benchmark question, the four tools on the agent's (or the
oracle's, or the flat) workspace, and a fixed prompt to answer from memory only. Grade with each
benchmark's own grader or judge prompt, recorded verbatim. This measures the whole system, but it adds a
second model's variance, so keep it out of G1-G5.

## 10. What the outcomes would mean

| Outcome | Reading | Likely next step |
| --- | --- | --- |
| G1 and G2 hold, G4 holds | Agents write usable lineage; the design works end to end | Tier 2 for realism; then answer accuracy |
| G2 misses under `agent-default` but holds under `agent-policy` | Agents can do it but the shipped guidance doesn't ask clearly enough | Move the rest of the policy (search first, then choose) into the MCP `INSTRUCTIONS`; re-test on a fresh tier |
| G2 misses under both | Agents don't notice supersession from dialogue | Consider an end-of-session consolidation step (SKILL.md "Stage 3") as its own arm |
| G4 misses | Agents over-supersede or over-delete, which hides true facts | Look at which writes did it (likely `extends` cases); consider tool-description changes or requiring a `read` of the target before `supersedes` |
| G3 misses | The agent's cards are harder to find than raw dialogue | Card-authoring guidance (summaries, aliases), as in `evals/retrieval` |
| G3 or G4 misses under `agent-policy` but holds under `agent-overlay` | Extraction, not lineage, is the weak step | Recommend mounting raw history read-only with an agent-written lineage overlay |

## 11. Known biases and risks

- **Value matching** both misses paraphrases and can count a card that mentions an old value as history
  ("used to drive X, now Y" is not stale, because it states the current value too; "may no longer be X"
  would count as stale). The audit (6.3) bounds this.
- **Prompt sensitivity.** Two prompts are a small sample of wording; report both rather than picking one.
- **Benchmark familiarity.** These datasets are public, and a model may have seen them. That matters little
  here because the agent only writes memory and never answers, but note the model's training cutoff.
- **Degenerate strategies.** An agent that stores each session verbatim reproduces `flat`; one that stores
  nothing scores well on `stale@10` and badly on `current@10` and `lost`. Report the operation mix so these
  are visible.
- **Same author.** This plan was written by the agent that built the engine and its harnesses. The lines are
  suggestions so that whoever runs the test can set them independently before seeing any result.
