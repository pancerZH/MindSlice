# Run `tier1`

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 0.987 [0.968, 1.000] | 0.833 [0.787, 0.876] | 0.012 [0.008, 0.016] | 1.000 [1.000, 1.000] | 0.976 [0.949, 0.996] |
| agent-overlay@gemini-4-argon-medium | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 1.000 [1.000, 1.000] | 0.934 [0.903, 0.961] | 0.002 [0.000, 0.004] | 0.961 [0.908, 1.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 0.956 [0.924, 0.981] | 0.756 [0.702, 0.806] | 0.079 [0.069, 0.090] | 0.987 [0.961, 1.000] | 0.953 [0.918, 0.984] |
| agent-policy@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.019 [0.000, 0.045] | 1.000 [1.000, 1.000] | 0.857 [0.814, 0.895] | 0.007 [0.004, 0.010] | 0.987 [0.961, 1.000] | 0.973 [0.942, 0.996] |
| flat | 0.327 [0.256, 0.404] | 0.936 [0.891, 0.968] | 0.968 [0.937, 0.994] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.902 [0.862, 0.938] |
| oracle | 0.006 [0.000, 0.019] | 0.006 [0.000, 0.019] | 0.968 [0.937, 0.994] | 0.891 [0.849, 0.926] | 0.000 [0.000, 0.000] | 0.921 [0.855, 0.974] | 1.000 [1.000, 1.000] |

n per metric: agent-default@gemini-4-argon-medium: stale-first 156, stale@10 156, current@10 158, retired 258, lost 2803, forgotten 76, history-named@10 92

## Lines (G1-G5)

| Arm | G1 | G2 | G3 | G4 | G5 |
| --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 0.321 [0.244, 0.397] **point pass** | 0.833 [0.787, 0.876] **confirmed** | 0.019 [-0.013, 0.051] **confirmed** | 0.012 [0.008, 0.016] **confirmed** | 1.000 [1.000, 1.000] **confirmed** |
| agent-overlay@gemini-4-argon-medium | 0.321 [0.250, 0.397] **point pass** | 0.934 [0.903, 0.961] **confirmed** | 0.032 [0.006, 0.063] **confirmed** | 0.002 [0.000, 0.004] **confirmed** | 0.961 [0.908, 1.000] **confirmed** |
| agent-policy@gemini-3.8-flash-medium | 0.321 [0.250, 0.397] **point pass** | 0.756 [0.702, 0.806] **confirmed** | -0.013 [-0.057, 0.032] **point pass** | 0.079 [0.069, 0.090] **miss** | 0.987 [0.961, 1.000] **confirmed** |
| agent-policy@gemini-4-argon-medium | 0.327 [0.256, 0.404] **point pass** | 0.857 [0.814, 0.895] **confirmed** | 0.032 [0.006, 0.063] **confirmed** | 0.007 [0.004, 0.010] **confirmed** | 0.987 [0.961, 1.000] **confirmed** |

G1: stale-first, flat minus arm (paired), line 0.3; G2: retired, line 0.7; G3: current@10, arm minus flat (paired), line -0.05; G4: lost, all current values (lower is better), line 0.05; G5: forgotten, line 0.9

## Audit of value matching (6.3)

Each `retired` failure and `lost` case (all of them when fewer than 50, else a fixed sample, seed 20261106) judged from the workspace as it was at the judgment point. More than 20% matching errors in either sample: that cell's lines are reported as unreliable (PLAN.md section 6). The corrected values count the matching errors as passes (exact when every case was judged); they are not lines.

| Cell | `retired` errors | `lost` errors | Lines | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 6 / 43 (14%) | 30 / 34 (88%) | **unreliable** | 0.833 / 0.857 | 0.012 / 0.001 |
| agent-overlay@gemini-4-argon-medium | 6 / 17 (35%) | 3 / 5 (60%) | **unreliable** | 0.934 / 0.957 | 0.002 / 0.001 |
| agent-policy@gemini-3.8-flash-medium | 8 / 50 (16%) | 50 / 50 (100%) | **unreliable** | 0.756 / 0.795 | 0.079 / 0.000 |
| agent-policy@gemini-4-argon-medium | 5 / 37 (14%) | 15 / 19 (79%) | **unreliable** | 0.857 / 0.876 | 0.007 / 0.001 |

## Paired comparisons

Mean difference over the units both cells scored, with the paired 95% interval.

| Comparison | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-policy minus agent-default (Argon) | -0.006 [-0.019, 0.000] | 0.000 [-0.026, 0.026] | 0.013 [0.000, 0.032] | 0.023 [-0.012, 0.058] | -0.005 [-0.009, -0.001] | -0.013 [-0.040, 0.000] | -0.004 [-0.040, 0.029] |
| agent-overlay minus agent-policy (Argon) | 0.006 [0.000, 0.019] | 0.000 [-0.026, 0.026] | 0.000 [0.000, 0.000] | 0.077 [0.039, 0.120] | -0.005 [-0.008, -0.002] | -0.026 [-0.079, 0.026] | 0.027 [0.004, 0.058] |
| Argon minus Flash (agent-policy) | -0.006 [-0.019, 0.000] | 0.000 [-0.026, 0.026] | 0.044 [0.019, 0.076] | 0.101 [0.058, 0.147] | -0.072 [-0.082, -0.063] | 0.000 [-0.040, 0.040] | 0.020 [-0.022, 0.060] |

## Run-to-run variance (agent-policy, main model)

20 fixed MEME episodes, 4 runs (tier 1 and the repeats); pooled value of each metric per run.

| Metric | n per run | Per run | Mean | SD | Range |
| --- | --- | --- | --- | --- | --- |
| stale-first | 32 | 0.000, 0.000, 0.000, 0.000 | 0.000 | 0.000 | 0.000-0.000 |
| stale@10 | 32 | 0.031, 0.031, 0.031, 0.000 | 0.023 | 0.016 | 0.000-0.031 |
| current@10 | 33 | 1.000, 1.000, 1.000, 1.000 | 1.000 | 0.000 | 1.000-1.000 |
| retired | 54 | 0.870, 0.907, 0.889, 0.907 | 0.893 | 0.018 | 0.870-0.907 |
| lost | 588 | 0.005, 0.009, 0.007, 0.005 | 0.006 | 0.002 | 0.005-0.009 |
| forgotten | 17 | 1.000, 1.000, 1.000, 1.000 | 1.000 | 0.000 | 1.000-1.000 |
| history-named@10 | 19 | 0.974, 0.974, 1.000, 0.974 | 0.980 | 0.013 | 0.974-1.000 |

## By group

### meme/Abs-hop1

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.832 [0.758, 0.895] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.663 [0.568, 0.758] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.105 [0.053, 0.168] |
| agent-policy@gemini-4-argon-medium | 95 | 0.579 [0.484, 0.674] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] |

### meme/Abs-hop2

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 29 | 0.931 [0.828, 1.000] |
| agent-overlay@gemini-4-argon-medium | 29 | 0.690 [0.517, 0.862] |
| agent-policy@gemini-3.8-flash-medium | 29 | 0.035 [0.000, 0.103] |
| agent-policy@gemini-4-argon-medium | 29 | 0.552 [0.379, 0.724] |
| flat | 29 | 1.000 [1.000, 1.000] |
| oracle | 29 | 0.000 [0.000, 0.000] |

### meme/Agg

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.640 [0.574, 0.704] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.805 [0.751, 0.853] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.663 [0.605, 0.719] |
| agent-policy@gemini-4-argon-medium | 95 | 0.623 [0.556, 0.688] |
| flat | 95 | 0.711 [0.651, 0.767] |
| oracle | 95 | 0.756 [0.700, 0.809] |

### meme/Cas-hop1

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.032 [0.000, 0.074] | 0.979 [0.947, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.021 [0.000, 0.053] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.011 [0.000, 0.032] | 0.032 [0.000, 0.074] | 0.937 [0.884, 0.979] |
| agent-policy@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.032 [0.000, 0.074] | 1.000 [1.000, 1.000] |
| flat | 95 | 0.474 [0.368, 0.568] | 1.000 [1.000, 1.000] | 0.968 [0.926, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |

### meme/Cas-hop2

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.016 [0.000, 0.049] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.984 [0.952, 1.000] |
| agent-policy@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| flat | 63 | 0.098 [0.033, 0.180] | 0.836 [0.738, 0.918] | 0.968 [0.921, 1.000] |
| oracle | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |

### meme/Del

| Arm | n | stale@10 | forgotten |
| --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.042 [0.011, 0.084] | 0.961 [0.908, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.000 [0.000, 0.000] | 0.987 [0.961, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.987 [0.961, 1.000] |
| flat | 95 | 0.958 [0.916, 0.990] | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.021 [0.000, 0.053] | 0.921 [0.855, 0.974] |

### meme/ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.979 [0.947, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.632 [0.537, 0.726] |
| agent-policy@gemini-4-argon-medium | 95 | 0.968 [0.926, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/Tr

| Arm | n | history-named@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 92 | 0.976 [0.949, 0.996] |
| agent-overlay@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 92 | 0.953 [0.918, 0.984] |
| agent-policy@gemini-4-argon-medium | 92 | 0.973 [0.942, 0.996] |
| flat | 92 | 0.902 [0.862, 0.938] |
| oracle | 92 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.979 [0.947, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.990 [0.968, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.905 [0.842, 0.958] |
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
| agent-default@gemini-4-argon-medium | 95 | 0.990 [0.968, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.905 [0.842, 0.958] |
| agent-policy@gemini-4-argon-medium | 95 | 0.990 [0.968, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 61 | 0.984 [0.951, 1.000] |
| agent-policy@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| flat | 61 | 0.885 [0.803, 0.951] |
| oracle | 61 | 0.902 [0.820, 0.967] |

### meme/before-Del

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 76 | 0.987 [0.961, 1.000] |
| agent-overlay@gemini-4-argon-medium | 76 | 0.987 [0.961, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 76 | 0.974 [0.934, 1.000] |
| agent-policy@gemini-4-argon-medium | 76 | 0.987 [0.961, 1.000] |
| flat | 76 | 1.000 [1.000, 1.000] |
| oracle | 76 | 1.000 [1.000, 1.000] |

### meme/before-ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.979 [0.947, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.621 [0.526, 0.716] |
| agent-policy@gemini-4-argon-medium | 95 | 0.968 [0.926, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |

### meme/dependent

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 329 | 0.003 [0.000, 0.009] |
| agent-overlay@gemini-4-argon-medium | 329 | 0.003 [0.000, 0.009] |
| agent-policy@gemini-3.8-flash-medium | 329 | 0.052 [0.027, 0.076] |
| agent-policy@gemini-4-argon-medium | 329 | 0.003 [0.000, 0.009] |
| flat | 329 | 0.000 [0.000, 0.000] |
| oracle | 329 | 0.000 [0.000, 0.000] |

### meme/plain

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 2062 | 0.014 [0.009, 0.019] |
| agent-overlay@gemini-4-argon-medium | 2062 | 0.002 [0.001, 0.004] |
| agent-policy@gemini-3.8-flash-medium | 2062 | 0.093 [0.081, 0.105] |
| agent-policy@gemini-4-argon-medium | 2062 | 0.009 [0.005, 0.013] |
| flat | 2062 | 0.000 [0.000, 0.000] |
| oracle | 2062 | 0.000 [0.000, 0.000] |

### meme/root

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 | 0.821 [0.737, 0.895] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.916 [0.853, 0.968] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.737 [0.642, 0.821] |
| agent-policy@gemini-4-argon-medium | 95 | 0.884 [0.821, 0.947] |
| flat | 95 | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.895 [0.832, 0.958] |

### meme/rule

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 412 | 0.010 [0.002, 0.019] |
| agent-overlay@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 412 | 0.034 [0.017, 0.053] |
| agent-policy@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| flat | 412 | 0.000 [0.000, 0.000] |
| oracle | 412 | 0.000 [0.000, 0.000] |

### meme/tracking

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-4-argon-medium | 163 | 0.841 [0.785, 0.896] |
| agent-overlay@gemini-4-argon-medium | 163 | 0.945 [0.908, 0.976] |
| agent-policy@gemini-3.8-flash-medium | 163 | 0.767 [0.699, 0.834] |
| agent-policy@gemini-4-argon-medium | 163 | 0.841 [0.785, 0.896] |
| flat | 163 | 0.000 [0.000, 0.000] |
| oracle | 163 | 0.890 [0.841, 0.939] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-4-argon-medium | 95 (0) | 475 | 9.94 (8, 30) | append 79, create 1863, delete 93, replace 419 | 251 / 662 | 0 | 0 | 0 (0) | 0 (1) | 0 | 86.54 (50677.5) | 18.6 | 6.94M + 11.07M / 0.95M (0.19M) |
| agent-overlay@gemini-4-argon-medium | 95 (0) | 475 | 11.89 (11, 41) | append 1, create 933, delete 21, replace 333 | 1195 / 845 | 26 | 1 | 0 (1) | 0 (6) | 1 | 104.54 (59479.7) | 9.6 | 8.89M + 20.79M / 1.17M (0.52M) |
| agent-policy@gemini-3.8-flash-medium | 95 (0) | 475 | 14.64 (14, 34) | append 29, create 2000, delete 97, replace 46 | 306 / 613 | 11 | 0 | 0 (16) | 0 (6) | 0 | 83.53 (46297.9) | 20.0 | 47.06M + 67.87M / 4.68M (3.92M) |
| agent-policy@gemini-4-argon-medium | 95 (0) | 475 | 9.16 (9, 23) | append 37, create 1985, delete 95, replace 37 | 324 / 553 | 0 | 0 | 0 (0) | 0 (0) | 0 | 88.53 (48591.8) | 19.9 | 6.68M + 10.21M / 0.91M (0.26M) |
| flat | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.004 (2.3) | 25.9 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.008 (5.2) | 23.9 | 0.00M + 0.00M / 0.00M (0.00M) |
