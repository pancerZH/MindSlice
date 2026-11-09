# Run `tier1-qwen-v3`

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 0.070 [0.032, 0.109] | 0.551 [0.468, 0.628] | 0.994 [0.981, 1.000] | 0.392 [0.335, 0.452] | 0.001 [0.000, 0.002] | 0.315 [0.228, 0.413] | 0.989 [0.975, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 0.026 [0.006, 0.051] | 0.211 [0.147, 0.276] | 1.000 [1.000, 1.000] | 0.566 [0.505, 0.623] | 0.004 [0.002, 0.007] | 0.609 [0.511, 0.707] | 0.996 [0.989, 1.000] |
| flat | 0.327 [0.256, 0.404] | 0.936 [0.891, 0.968] | 0.968 [0.937, 0.994] | 0.000 [0.000, 0.000] | 0.001 [0.000, 0.002] | 0.000 [0.000, 0.000] | 0.907 [0.871, 0.939] |
| oracle | 0.006 [0.000, 0.019] | 0.006 [0.000, 0.019] | 0.968 [0.937, 0.994] | 0.875 [0.836, 0.911] | 0.001 [0.000, 0.002] | 0.924 [0.870, 0.967] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.730 [0.676, 0.779] | 0.002 [0.001, 0.004] | 0.978 [0.946, 1.000] | 0.982 [0.961, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 0.000 [0.000, 0.000] | 0.013 [0.000, 0.032] | 1.000 [1.000, 1.000] | 0.676 [0.619, 0.730] | 0.004 [0.002, 0.007] | 0.978 [0.946, 1.000] | 0.996 [0.989, 1.000] |
| agent-overlay@gemini-4-argon-medium | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 1.000 [1.000, 1.000] | 0.922 [0.890, 0.950] | 0.003 [0.001, 0.005] | 0.946 [0.891, 0.989] | 1.000 [1.000, 1.000] |

n per metric: agent-overlay@qwen3.8-flash-next-iq3_s: stale-first 156, stale@10 156, current@10 158, retired 281, lost 3047, forgotten 92, history-named@10 93

## Lines (G1-G5)

| Arm | G1 | G2 | G3 | G4 | G5 |
| --- | --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 0.256 [0.179, 0.327] **miss** | 0.392 [0.335, 0.452] **miss** | 0.025 [0.006, 0.051] **confirmed** | 0.001 [0.000, 0.002] **confirmed** | 0.315 [0.228, 0.413] **miss** |
| agent-policy@qwen3.8-flash-next-iq3_s | 0.301 [0.224, 0.385] **point pass** | 0.566 [0.505, 0.623] **miss** | 0.032 [0.006, 0.063] **confirmed** | 0.004 [0.002, 0.007] **confirmed** | 0.609 [0.511, 0.707] **miss** |
| agent-policy@gemini-4-argon-medium | 0.327 [0.256, 0.404] **point pass** | 0.730 [0.676, 0.779] **point pass** | 0.032 [0.006, 0.063] **confirmed** | 0.002 [0.001, 0.004] **confirmed** | 0.978 [0.946, 1.000] **confirmed** |
| agent-policy@gemini-3.8-flash-medium | 0.327 [0.256, 0.404] **point pass** | 0.676 [0.619, 0.730] **miss** | 0.032 [0.006, 0.063] **confirmed** | 0.004 [0.002, 0.007] **confirmed** | 0.978 [0.946, 1.000] **confirmed** |
| agent-overlay@gemini-4-argon-medium | 0.321 [0.250, 0.397] **point pass** | 0.922 [0.890, 0.950] **confirmed** | 0.032 [0.006, 0.063] **confirmed** | 0.003 [0.001, 0.005] **confirmed** | 0.946 [0.891, 0.989] **point pass** |

G1: stale-first, flat minus arm (paired), line 0.3; G2: retired, line 0.7; G3: current@10, arm minus flat (paired), line -0.05; G4: lost, all current values (lower is better), line 0.05; G5: forgotten, line 0.9

## Audit of value matching, both ways (6.3, and the other way)

Flagged: up to 50 `retired` failures and 50 `lost` cases per cell (seed 20261106; cases the tier-1 audit judged keep their verdict). More than 20% matching errors in either: that cell's lines are reported as unreliable (PLAN.md section 6). The other way: 15 updates the matcher counts as retired, and up to 20 values the frozen matcher called lost that it keeps. The corrected values remove the flagged matching errors and add the misses at the sampled share; they are not lines.

| Cell | `retired` errors | `lost` errors | Lines | Missed in passes | Wrong in flips | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 1 / 50 (2%) | 0 / 3 (0%) | reliable | 2 / 15 (13%) | – | 0.392 / 0.352 | 0.001 / 0.001 |
| agent-policy@qwen3.8-flash-next-iq3_s | 4 / 50 (8%) | 4 / 13 (31%) | **unreliable** | 0 / 15 (0%) | – | 0.566 / 0.601 | 0.004 / 0.003 |

## Paired comparisons

Mean difference over the units both cells scored, with the paired 95% interval.

| Comparison | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-overlay minus agent-policy (Argon) | 0.006 [0.000, 0.019] | 0.019 [0.000, 0.045] | 0.000 [0.000, 0.000] | 0.192 [0.146, 0.242] | 0.000 [-0.002, 0.003] | -0.033 [-0.098, 0.022] | 0.018 [0.000, 0.039] |
| Argon minus Flash (agent-policy) | 0.000 [0.000, 0.000] | -0.013 [-0.032, 0.000] | 0.000 [0.000, 0.000] | 0.053 [0.000, 0.107] | -0.002 [-0.004, -0.000] | 0.000 [-0.033, 0.033] | -0.014 [-0.036, 0.000] |
| Qwen minus Argon (agent-policy) | 0.026 [0.006, 0.051] | 0.211 [0.147, 0.276] | 0.000 [0.000, 0.000] | -0.164 [-0.231, -0.103] | 0.002 [-0.000, 0.004] | -0.370 [-0.467, -0.272] | 0.014 [-0.004, 0.039] |
| Qwen minus Flash (agent-policy) | 0.026 [0.006, 0.051] | 0.199 [0.128, 0.269] | 0.000 [0.000, 0.000] | -0.110 [-0.171, -0.050] | 0.000 [-0.003, 0.003] | -0.370 [-0.478, -0.272] | 0.000 [-0.011, 0.011] |
| agent-overlay minus agent-policy (Qwen) | 0.045 [0.000, 0.096] | 0.340 [0.237, 0.442] | -0.006 [-0.019, 0.000] | -0.174 [-0.242, -0.107] | -0.003 [-0.006, -0.001] | -0.293 [-0.435, -0.163] | -0.007 [-0.021, 0.007] |

## By group

### meme/Abs-hop1

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 0.916 [0.853, 0.968] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.684 [0.590, 0.779] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 95 | 0.063 [0.021, 0.116] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.084 [0.032, 0.137] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.168 [0.095, 0.242] |

### meme/Abs-hop2

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 29 | 0.931 [0.828, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 29 | 0.759 [0.586, 0.897] |
| flat | 29 | 1.000 [1.000, 1.000] |
| oracle | 29 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 29 | 0.103 [0.000, 0.241] |
| agent-policy@gemini-3.8-flash-medium | 29 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 29 | 0.379 [0.207, 0.552] |

### meme/Agg

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 0.825 [0.772, 0.870] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.833 [0.786, 0.874] |
| flat | 95 | 0.740 [0.684, 0.789] |
| oracle | 95 | 0.775 [0.723, 0.825] |
| agent-policy@gemini-4-argon-medium | 95 | 0.681 [0.618, 0.737] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.760 [0.709, 0.807] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.821 [0.772, 0.867] |

### meme/Cas-hop1

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 0.105 [0.053, 0.179] | 0.579 [0.474, 0.674] | 0.990 [0.968, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.021 [0.000, 0.053] | 0.200 [0.126, 0.274] | 1.000 [1.000, 1.000] |
| flat | 95 | 0.474 [0.368, 0.568] | 1.000 [1.000, 1.000] | 0.968 [0.926, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.000 [0.000, 0.000] | 0.021 [0.000, 0.053] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.021 [0.000, 0.053] | 1.000 [1.000, 1.000] |

### meme/Cas-hop2

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 63 | 0.016 [0.000, 0.049] | 0.508 [0.393, 0.639] | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 63 | 0.033 [0.000, 0.082] | 0.230 [0.131, 0.328] | 1.000 [1.000, 1.000] |
| flat | 63 | 0.098 [0.033, 0.180] | 0.836 [0.738, 0.918] | 0.968 [0.921, 1.000] |
| oracle | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |
| agent-policy@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 63 | 0.000 [0.000, 0.000] | 0.016 [0.000, 0.049] | 1.000 [1.000, 1.000] |

### meme/Del

| Arm | n | stale@10 | forgotten |
| --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 0.653 [0.558, 0.747] | 0.315 [0.228, 0.413] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.274 [0.190, 0.368] | 0.609 [0.511, 0.707] |
| flat | 95 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.021 [0.000, 0.053] | 0.924 [0.870, 0.967] |
| agent-policy@gemini-4-argon-medium | 95 | 0.000 [0.000, 0.000] | 0.978 [0.946, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.000 [0.000, 0.000] | 0.978 [0.946, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.011 [0.000, 0.032] | 0.946 [0.891, 0.989] |

### meme/ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |

### meme/Tr

| Arm | n | history-named@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 93 | 0.989 [0.975, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 93 | 0.996 [0.989, 1.000] |
| flat | 93 | 0.907 [0.871, 0.939] |
| oracle | 93 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 93 | 0.982 [0.961, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 93 | 0.996 [0.989, 1.000] |
| agent-overlay@gemini-4-argon-medium | 93 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.990 [0.968, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.990 [0.968, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 29 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 29 | 1.000 [1.000, 1.000] |
| flat | 29 | 0.966 [0.897, 1.000] |
| oracle | 29 | 0.966 [0.897, 1.000] |
| agent-policy@gemini-4-argon-medium | 29 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 29 | 0.966 [0.897, 1.000] |
| agent-overlay@gemini-4-argon-medium | 29 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 61 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 61 | 1.000 [1.000, 1.000] |
| flat | 61 | 0.885 [0.803, 0.951] |
| oracle | 61 | 0.902 [0.820, 0.967] |
| agent-policy@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 61 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 61 | 1.000 [1.000, 1.000] |

### meme/before-Del

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 92 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 92 | 1.000 [1.000, 1.000] |
| flat | 92 | 1.000 [1.000, 1.000] |
| oracle | 92 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 92 | 0.989 [0.967, 1.000] |
| agent-overlay@gemini-4-argon-medium | 92 | 1.000 [1.000, 1.000] |

### meme/before-ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 1.000 [1.000, 1.000] |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 95 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 95 | 1.000 [1.000, 1.000] |

### meme/dependent

| Arm | n | lost |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 329 | 0.000 [0.000, 0.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 329 | 0.003 [0.000, 0.009] |
| flat | 329 | 0.000 [0.000, 0.000] |
| oracle | 329 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 329 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 329 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 329 | 0.000 [0.000, 0.000] |

### meme/plain

| Arm | n | lost |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 2306 | 0.001 [0.000, 0.003] |
| agent-policy@qwen3.8-flash-next-iq3_s | 2306 | 0.005 [0.003, 0.008] |
| flat | 2306 | 0.001 [0.000, 0.003] |
| oracle | 2306 | 0.001 [0.000, 0.003] |
| agent-policy@gemini-4-argon-medium | 2306 | 0.003 [0.001, 0.006] |
| agent-policy@gemini-3.8-flash-medium | 2306 | 0.006 [0.003, 0.009] |
| agent-overlay@gemini-4-argon-medium | 2306 | 0.004 [0.001, 0.006] |

### meme/root

| Arm | n | retired |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 | 0.221 [0.137, 0.305] |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 | 0.526 [0.432, 0.621] |
| flat | 95 | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.926 [0.874, 0.979] |
| agent-policy@gemini-4-argon-medium | 95 | 0.884 [0.821, 0.937] |
| agent-policy@gemini-3.8-flash-medium | 95 | 0.737 [0.653, 0.821] |
| agent-overlay@gemini-4-argon-medium | 95 | 0.990 [0.968, 1.000] |

### meme/rule

| Arm | n | lost |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 412 | 0.000 [0.000, 0.000] |
| agent-policy@qwen3.8-flash-next-iq3_s | 412 | 0.000 [0.000, 0.000] |
| flat | 412 | 0.000 [0.000, 0.000] |
| oracle | 412 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 412 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 412 | 0.000 [0.000, 0.000] |

### meme/tracking

| Arm | n | retired |
| --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 186 | 0.478 [0.409, 0.554] |
| agent-policy@qwen3.8-flash-next-iq3_s | 186 | 0.586 [0.516, 0.656] |
| flat | 186 | 0.000 [0.000, 0.000] |
| oracle | 186 | 0.850 [0.796, 0.898] |
| agent-policy@gemini-4-argon-medium | 186 | 0.650 [0.586, 0.720] |
| agent-policy@gemini-3.8-flash-medium | 186 | 0.645 [0.575, 0.715] |
| agent-overlay@gemini-4-argon-medium | 186 | 0.887 [0.844, 0.930] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-overlay@qwen3.8-flash-next-iq3_s | 95 (0) | 475 | 13.97 (13, 33) | append 428, create 2350, delete 105, replace 327 | 829 / 1214 | 61 | 0 | 0 (0) | 0 (0) | 98 | 60.63 (33540.1) | 23.5 | 6.13M + 41.16M / 2.47M (0.00M) |
| agent-policy@qwen3.8-flash-next-iq3_s | 95 (0) | 475 | 12.47 (12, 30) | append 472, create 2231, delete 101, replace 211 | 276 / 952 | 81 | 0 | 0 (0) | 0 (0) | 135 | 47.42 (25702.0) | 22.0 | 4.10M + 28.82M / 1.85M (0.00M) |
| flat | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.004 (2.3) | 25.9 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 95 (0) | 475 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.008 (5.2) | 23.9 | 0.00M + 0.00M / 0.00M (0.00M) |
| agent-policy@gemini-4-argon-medium | 95 (0) | 475 | 9.16 (9, 23) | append 37, create 1985, delete 95, replace 37 | 324 / 553 | 0 | 0 | 0 (0) | 0 (0) | 0 | 88.53 (48591.8) | 19.9 | 6.68M + 10.21M / 0.91M (0.26M) |
| agent-policy@gemini-3.8-flash-medium | 95 (0) | 475 | 14.64 (14, 34) | append 29, create 2000, delete 97, replace 46 | 306 / 613 | 11 | 0 | 0 (16) | 0 (6) | 0 | 83.53 (46297.9) | 20.0 | 47.06M + 67.87M / 4.68M (3.92M) |
| agent-overlay@gemini-4-argon-medium | 95 (0) | 475 | 11.89 (11, 41) | append 1, create 933, delete 21, replace 333 | 1195 / 845 | 26 | 1 | 0 (1) | 0 (6) | 1 | 104.54 (59479.7) | 9.6 | 8.89M + 20.79M / 1.17M (0.52M) |
