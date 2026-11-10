# Agent-in-the-loop lineage test

Where a real LLM agent lands between MindSlice's flat cards (Mode A) and the annotations' lineage (Mode B)
when it writes memory itself through the four MCP tools. Specification:
[`../agent_test.md`](../agent_test.md). Frozen setup: [PLAN.md](PLAN.md). Findings: [REPORT.md](REPORT.md). How the protocol got there (matcher
post-mortems, cost and quota re-freezes): [decision_ledger.md](decision_ledger.md).
Generated tables: [`results/`](results/).

## Run it

```bash
python -m evals.external fetch                       # the datasets (as for evals/external)
python -m evals.agent offline --tier 1 --run gate1   # flat, oracle and the scripted agents (no LLM; ~4 min on 14 cores)
python -m evals.agent gate --run gate1 --write       # Gate 1: scripted agents vs flat / oracle
python -m evals.agent levels --run gate1             # value-based vs card-level judgments
python -m evals.agent agy --tier smoke --run smoke --models gemini-3.8-flash-medium,gemini-4-argon-medium --jobs 8
python -m evals.agent offline --tier smoke --run gate1-smoke && python -m evals.agent report --run smoke --flat-from gate1-smoke --no-lines
python -m evals.agent project --run smoke             # tier-1 runtime and token projection from the smoke tier
python -m evals.agent freeze [--check]               # what PLAN.md freezes; tier 1 refuses to run if it changed
```

Runs live outside the repository (`$MINDSLICE_AGENT_RUNS`, default `~/.cache/mindslice/agent-runs`), one
directory per arm, model and haystack: `ws/` (the workspace; `ws/overlay/` is the agent's Markdown memory,
kept for auditing), `records.jsonl` (every judgment and per-session telemetry), `calls.jsonl` (every MCP
message and tool call with arguments, result and latency) and, for LLM arms, `agy/sNNN/` (the CLI's
`stream-json` trace, the tool-gate log and the exact configuration of that session). They hold dataset text
and are never committed.

`tests/test_agent_eval.py` runs in CI without data or a model: prompts verbatim from the plan, transcript
formats, value matching, the scripted agents against flat and oracle on synthetic datasets, the dispatcher
cap, the MCP proxy, and the CLI trace parser.

## Layout

| Path | What it is |
| --- | --- |
| `sessions.py` | What the agent reads (one conversation per session; MemoryAgentBench in 50-fact batches) and the tiers |
| `prompts.py` | The prompts of agent_test.md 4.2-4.4, verbatim, and their SHA-256 |
| `plan.py` | What is judged after which session: questions, updates (`retired`), deletions (`forgotten`), current values (`lost`) |
| `judge.py` | Value-based judgments on any workspace (what a card *states*; warned as in Mode B) |
| `score.py` | Metrics, bootstrap intervals, paired differences, lines G1-G5, telemetry |
| `runner.py` | One writer over one haystack: sessions in order, judgments at each point |
| `agents.py` | `flat`, `oracle` and the scripted agents (`scripted-flat`, `scripted-oracle`, `scripted-overlay`) |
| `tools.py` | In-process tool dispatch (as MCP `tools/call`), the 40-call cap, call telemetry |
| `mcp_proxy.py` | Thin stdio wrapper around `python -m mindslice -w <ws> mcp`: logs every message, enforces the cap |
| `agy.py` | The LLM arms through the Antigravity CLI (`agy --print`, real MCP over stdio), one fresh conversation per session |
| `tool_gate.py` | The CLI's `PreToolUse` hook: only MCP tools may run |
| `run.py`, `report.py` | CLI and Markdown rendering |
