# Run `confirm-mab32k-v3`

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.023 [0.000, 0.068] | 0.970 [0.924, 1.000] | 0.909 [0.818, 0.977] | 0.000 [0.000, 0.000] | – | – |
| flat | 0.795 [0.659, 0.909] | 0.955 [0.886, 1.000] | 0.970 [0.924, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – | – |
| oracle | 0.000 [0.000, 0.000] | 0.045 [0.000, 0.114] | 0.970 [0.924, 1.000] | 0.955 [0.886, 1.000] | 0.000 [0.000, 0.000] | – | – |

n per metric: agent-policy@gemini-4-argon-medium: stale-first 44, stale@10 44, current@10 66, retired 44, lost 63, forgotten 0, history-named@10 0

## Lines (G1-G5)

| Arm | G1 | G2 | G3 | G4 | G5 |
| --- | --- | --- | --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 0.795 [0.659, 0.909] **confirmed** | 0.909 [0.818, 0.977] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | – |

G1: stale-first, flat minus arm (paired), line 0.3; G2: retired, line 0.7; G3: current@10, arm minus flat (paired), line -0.05; G4: lost, all current values (lower is better), line 0.05; G5: forgotten, line 0.9

## Audit of value matching, both ways (6.3, and the other way)

Flagged: up to 50 `retired` failures and 50 `lost` cases per cell (seed 20261106; cases the tier-1 audit judged keep their verdict). More than 20% matching errors in either: that cell's lines are reported as unreliable (PLAN.md section 6). The other way: 15 updates the matcher counts as retired, and up to 20 values the frozen matcher called lost that it keeps. The corrected values remove the flagged matching errors and add the misses at the sampled share; they are not lines.

| Cell | `retired` errors | `lost` errors | Lines | Missed in passes | Wrong in flips | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 3 / 4 (75%) | – | **unreliable** | 0 / 15 (0%) | – | 0.909 / 0.977 | 0.000 / 0.000 |

## By group

### mab-sh/conflict

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 44 | 0.000 [0.000, 0.000] | 0.023 [0.000, 0.068] | 0.955 [0.886, 1.000] |
| flat | 44 | 0.795 [0.659, 0.909] | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] |
| oracle | 44 | 0.000 [0.000, 0.000] | 0.045 [0.000, 0.114] | 0.955 [0.886, 1.000] |

### mab-sh/other

| Arm | n | current@10 |
| --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 22 | 1.000 [1.000, 1.000] |
| flat | 22 | 1.000 [1.000, 1.000] |
| oracle | 22 | 1.000 [1.000, 1.000] |

### mab/conflict

| Arm | n | retired |
| --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 44 | 0.909 [0.818, 0.977] |
| flat | 44 | 0.000 [0.000, 0.000] |
| oracle | 44 | 0.955 [0.886, 1.000] |

### mab/fact

| Arm | n | lost |
| --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] |
| flat | 63 | 0.000 [0.000, 0.000] |
| oracle | 63 | 0.000 [0.000, 0.000] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-policy@gemini-4-argon-medium | 1 (0) | 231 | 18.41 (18, 31) | create 2309 | 837 / 4 | 4 | 0 | 0 (0) | 0 (0) | 0 | 91.53 (23756.5) | 2309.0 | 5.28M + 10.12M / 0.59M (0.04M) |
| flat | 1 (0) | 231 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.086 (19.9) | 2310.0 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 1 (0) | 231 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.096 (25.2) | 2310.0 | 0.00M + 0.00M / 0.00M (0.00M) |
