# Run `smoke-final`

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.966 [0.920, 1.000] | 0.922 [0.857, 0.974] | 0.060 [0.032, 0.093] | 1.000 [1.000, 1.000] | 0.933 [0.800, 1.000] |
| agent-default@gemini-4-argon-medium | 0.015 [0.000, 0.044] | 0.118 [0.044, 0.191] | 0.989 [0.966, 1.000] | 0.922 [0.857, 0.974] | 0.014 [0.000, 0.032] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 0.265 [0.162, 0.382] | 0.368 [0.250, 0.485] | 0.977 [0.943, 1.000] | 0.675 [0.571, 0.779] | 0.014 [0.000, 0.032] | 0.500 [0.000, 1.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.989 [0.966, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 0.015 [0.000, 0.044] | 0.015 [0.000, 0.044] | 0.966 [0.920, 1.000] | 0.896 [0.818, 0.961] | 0.032 [0.009, 0.056] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 0.000 [0.000, 0.000] | 0.044 [0.000, 0.103] | 0.989 [0.966, 1.000] | 0.935 [0.883, 0.987] | 0.005 [0.000, 0.014] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| flat | 0.706 [0.588, 0.824] | 0.985 [0.956, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.933 [0.800, 1.000] |
| oracle | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.922 [0.857, 0.974] | 0.000 [0.000, 0.000] | 0.750 [0.250, 1.000] | 1.000 [1.000, 1.000] |

n per metric: agent-default@gemini-3.8-flash-medium: stale-first 68, stale@10 68, current@10 88, retired 77, lost 216, forgotten 4, history-named@10 5

## By group

### mab-sh/conflict

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 62 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.984 [0.952, 1.000] |
| agent-default@gemini-4-argon-medium | 62 | 0.000 [0.000, 0.000] | 0.097 [0.032, 0.177] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 62 | 0.290 [0.177, 0.403] | 0.403 [0.290, 0.516] | 0.984 [0.952, 1.000] |
| agent-overlay@gemini-4-argon-medium | 62 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.984 [0.952, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 62 | 0.016 [0.000, 0.048] | 0.016 [0.000, 0.048] | 0.968 [0.919, 1.000] |
| agent-policy@gemini-4-argon-medium | 62 | 0.000 [0.000, 0.000] | 0.032 [0.000, 0.081] | 0.984 [0.952, 1.000] |
| flat | 62 | 0.726 [0.613, 0.839] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| oracle | 62 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |

### mab-sh/other

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 20 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 20 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 20 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 20 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 20 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 20 | 1.000 [1.000, 1.000] |
| flat | 20 | 1.000 [1.000, 1.000] |
| oracle | 20 | 1.000 [1.000, 1.000] |

### mab/conflict

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 62 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 62 | 0.968 [0.919, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 62 | 0.597 [0.484, 0.710] |
| agent-overlay@gemini-4-argon-medium | 62 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 62 | 0.984 [0.952, 1.000] |
| agent-policy@gemini-4-argon-medium | 62 | 0.968 [0.919, 1.000] |
| flat | 62 | 0.000 [0.000, 0.000] |
| oracle | 62 | 1.000 [1.000, 1.000] |

### mab/fact

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 82 | 0.000 [0.000, 0.000] |
| agent-default@gemini-4-argon-medium | 82 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-3.8-flash-medium | 82 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 82 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 82 | 0.012 [0.000, 0.037] |
| agent-policy@gemini-4-argon-medium | 82 | 0.000 [0.000, 0.000] |
| flat | 82 | 0.000 [0.000, 0.000] |
| oracle | 82 | 0.000 [0.000, 0.000] |

### meme/Abs-hop1

| Arm | n | stale@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.200 [0.000, 0.600] |
| agent-default@gemini-4-argon-medium | 5 | 0.600 [0.200, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 0.400 [0.000, 0.800] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.200 [0.000, 0.600] |
| agent-policy@gemini-4-argon-medium | 5 | 0.600 [0.200, 1.000] |
| flat | 5 | 1.000 [1.000, 1.000] |
| oracle | 5 | 0.000 [0.000, 0.000] |

### meme/Agg

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.667 [0.400, 0.933] |
| agent-default@gemini-4-argon-medium | 5 | 0.800 [0.667, 0.933] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 0.400 [0.133, 0.600] |
| agent-overlay@gemini-4-argon-medium | 5 | 0.533 [0.400, 0.667] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.600 [0.400, 0.800] |
| agent-policy@gemini-4-argon-medium | 5 | 0.667 [0.467, 0.867] |
| flat | 5 | 0.267 [0.133, 0.333] |
| oracle | 5 | 0.400 [0.333, 0.533] |

### meme/Cas-hop1

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.600 [0.200, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 0.200 [0.000, 0.600] | 0.400 [0.000, 0.800] | 0.800 [0.400, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.800 [0.400, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.800 [0.400, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 0.000 [0.000, 0.000] | 0.200 [0.000, 0.600] | 1.000 [1.000, 1.000] |
| flat | 5 | 0.600 [0.200, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| oracle | 5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |

### meme/Cas-hop2

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| flat | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| oracle | 1 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |

### meme/Del

| Arm | n | stale@10 | forgotten |
| --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 0.600 [0.200, 1.000] | 0.500 [0.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] |
| flat | 5 | 0.800 [0.400, 1.000] | 0.000 [0.000, 0.000] |
| oracle | 5 | 0.000 [0.000, 0.000] | 0.750 [0.250, 1.000] |

### meme/ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| flat | 5 | 1.000 [1.000, 1.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/Tr

| Arm | n | history-named@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.933 [0.800, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| flat | 5 | 0.933 [0.800, 1.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.600 [0.200, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 0.800 [0.400, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 0.800 [0.400, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.600 [0.200, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 0.800 [0.400, 1.000] |
| flat | 5 | 1.000 [1.000, 1.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| flat | 5 | 1.000 [1.000, 1.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 1 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 1 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 1 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 1 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 1 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 1 | 1.000 [1.000, 1.000] |
| flat | 1 | 0.000 [0.000, 0.000] |
| oracle | 1 | 0.000 [0.000, 0.000] |

### meme/before-Del

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 4 | 0.750 [0.250, 1.000] |
| agent-default@gemini-4-argon-medium | 4 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 4 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 4 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 4 | 0.750 [0.250, 1.000] |
| agent-policy@gemini-4-argon-medium | 4 | 1.000 [1.000, 1.000] |
| flat | 4 | 1.000 [1.000, 1.000] |
| oracle | 4 | 1.000 [1.000, 1.000] |

### meme/before-ER

| Arm | n | current@10 |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-default@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| flat | 5 | 1.000 [1.000, 1.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/dependent

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 12 | 0.167 [0.000, 0.417] |
| agent-default@gemini-4-argon-medium | 12 | 0.083 [0.000, 0.250] |
| agent-overlay@gemini-3.8-flash-medium | 12 | 0.083 [0.000, 0.250] |
| agent-overlay@gemini-4-argon-medium | 12 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 12 | 0.167 [0.000, 0.417] |
| agent-policy@gemini-4-argon-medium | 12 | 0.083 [0.000, 0.250] |
| flat | 12 | 0.000 [0.000, 0.000] |
| oracle | 12 | 0.000 [0.000, 0.000] |

### meme/plain

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 108 | 0.065 [0.018, 0.111] |
| agent-default@gemini-4-argon-medium | 108 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-3.8-flash-medium | 108 | 0.000 [0.000, 0.000] |
| agent-overlay@gemini-4-argon-medium | 108 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 108 | 0.018 [0.000, 0.046] |
| agent-policy@gemini-4-argon-medium | 108 | 0.000 [0.000, 0.000] |
| flat | 108 | 0.000 [0.000, 0.000] |
| oracle | 108 | 0.000 [0.000, 0.000] |

### meme/root

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 5 | 0.400 [0.000, 0.800] |
| agent-default@gemini-4-argon-medium | 5 | 0.600 [0.200, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 5 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 5 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 5 | 0.200 [0.000, 0.600] |
| agent-policy@gemini-4-argon-medium | 5 | 0.600 [0.200, 1.000] |
| flat | 5 | 0.000 [0.000, 0.000] |
| oracle | 5 | 1.000 [1.000, 1.000] |

### meme/rule

| Arm | n | lost |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 14 | 0.286 [0.071, 0.571] |
| agent-default@gemini-4-argon-medium | 14 | 0.143 [0.000, 0.357] |
| agent-overlay@gemini-3.8-flash-medium | 14 | 0.143 [0.000, 0.357] |
| agent-overlay@gemini-4-argon-medium | 14 | 0.000 [0.000, 0.000] |
| agent-policy@gemini-3.8-flash-medium | 14 | 0.143 [0.000, 0.357] |
| agent-policy@gemini-4-argon-medium | 14 | 0.000 [0.000, 0.000] |
| flat | 14 | 0.000 [0.000, 0.000] |
| oracle | 14 | 0.000 [0.000, 0.000] |

### meme/tracking

| Arm | n | retired |
| --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 10 | 0.700 [0.400, 1.000] |
| agent-default@gemini-4-argon-medium | 10 | 0.800 [0.500, 1.000] |
| agent-overlay@gemini-3.8-flash-medium | 10 | 1.000 [1.000, 1.000] |
| agent-overlay@gemini-4-argon-medium | 10 | 1.000 [1.000, 1.000] |
| agent-policy@gemini-3.8-flash-medium | 10 | 0.700 [0.400, 1.000] |
| agent-policy@gemini-4-argon-medium | 10 | 0.900 [0.700, 1.000] |
| flat | 10 | 0.000 [0.000, 0.000] |
| oracle | 10 | 0.400 [0.100, 0.700] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-default@gemini-3.8-flash-medium | 6 (0) | 71 | 23.11 (24, 40) | append 7, create 549, delete 5, replace 1 | 177 / 16 | 21 | 0 | 0 (2) | 0 (0) | 0 | 93.04 (6595.5) | 90.7 | 11.02M + 15.29M / 0.51M (0.37M) |
| agent-default@gemini-4-argon-medium | 6 (0) | 71 | 14.44 (15, 27) | append 5, create 396, delete 5, replace 157 | 23 / 22 | 0 | 0 | 0 (0) | 0 (0) | 0 | 83.52 (6647.9) | 65.2 | 1.16M + 1.83M / 0.16M (0.02M) |
| agent-overlay@gemini-3.8-flash-medium | 6 (0) | 71 | 28.89 (30, 44) | create 132, delete 3, replace 3 | 132 / 23 | 19 | 20 | 0 (4) | 0 (5) | 20 | 144.52 (10976.3) | 21.3 | 12.84M + 27.38M / 1.05M (0.93M) |
| agent-overlay@gemini-4-argon-medium | 6 (0) | 71 | 10.41 (11, 22) | append 3, create 212, delete 1, replace 6 | 216 / 36 | 6 | 0 | 0 (0) | 0 (0) | 0 | 75.53 (6584.3) | 35.2 | 1.22M + 2.29M / 0.12M (0.05M) |
| agent-policy@gemini-3.8-flash-medium | 6 (0) | 71 | 23.35 (24, 41) | append 3, create 553, delete 5, replace 4 | 179 / 20 | 21 | 4 | 0 (1) | 0 (1) | 4 | 94.04 (6680.2) | 91.3 | 11.38M + 15.60M / 0.52M (0.37M) |
| agent-policy@gemini-4-argon-medium | 6 (0) | 71 | 14.28 (14, 23) | create 551, delete 5, replace 2 | 176 / 17 | 0 | 0 | 0 (0) | 0 (0) | 0 | 76.03 (6718.5) | 91.0 | 1.16M + 1.88M / 0.16M (0.02M) |
| flat | 6 (0) | 71 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.01 (1.0) | 99.5 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 6 (0) | 71 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 (0) | 0 | 0.014 (2.6) | 97.8 | 0.00M + 0.00M / 0.00M (0.00M) |
