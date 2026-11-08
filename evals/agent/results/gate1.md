# Gate 1: scripted agents through the MCP tools vs the harness's own arms

Each scripted agent drives a fresh workspace through `manifest` / `search` / `read` / `write` only. `disagree` counts units (questions, updates, values, deletions) whose judgment differs from the reference arm; the paired difference is scripted minus reference (pooled groups as for the lines).

## scripted-flat vs flat

| Metric | Units | Disagree | Scripted | Reference | Paired difference | First disagreements |
| --- | --- | --- | --- | --- | --- | --- |
| current@10 | 865 | 0 | 0.969 [0.942, 0.991] | 0.969 [0.942, 0.991] | 0.000 [0.000, 0.000] | – |
| forgotten | 76 | 0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – |
| history-named@10 | 92 | 0 | 0.902 [0.862, 0.938] | 0.902 [0.862, 0.938] | 0.000 [0.000, 0.000] | – |
| lost | 2866 | 0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – |
| retired | 302 | 0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – |
| stale-first | 200 | 0 | 0.430 [0.360, 0.500] | 0.430 [0.360, 0.500] | 0.000 [0.000, 0.000] | – |
| stale@10 | 419 | 0 | 0.940 [0.905, 0.970] | 0.940 [0.905, 0.970] | 0.000 [0.000, 0.000] | – |

## scripted-oracle vs oracle

| Metric | Units | Disagree | Scripted | Reference | Paired difference | First disagreements |
| --- | --- | --- | --- | --- | --- | --- |
| current@10 | 865 | 0 | 0.969 [0.942, 0.991] | 0.969 [0.942, 0.991] | 0.000 [0.000, 0.000] | – |
| forgotten | 76 | 0 | 0.921 [0.855, 0.974] | 0.921 [0.855, 0.974] | 0.000 [0.000, 0.000] | – |
| history-named@10 | 92 | 0 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | – |
| lost | 2866 | 0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – |
| retired | 302 | 0 | 0.904 [0.868, 0.937] | 0.904 [0.868, 0.937] | 0.000 [0.000, 0.000] | – |
| stale-first | 200 | 0 | 0.005 [0.000, 0.015] | 0.005 [0.000, 0.015] | 0.000 [0.000, 0.000] | – |
| stale@10 | 419 | 0 | 0.010 [0.000, 0.025] | 0.010 [0.000, 0.025] | 0.000 [0.000, 0.000] | – |

## scripted-overlay vs oracle

| Metric | Units | Disagree | Scripted | Reference | Paired difference | First disagreements |
| --- | --- | --- | --- | --- | --- | --- |
| current@10 | 865 | 12 | 0.969 [0.942, 0.991] | 0.969 [0.942, 0.991] | 0.000 [0.000, 0.000] | `meme-nofiller/pl_009|pl_009/after5`, `meme-nofiller/pl_010|pl_010/after4`, `meme-nofiller/pl_012|pl_012/after4` |
| forgotten | 76 | 0 | 0.921 [0.855, 0.974] | 0.921 [0.855, 0.974] | 0.000 [0.000, 0.000] | – |
| history-named@10 | 92 | 0 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | – |
| lost | 2866 | 0 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | – |
| retired | 302 | 0 | 0.904 [0.868, 0.937] | 0.904 [0.868, 0.937] | 0.000 [0.000, 0.000] | – |
| stale-first | 200 | 0 | 0.005 [0.000, 0.015] | 0.005 [0.000, 0.015] | 0.000 [0.000, 0.000] | – |
| stale@10 | 419 | 0 | 0.010 [0.000, 0.025] | 0.010 [0.000, 0.025] | 0.000 [0.000, 0.000] | – |

Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 replicates, seed 20261106); differences are paired by unit.

## Pooled

| Arm | stale-first | stale@10 | current@10 | retired | lost | forgotten | history-named@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| flat | 0.430 [0.360, 0.500] | 0.940 [0.905, 0.970] | 0.969 [0.942, 0.991] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.902 [0.862, 0.938] |
| oracle | 0.005 [0.000, 0.015] | 0.010 [0.000, 0.025] | 0.969 [0.942, 0.991] | 0.904 [0.868, 0.937] | 0.000 [0.000, 0.000] | 0.921 [0.855, 0.974] | 1.000 [1.000, 1.000] |
| scripted-flat | 0.430 [0.360, 0.500] | 0.940 [0.905, 0.970] | 0.969 [0.942, 0.991] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.902 [0.862, 0.938] |
| scripted-oracle | 0.005 [0.000, 0.015] | 0.010 [0.000, 0.025] | 0.969 [0.942, 0.991] | 0.904 [0.868, 0.937] | 0.000 [0.000, 0.000] | 0.921 [0.855, 0.974] | 1.000 [1.000, 1.000] |
| scripted-overlay | 0.005 [0.000, 0.015] | 0.010 [0.000, 0.025] | 0.969 [0.942, 0.991] | 0.904 [0.868, 0.937] | 0.000 [0.000, 0.000] | 0.921 [0.855, 0.974] | 1.000 [1.000, 1.000] |

n per metric: flat: stale-first 200, stale@10 200, current@10 224, retired 302, lost 2866, forgotten 76, history-named@10 92

## Lines (G1-G5)

| Arm | G1 | G2 | G3 | G4 | G5 |
| --- | --- | --- | --- | --- | --- |
| oracle | 0.425 [0.355, 0.495] **confirmed** | 0.904 [0.868, 0.937] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.921 [0.855, 0.974] **point pass** |
| scripted-flat | 0.000 [0.000, 0.000] **miss** | 0.000 [0.000, 0.000] **miss** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **miss** |
| scripted-oracle | 0.425 [0.355, 0.495] **confirmed** | 0.904 [0.868, 0.937] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.921 [0.855, 0.974] **point pass** |
| scripted-overlay | 0.425 [0.355, 0.495] **confirmed** | 0.904 [0.868, 0.937] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | 0.921 [0.855, 0.974] **point pass** |

G1: stale-first, flat minus arm (paired), line 0.3; G2: retired, line 0.7; G3: current@10, arm minus flat (paired), line -0.05; G4: lost, all current values (lower is better), line 0.05; G5: forgotten, line 0.9

## By group

### mab-sh/conflict

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| flat | 44 | 0.795 [0.659, 0.909] | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] |
| oracle | 44 | 0.000 [0.000, 0.000] | 0.023 [0.000, 0.068] | 0.955 [0.886, 1.000] |
| scripted-flat | 44 | 0.795 [0.659, 0.909] | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] |
| scripted-oracle | 44 | 0.000 [0.000, 0.000] | 0.023 [0.000, 0.068] | 0.955 [0.886, 1.000] |
| scripted-overlay | 44 | 0.000 [0.000, 0.000] | 0.023 [0.000, 0.068] | 0.955 [0.886, 1.000] |

### mab-sh/other

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 22 | 1.000 [1.000, 1.000] |
| oracle | 22 | 1.000 [1.000, 1.000] |
| scripted-flat | 22 | 1.000 [1.000, 1.000] |
| scripted-oracle | 22 | 1.000 [1.000, 1.000] |
| scripted-overlay | 22 | 1.000 [1.000, 1.000] |

### mab/conflict

| Arm | n | retired |
| --- | --- | --- |
| flat | 44 | 0.000 [0.000, 0.000] |
| oracle | 44 | 0.977 [0.932, 1.000] |
| scripted-flat | 44 | 0.000 [0.000, 0.000] |
| scripted-oracle | 44 | 0.977 [0.932, 1.000] |
| scripted-overlay | 44 | 0.977 [0.932, 1.000] |

### mab/fact

| Arm | n | lost |
| --- | --- | --- |
| flat | 63 | 0.000 [0.000, 0.000] |
| oracle | 63 | 0.000 [0.000, 0.000] |
| scripted-flat | 63 | 0.000 [0.000, 0.000] |
| scripted-oracle | 63 | 0.000 [0.000, 0.000] |
| scripted-overlay | 63 | 0.000 [0.000, 0.000] |

### meme/Abs-hop1

| Arm | n | stale@10 |
| --- | --- | --- |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] |
| scripted-flat | 95 | 1.000 [1.000, 1.000] |
| scripted-oracle | 95 | 0.011 [0.000, 0.032] |
| scripted-overlay | 95 | 0.011 [0.000, 0.032] |

### meme/Abs-hop2

| Arm | n | stale@10 |
| --- | --- | --- |
| flat | 29 | 1.000 [1.000, 1.000] |
| oracle | 29 | 0.000 [0.000, 0.000] |
| scripted-flat | 29 | 1.000 [1.000, 1.000] |
| scripted-oracle | 29 | 0.000 [0.000, 0.000] |
| scripted-overlay | 29 | 0.000 [0.000, 0.000] |

### meme/Agg

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 95 | 0.711 [0.651, 0.767] |
| oracle | 95 | 0.756 [0.700, 0.809] |
| scripted-flat | 95 | 0.711 [0.651, 0.767] |
| scripted-oracle | 95 | 0.756 [0.700, 0.809] |
| scripted-overlay | 95 | 0.733 [0.677, 0.788] |

### meme/Cas-hop1

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| flat | 95 | 0.474 [0.368, 0.568] | 1.000 [1.000, 1.000] | 0.968 [0.926, 1.000] |
| oracle | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |
| scripted-flat | 95 | 0.474 [0.368, 0.568] | 1.000 [1.000, 1.000] | 0.968 [0.926, 1.000] |
| scripted-oracle | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |
| scripted-overlay | 95 | 0.011 [0.000, 0.032] | 0.011 [0.000, 0.032] | 0.968 [0.926, 1.000] |

### meme/Cas-hop2

| Arm | n | stale-first | stale@10 | current@10 |
| --- | --- | --- | --- | --- |
| flat | 63 | 0.098 [0.033, 0.180] | 0.836 [0.738, 0.918] | 0.968 [0.921, 1.000] |
| oracle | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |
| scripted-flat | 63 | 0.098 [0.033, 0.180] | 0.836 [0.738, 0.918] | 0.968 [0.921, 1.000] |
| scripted-oracle | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |
| scripted-overlay | 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.968 [0.921, 1.000] |

### meme/Del

| Arm | n | stale@10 | forgotten |
| --- | --- | --- | --- |
| flat | 95 | 0.958 [0.916, 0.990] | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.021 [0.000, 0.053] | 0.921 [0.855, 0.974] |
| scripted-flat | 95 | 0.958 [0.916, 0.990] | 0.000 [0.000, 0.000] |
| scripted-oracle | 95 | 0.021 [0.000, 0.053] | 0.921 [0.855, 0.974] |
| scripted-overlay | 95 | 0.021 [0.000, 0.053] | 0.921 [0.855, 0.974] |

### meme/ER

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-flat | 95 | 1.000 [1.000, 1.000] |
| scripted-oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-overlay | 95 | 1.000 [1.000, 1.000] |

### meme/Tr

| Arm | n | history-named@10 |
| --- | --- | --- |
| flat | 92 | 0.902 [0.862, 0.938] |
| oracle | 92 | 1.000 [1.000, 1.000] |
| scripted-flat | 92 | 0.902 [0.862, 0.938] |
| scripted-oracle | 92 | 1.000 [1.000, 1.000] |
| scripted-overlay | 92 | 1.000 [1.000, 1.000] |

### meme/before-Abs-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-flat | 95 | 1.000 [1.000, 1.000] |
| scripted-oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-overlay | 95 | 0.990 [0.968, 1.000] |

### meme/before-Abs-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 29 | 0.966 [0.897, 1.000] |
| oracle | 29 | 0.966 [0.897, 1.000] |
| scripted-flat | 29 | 0.966 [0.897, 1.000] |
| scripted-oracle | 29 | 0.966 [0.897, 1.000] |
| scripted-overlay | 29 | 0.966 [0.897, 1.000] |

### meme/before-Cas-hop1

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-flat | 95 | 1.000 [1.000, 1.000] |
| scripted-oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-overlay | 95 | 1.000 [1.000, 1.000] |

### meme/before-Cas-hop2

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 61 | 0.885 [0.803, 0.951] |
| oracle | 61 | 0.902 [0.820, 0.967] |
| scripted-flat | 61 | 0.885 [0.803, 0.951] |
| scripted-oracle | 61 | 0.902 [0.820, 0.967] |
| scripted-overlay | 61 | 0.902 [0.820, 0.967] |

### meme/before-Del

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 76 | 1.000 [1.000, 1.000] |
| oracle | 76 | 1.000 [1.000, 1.000] |
| scripted-flat | 76 | 1.000 [1.000, 1.000] |
| scripted-oracle | 76 | 1.000 [1.000, 1.000] |
| scripted-overlay | 76 | 1.000 [1.000, 1.000] |

### meme/before-ER

| Arm | n | current@10 |
| --- | --- | --- |
| flat | 95 | 1.000 [1.000, 1.000] |
| oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-flat | 95 | 1.000 [1.000, 1.000] |
| scripted-oracle | 95 | 1.000 [1.000, 1.000] |
| scripted-overlay | 95 | 1.000 [1.000, 1.000] |

### meme/dependent

| Arm | n | lost |
| --- | --- | --- |
| flat | 329 | 0.000 [0.000, 0.000] |
| oracle | 329 | 0.000 [0.000, 0.000] |
| scripted-flat | 329 | 0.000 [0.000, 0.000] |
| scripted-oracle | 329 | 0.000 [0.000, 0.000] |
| scripted-overlay | 329 | 0.000 [0.000, 0.000] |

### meme/plain

| Arm | n | lost |
| --- | --- | --- |
| flat | 2062 | 0.000 [0.000, 0.000] |
| oracle | 2062 | 0.000 [0.000, 0.000] |
| scripted-flat | 2062 | 0.000 [0.000, 0.000] |
| scripted-oracle | 2062 | 0.000 [0.000, 0.000] |
| scripted-overlay | 2062 | 0.000 [0.000, 0.000] |

### meme/root

| Arm | n | retired |
| --- | --- | --- |
| flat | 95 | 0.000 [0.000, 0.000] |
| oracle | 95 | 0.895 [0.832, 0.958] |
| scripted-flat | 95 | 0.000 [0.000, 0.000] |
| scripted-oracle | 95 | 0.895 [0.832, 0.958] |
| scripted-overlay | 95 | 0.895 [0.832, 0.958] |

### meme/rule

| Arm | n | lost |
| --- | --- | --- |
| flat | 412 | 0.000 [0.000, 0.000] |
| oracle | 412 | 0.000 [0.000, 0.000] |
| scripted-flat | 412 | 0.000 [0.000, 0.000] |
| scripted-oracle | 412 | 0.000 [0.000, 0.000] |
| scripted-overlay | 412 | 0.000 [0.000, 0.000] |

### meme/tracking

| Arm | n | retired |
| --- | --- | --- |
| flat | 163 | 0.000 [0.000, 0.000] |
| oracle | 163 | 0.890 [0.841, 0.939] |
| scripted-flat | 163 | 0.000 [0.000, 0.000] |
| scripted-oracle | 163 | 0.890 [0.841, 0.939] |
| scripted-overlay | 163 | 0.890 [0.841, 0.939] |

## Telemetry

| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | Tool errors | Cap hits | Non-MCP calls run (denied) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flat | 96 (0) | 706 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 | 0.006 (22.2) | 49.7 | 0.00M + 0.00M / 0.00M (0.00M) |
| oracle | 96 (0) | 706 | 0.0 (0, 0) | – | 0 / 0 | 0 | 0 | 0 (0) | 0 | 0.011 (30.4) | 47.7 | 0.00M + 0.00M / 0.00M (0.00M) |
| scripted-flat | 96 (0) | 706 | 6.76 (6, 11) | create 4771 | 0 / 0 | 0 | 0 | 0 (0) | 0 | 0.022 (205.0) | 49.7 | 0.00M + 0.00M / 0.00M (0.00M) |
| scripted-oracle | 96 (0) | 706 | 6.76 (6, 11) | create 4676, delete 96 | 335 / 533 | 0 | 0 | 0 (0) | 0 | 0.022 (205.0) | 47.7 | 0.00M + 0.00M / 0.00M (0.00M) |
| scripted-overlay | 96 (0) | 706 | 1.35 (1, 9) | create 952 | 952 / 533 | 0 | 0 | 0 (0) | 0 | 0.004 (10.8) | 9.9 | 0.00M + 0.00M / 0.00M (0.00M) |

