# Reader QA dry-run on the smoke episodes (2026-11-09; never scored, not lines)

PLAN.md section 11.6. MEME `nofiller` `pl_001`-`pl_005` (the smoke tier, never scored), the saved workspaces of every cell, 16 target questions (Cascade 6, Absence 5, Deletion 5, after the change) and their 16 before-change controls per cell, read by Argon, Flash (through `agy`, all tools denied) and the local Qwen (`evals/agent/reader.py`). Cells show correct/n and (Cascade/Absence/Deletion) correct. n is tiny: read these as directions, not estimates.

**Harness check.** Every rebuilt page equals the page the run recorded: 256 of 256 (8 cells x 32 questions, no model).

## Page version draft-1 (lineage notes only)

| Memory | Argon reads: targets | Flash reads: targets | Qwen reads: targets | Argon: controls | Flash: controls | Qwen: controls |
| --- | --- | --- | --- | --- | --- | --- |
| `flat` | 10/16 (3/3/4) | 10/16 (3/3/4) | 12/16 (5/3/4) | 14/16 (5/5/4) | 14/16 (5/5/4) | 14/16 (5/5/4) |
| `oracle` | 13/16 (3/5/5) | 12/16 (2/5/5) | 13/16 (3/5/5) | 14/16 (5/5/4) | 14/16 (5/5/4) | 14/16 (5/5/4) |
| Argon `agent-default` | 14/16 (4/5/5) | 14/16 (4/5/5) | – | 15/16 (6/5/4) | 15/16 (6/5/4) | – |
| Argon `agent-policy` | 16/16 (6/5/5) | 16/16 (6/5/5) | – | 15/16 (6/5/4) | 15/16 (6/5/4) | – |
| Argon `agent-overlay` | 16/16 (6/5/5) | 16/16 (6/5/5) | – | 15/16 (6/5/4) | 15/16 (6/5/4) | – |
| Flash `agent-policy` | 13/16 (3/5/5) | 14/16 (4/5/5) | – | 14/16 (6/5/3) | 14/16 (6/5/3) | – |
| Qwen `agent-policy` | 10/16 (1/5/4) | 10/16 (1/4/5) | – | 15/16 (6/5/4) | 15/16 (6/5/4) | – |
| Qwen `agent-overlay` | 13/16 (3/5/5) | 13/16 (3/5/5) | – | 15/16 (6/5/4) | 15/16 (6/5/4) | – |

## Page version draft-2 (a card a lineage note names is quoted when it isn't on the page)

| Memory | Argon: targets | Flash: targets | Qwen: targets | Argon: controls | Flash: controls | Qwen: controls |
| --- | --- | --- | --- | --- | --- | --- |
| `flat` | 10/16 (3/3/4) | 10/16 (3/3/4) | 11/16 (4/3/4) | 14/16 (5/5/4) | 14/16 (5/5/4) | 14/16 (5/5/4) |
| `oracle` | 14/16 (4/5/5) | 13/16 (3/5/5) | 12/16 (3/4/5) | 14/16 (5/5/4) | 14/16 (5/5/4) | 14/16 (5/5/4) |

## Readers and cost

- Same correctness, Argon and Flash: 248/256 (draft-1); Argon and Qwen: 62/64.
- Argon: 320 calls, every answer valid JSON; latency median 7.2 s, mean 8.0 s.
- Flash: 320 calls, every answer valid JSON; latency median 6.6 s, mean 9.3 s.
- Qwen: 128 calls, every answer valid JSON; latency median 5.5 s, mean 9.2 s.
- Gemini quota for the whole dry-run (Argon 322 calls including 2 probes, Flash 320): weekly 6.12% -> 4.87%, 1.25% of a week, about 0.002% per call; the five-hour bucket 100% -> 95%.
