# Run `tier1-v3`

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.779 [0.730, 0.826] | 0.004 [0.002, 0.007] | 0.989 [0.967, 1.000] | 0.996 [0.989, 1.000] |
| agent-overlay@gemini-4-argon-medium | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 1.000 [1.000, 1.000] | 0.922 [0.890, 0.950] | 0.003 [0.001, 0.005] | 0.946 [0.891, 0.989] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 0.000 [0.000, 0.000] | 0.013 [0.000, 0.032] | 1.000 [1.000, 1.000] | 0.676 [0.619, 0.730] | 0.004 [0.002, 0.007] | 0.978 [0.946, 1.000] | 0.996 [0.989, 1.000] |
| agent-policy@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.730 [0.676, 0.779] | 0.002 [0.001, 0.004] | 0.978 [0.946, 1.000] | 0.982 [0.961, 1.000] |
| flat | 0.327 [0.256, 0.404] | 0.936 [0.891, 0.968] | 0.968 [0.937, 0.994] | 0.000 [0.000, 0.000] | 0.001 [0.000, 0.002] | 0.000 [0.000, 0.000] | 0.907 [0.871, 0.939] |
| oracle | 0.006 [0.000, 0.019] | 0.006 [0.000, 0.019] | 0.968 [0.937, 0.994] | 0.875 [0.836, 0.911] | 0.001 [0.000, 0.002] | 0.924 [0.870, 0.967] | 1.000 [1.000, 1.000] |

n per metric: agent-default@gemini-4-argon-medium: stale-first 156, stale@10 156, current@10 158, retired 281, lost 3047, forgotten 92, history-named@10 93

## Lines (G1-G5)

| Arm | G1 | G2 | G3 | G4 | G5 |
| --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 0.327 [0.256, 0.404] **point pass** | 0.779 [0.730, 0.826] **confirmed** | 0.032 [0.006, 0.063] **confirmed** | 0.004 [0.002, 0.007] **confirmed** | 0.989 [0.967, 1.000] **confirmed** |
| agent-overlay@gemini-4-argon-medium | 0.321 [0.250, 0.397] **point pass** | 0.922 [0.890, 0.950] **confirmed** | 0.032 [0.006, 0.063] **confirmed** | 0.003 [0.001, 0.005] **confirmed** | 0.946 [0.891, 0.989] **point pass** |
| agent-policy@gemini-3.8-flash-medium | 0.327 [0.256, 0.404] **point pass** | 0.676 [0.619, 0.730] **miss** | 0.032 [0.006, 0.063] **confirmed** | 0.004 [0.002, 0.007] **confirmed** | 0.978 [0.946, 1.000] **confirmed** |
| agent-policy@gemini-4-argon-medium | 0.327 [0.256, 0.404] **point pass** | 0.730 [0.676, 0.779] **point pass** | 0.032 [0.006, 0.063] **confirmed** | 0.002 [0.001, 0.004] **confirmed** | 0.978 [0.946, 1.000] **confirmed** |

G1: stale-first, flat minus arm (paired), line 0.3; G2: retired, line 0.7; G3: current@10, arm minus flat (paired), line -0.05; G4: lost, all current values (lower is better), line 0.05; G5: forgotten, line 0.9

## Audit of value matching, both ways (6.3, and the other way)

Flagged: up to 50 `retired` failures and 50 `lost` cases per cell (seed 20261106; cases the tier-1 audit judged keep their verdict). More than 20% matching errors in either: that cell's lines are reported as unreliable (PLAN.md section 6). The other way: 15 updates the matcher counts as retired, and up to 20 values the frozen matcher called lost that it keeps. The corrected values remove the flagged matching errors and add the misses at the sampled share; they are not lines.

| Cell | `retired` errors | `lost` errors | Lines | Missed in passes | Wrong in flips | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 0 / 50 (0%) | 2 / 12 (17%) | reliable | 0 / 15 (0%) | – | 0.779 / 0.779 | 0.004 / 0.003 |
| agent-overlay@gemini-4-argon-medium | 0 / 22 (0%) | 0 / 8 (0%) | reliable | 0 / 15 (0%) | – | 0.922 / 0.922 | 0.003 / 0.003 |
| agent-policy@gemini-3.8-flash-medium | 1 / 50 (2%) | 2 / 13 (15%) | reliable | 0 / 15 (0%) | – | 0.676 / 0.683 | 0.004 / 0.004 |
| agent-policy@gemini-4-argon-medium | 0 / 50 (0%) | 2 / 7 (29%) | **unreliable** | 1 / 15 (7%) | – | 0.730 / 0.681 | 0.002 / 0.002 |

## Paired comparisons

Mean difference over the units both cells scored, with the paired 95% interval.

| Comparison | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-policy minus agent-default (Argon) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | -0.050 [-0.100, 0.004] | -0.002 [-0.004, 0.000] | -0.011 [-0.033, 0.000] | -0.014 [-0.036, 0.004] |
| agent-overlay minus agent-policy (Argon) | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 0.000 [0.000, 0.000] | 0.192 [0.146, 0.242] | 0.000 [-0.002, 0.003] | -0.033 [-0.098, 0.022] | 0.018 [0.000, 0.039] |
| Argon minus Flash (agent-policy) | 0.000 [0.000, 0.000] | -0.013 [-0.032, 0.000] | 0.000 [0.000, 0.000] | 0.053 [0.000, 0.107] | -0.002 [-0.004, -0.000] | 0.000 [-0.033, 0.033] | -0.014 [-0.036, 0.000] |

## Run-to-run variance (agent-policy, main model)

20 fixed MEME episodes, 4 runs (tier 1 and the repeats); pooled value of each metric per run.

| Metric | n per run | Per run | Mean | SD | Range |
| --- | --- | --- | --- | --- | --- |
| stale-first | 32 | 0.000, 0.000, 0.000, 0.000 | 0.000 | 0.000 | 0.000-0.000 |
| stale@10 | 32 | 0.000, 0.000, 0.000, 0.000 | 0.000 | 0.000 | 0.000-0.000 |
| current@10 | 33 | 1.000, 1.000, 1.000, 1.000 | 1.000 | 0.000 | 1.000-1.000 |
| retired | 60 | 0.733, 0.750, 0.783, 0.800 | 0.767 | 0.030 | 0.733-0.800 |
| lost | 646 | 0.003, 0.002, 0.002, 0.003 | 0.002 | 0.001 | 0.002-0.003 |
| forgotten | 19 | 1.000, 1.000, 1.000, 1.000 | 1.000 | 0.000 | 1.000-1.000 |
| history-named@10 | 20 | 0.983, 0.983, 1.000, 0.983 | 0.988 | 0.008 | 0.983-1.000 |

## By group

### meme/Abs-hop1

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.232 [0.147, 0.316] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.168 [0.095, 0.242] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.084 [0.032, 0.137] |
| agent-policy@gemini-4-argon-medium | 95 | 0.063 [0.021, 0.116] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 0.000 [0.000, 0.000] |

### meme/Abs-hop2

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 29 | 0.138 [0.035, 0.276] |
| agent-overlay@gemini-4-argon-medium | 29 | 0.379 [0.207, 0.552] |
| agent-policy@gemini-3.8-flash-medium | 29 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 29 | 0.103 [0.000, 0.241] |
| flat | 29 | 1.000 [1.000, 1.000] |
| oracle | 29 | 0.000 [0.000, 0.000] |

### meme/Agg

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.698 [0.646, 0.751] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.821 [0.772, 0.867] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.760 [0.709, 0.807] |
| agent-policy@gemini-4-argon-medium | 95 | 0.681 [0.618, 0.737] |
| flat | 95 | 0.740 [0.684, 0.789] |
| oracle | 95 | 0.775 [0.723, 0.825] |

### meme/Cas-hop1

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.021 [0.000, 0.053] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.000 [0.000, 0.000] | 0.021 [0.000, 0.053] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| flat | 95 | 0.474 [0.368, 0.568] | 1.000 [1.000, 1.000] | 0.968 [0.926, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |

### meme/Cas-hop2

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.016 [0.000, 0.049] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| flat | 63 | 0.098 [0.033, 0.180] | 0.836 [0.738, 0.918] | 0.968 [0.921, 1.000] |
| oracle | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |

### meme/Del

| Arm | n | stale@10 | forgotten |
| --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.989 [0.967, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.946 [0.891, 0.989] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.000 [0.000, 0.000] | 0.978 [0.946, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.978 [0.946, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.021 [0.000, 0.053] | 0.924 [0.870, 0.967] |

### meme/ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/Tr

| Arm | n | history-named@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 93 | 0.996 [0.989, 1.000] |
| agent-overlay@gemini-4-argon-medium | 93 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 93 | 0.996 [0.989, 1.000] |
| agent-policy@gemini-4-argon-medium | 93 | 0.982 [0.961, 1.000] |
| flat | 93 | 0.907 [0.871, 0.939] |
| oracle | 93 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.979 [0.947, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.990 [0.968, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 29 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 29 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 29 | 0.966 [0.897, 1.000] |
| agent-policy@gemini-4-argon-medium | 29 | 1.000 [1.000, 1.000] |
| flat | 29 | 0.966 [0.897, 1.000] |
| oracle | 29 | 0.966 [0.897, 1.000] |

### meme/before-Cas-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 61 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| flat | 61 | 0.885 [0.803, 0.951] |
| oracle | 61 | 0.902 [0.820, 0.967] |

### meme/before-Del

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 92 | 0.989 [0.967, 1.000] |
| agent-policy@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |
| flat | 92 | 1.000 [1.000, 1.000] |
| oracle | 92 | 1.000 [1.000, 1.000] |

### meme/before-ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/dependent

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 329 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 329 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 329 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 329 | 0.000 [0.000, 0.000] |
| flat | 329 | 0.000 [0.000, 0.000] |
| oracle | 329 | 0.000 [0.000, 0.000] |

### meme/plain

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 2306 | 0.005 [0.003, 0.008] |
| agent-overlay@gemini-4-argon-medium | 2306 | 0.004 [0.001, 0.006] |
| agent-policy@gemini-3.8-flash-medium | 2306 | 0.006 [0.003, 0.009] |
| agent-policy@gemini-4-argon-medium | 2306 | 0.003 [0.001, 0.006] |
| flat | 2306 | 0.001 [0.000, 0.003] |
| oracle | 2306 | 0.001 [0.000, 0.003] |

### meme/root

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.832 [0.758, 0.905] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.990 [0.968, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.737 [0.653, 0.821] |
| agent-policy@gemini-4-argon-medium | 95 | 0.884 [0.821, 0.937] |
| flat | 95 | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.926 [0.874, 0.979] |

### meme/rule

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 412 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| flat | 412 | 0.000 [0.000, 0.000] |
| oracle | 412 | 0.000 [0.000, 0.000] |

### meme/tracking

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 186 | 0.753 [0.688, 0.812] |
| agent-overlay@gemini-4-argon-medium | 186 | 0.887 [0.844, 0.930] |
| agent-policy@gemini-3.8-flash-medium | 186 | 0.645 [0.575, 0.715] |
| agent-policy@gemini-4-argon-medium | 186 | 0.650 [0.586, 0.720] |
| flat | 186 | 0.000 [0.000, 0.000] |
| oracle | 186 | 0.850 [0.796, 0.898] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 (0) | 475 | 9.94 (8, 30) | append 79, create 1863, delete 93, replace 419 | 251 / 662 | 0 | 0 | 0 (0) | 0 (1) | 0 | 86.54 (50677.5) | 18.6 | 6.94M + 11.07M / 0.95M (0.19M) |
| agent-overlay@gemini-4-argon-medium | 95 (0) | 475 | 11.89 (11, 41) | append 1, create 933, delete 21, replace 333 | 1195 / 845 | 26 | 1 | 0 (1) | 0 (6) | 1 | 104.54 (59479.7) | 9.6 | 8.89M + 20.79M / 1.17M (0.52M) |
| agent-policy@gemini-3.8-flash-medium | 95 (0) | 475 | 14.64 (14, 34) | append 29, create 2000, delete 97, replace 46 | 306 / 613 | 11 | 0 | 0 (16) | 0 (6) | 0 | 83.53 (46297.9) | 20.0 | 47.06M + 67.87M / 4.68M (3.92M) |
| agent-policy@gemini-4-argon-medium | 95 (0) | 475 | 9.16 (9, 23) | append 37, create 1985, delete 95, replace 37 | 324 / 553 | 0 | 0 | 0 (0) | 0 (0) | 0 | 88.53 (48591.8) | 19.9 | 6.68M + 10.21M / 0.91M (0.26M) |
| flat | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.004 (2.3) | 25.9 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.008 (5.2) | 23.9 | 0.00M + 0.00M / 0.00M (0.00M) |
