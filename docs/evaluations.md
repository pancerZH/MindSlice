# MindSlice evaluations

What the evaluations measured, what they settled in the engine's design, and how to run them. None of this is
needed to use MindSlice; see the [setup guide](getting-started.md) for that and the [reference](reference.md) for how it works.

## What the evaluations show, and where MindSlice stops

Three evaluations, each scored deterministically: [`evals/retrieval`](../evals/retrieval/README.md) (search on
authored cards), [`evals/external`](../evals/external/REPORT.md) (four published memory benchmarks, no language
model) and [`evals/agent`](../evals/agent/REPORT.md) (LLM agents writing memory through the MCP tools).

- **Lineage keeps the current fact first.** Over 442 benchmark state questions a stale fact outranks the
  current one on 62% of first pages without lineage and on none with the annotations' lineage. Agents writing
  their own lineage (Argon, MEME): a stale card ranks first on 0-0.6% of Cascade pages (flat 33%), and the
  MemoryAgentBench 32k confirmatory run confirmed all four pre-registered lines.
- **Weaker models write weaker lineage.** A local 3-bit Qwen retired 0.392-0.566 of stale facts (Argon
  0.730-0.922) and forgot 0.315-0.609 of what it was asked to (Argon 0.946-0.989).
- **The page turns into answers.** Reading the same top-10 pages, a local 3-bit Qwen answered 0.76 of MEME's
  after-change questions (Cascade, Absence, Deletion) correctly from memory with lineage and 0.48 from timestamped
  raw chunks, with no cost before the change (pre-registered comparison reader; the lines are read on Argon after
  the weekly Gemini reset). No dense raw-history RAG baseline has been run.

The usual alternative is RAG over the raw history: keep every turn, retrieve with dense embeddings and a
reranker. Three boundaries for reading these numbers against it (details in
[the agent report](../evals/agent/REPORT.md#against-flat-history-and-raw-history-rag)):

1. **The benchmark replay's token bill is not the price of using memory.** The agent evaluation's 17M-115M
   context tokens per cell are write-side only (the harness searches the questions, with no model): a separate
   memory-keeper agent re-reads each transcript in a fresh conversation, re-sending prompt, tool schemas and
   history at every step, a multiple of 37-76 per token of dialogue for Argon and 230-550 for Flash. In use, the
   agent that already holds the conversation writes with a few extra tool calls, and reading is bounded by the
   engine, not the history: `search(k=10)` returns about 2.1-2.4k tokens and `read()` about 0.3-0.6k (medians),
   both on 5-session MEME memories and on a 2,309-card (about 274k-token) MemoryAgentBench memory. That is the
   same order as injecting the top 10 raw rounds (2.5k on MEME): MindSlice doesn't read fewer tokens than raw
   retrieval, it reads a page with the current fact first and stale ones redirected or flagged.
2. **Retrieval is lexical (SQLite FTS5), not dense.** It is near complete when the question reuses the
   evidence's words (Recall@10 0.98-1.00 on LongMemEval single-session questions and MEME's exact recall,
   including its invented names; 0.976 on MemoryAgentBench), deterministic, explainable (`coverage`,
   `unmatched_terms`) and dependency-free. It is weak on implicit conversational paraphrase (LoCoMo multi-hop
   and open-domain 0.30; "what do I do in my free time?" 0.40 when the evidence says "hobby"): the case dense
   retrievers and rerankers are built for. None has been run here, so there is no measured gap to quote.
   MindSlice's remedies are authored `aliases` (+0.16 nDCG@5 on vocabulary-gap queries) and agents rephrasing
   after `unmatched_terms`; a dense layer can sit above the engine, but none ships.
3. **`agent-overlay` is raw history plus agent-written lineage, with constraints.** The transcript is mounted
   verbatim as a read-only slice and the agent writes only lineage. It retired the most on Argon (0.922) but
   the least on Qwen (0.392): every raw round stating an old value has to be found and superseded. Forgetting
   hides rounds without erasing them; `supersedes` retires whole rounds; it took more context (30M against 17M
   tokens on Argon); and something outside the agent has to append each transcript to the history slice.

## Search decisions the evaluations settled

On the evaluation's blind holdout ([`evals/retrieval`](../evals/retrieval/PLAN.md), `holdout-3`), aliases
written by an agent following the then-current manual `slice-builder` workflow added 0.16 nDCG@5
on queries in the asker's own words, and 0.14 overall. This predates the
[Forge integration](../skills/slice-builder/SKILL.md) and is not an evaluation of Forge. They also put about one card from the other language's handbook on every first page, which costs
ordinary queries a little when only the asker's own handbook counts (-0.025).

Spelling suggestions (`did_you_mean`) were tried and removed. A small corpus lacks many ordinary words,
so they fired on 52 of 230 evaluation queries, only 5 of them typos (`how` -> `now`), and retrying with
them helped 4 queries and hurt 21. Constraining them would mean thresholds fitted to a handful of English
typos. The caller, usually a language model, can correct its own spelling once `unmatched_terms` names the
word that missed.

Coverage-first ordering was tried and evaluated ([`evals/retrieval`](../evals/retrieval/PLAN.md)). On a
harder, multi-candidate holdout it trailed BM25 order by 0.026 nDCG@5 overall (0.065 in English) and
gained only 0.002 on tiny corpora. In a small corpus, words that are rare but carry no topic ("do",
"when") earned too much coverage credit. The engine went back to BM25 order.

## The evaluation suites

`evals/retrieval/` is a small English and Chinese retrieval-quality evaluation of `search()`. It reports
nDCG@5, Recall@10 and MRR@10 with bootstrap intervals, compares against alternative systems, and fixes its
pass lines in advance. See [its README](../evals/retrieval/README.md) and [plan](../evals/retrieval/PLAN.md).

`evals/external/` runs the engine on four published memory benchmarks (LongMemEval-S, LoCoMo, MEME,
MemoryAgentBench) with no language model: a fixed compiler turns their dialogue into cards, and scoring
compares `search()` and `read()` responses with the datasets' annotations. It measures retrieval, whether
`coverage` and `unmatched_terms` flag unanswerable questions, and what `supersedes` / `extends` / deletion
do for stale facts. See [its README](../evals/external/README.md), [plan](../evals/external/PLAN.md) and
[report](../evals/external/REPORT.md).

`evals/agent/` runs the test those results leave open ([plan](../evals/agent_test.md), [frozen setup](../evals/agent/PLAN.md),
[report](../evals/agent/REPORT.md)): whether an LLM agent writing memory through the MCP tools records `supersedes`
well enough to keep stale facts behind current ones, scored by the same deterministic harness. One arm
(`agent-overlay`) mounts the raw sessions as a read-only slice, so the agent writes only lineage over them.
