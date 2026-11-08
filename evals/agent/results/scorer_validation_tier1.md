# Value-based vs card-level judgments (`gate1`)

Same first pages, two judges: card-level marks a result stale or current when it is the card holding the annotated turn (evals/external, Mode B); value-based when its text states the value (agent_test.md 6.1). `Disagree` counts questions scored by both whose 0/1 (or share) differs.

## flat

| Group | Metric | n (value / card) | Value-based | Card-level | Disagree | Examples |
| --- | --- | --- | --- | --- | --- | --- |
| mab-sh/conflict | stale-first | 44 / 44 | 0.795 [0.682, 0.909] | 0.795 [0.682, 0.909] | 0 | – |
| mab-sh/conflict | stale@10 | 44 / 44 | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] | 0 | – |
| mab-sh/conflict | current@10 | 44 / 44 | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] | 0 | – |
| mab-sh/other | current@10 | 22 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Abs-hop1 | stale@10 | 95 / 95 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0 | – |
| meme/Abs-hop2 | stale@10 | 29 / 30 | 1.000 [1.000, 1.000] | 0.967 [0.900, 1.000] | 0 | – |
| meme/Agg | current@10 | 95 / 0 | 0.711 [0.651, 0.767] | – | 0 | – |
| meme/Cas-hop1 | stale-first | 95 / 95 | 0.474 [0.368, 0.568] | 0.484 [0.379, 0.590] | 1 | sw_044/after1 |
| meme/Cas-hop1 | stale@10 | 95 / 95 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0 | – |
| meme/Cas-hop1 | current@10 | 95 / 95 | 0.968 [0.926, 1.000] | 0.968 [0.926, 1.000] | 0 | – |
| meme/Cas-hop2 | stale-first | 61 / 63 | 0.098 [0.033, 0.180] | 0.111 [0.048, 0.191] | 1 | pl_030/after2 |
| meme/Cas-hop2 | stale@10 | 61 / 63 | 0.836 [0.738, 0.918] | 0.825 [0.730, 0.905] | 1 | pl_030/after2 |
| meme/Cas-hop2 | current@10 | 63 / 63 | 0.968 [0.921, 1.000] | 0.968 [0.921, 1.000] | 0 | – |
| meme/Del | stale@10 | 95 / 95 | 0.958 [0.916, 0.990] | 1.000 [1.000, 1.000] | 4 | pl_019/after3, pl_021/after5, pl_044/after4 |
| meme/ER | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Tr | stale@10 | 0 / 95 | – | 0.000 [0.000, 0.000] | 0 | – |
| meme/Tr | history-named@10 | 92 / 93 | 0.902 [0.862, 0.938] | 0.889 [0.850, 0.925] | 14 | pl_006/after0, pl_008/after0, pl_018/after0 |
| meme/before-Abs-hop1 | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-Abs-hop2 | current@10 | 29 / 0 | 0.966 [0.897, 1.000] | – | 0 | – |
| meme/before-Cas-hop1 | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-Cas-hop2 | current@10 | 61 / 0 | 0.885 [0.803, 0.951] | – | 0 | – |
| meme/before-Del | current@10 | 76 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-ER | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |

## oracle

| Group | Metric | n (value / card) | Value-based | Card-level | Disagree | Examples |
| --- | --- | --- | --- | --- | --- | --- |
| mab-sh/conflict | stale-first | 44 / 44 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| mab-sh/conflict | stale@10 | 44 / 44 | 0.023 [0.000, 0.068] | 0.000 [0.000, 0.000] | 1 | factconsolidation_sh_32k_no5 |
| mab-sh/conflict | current@10 | 44 / 44 | 0.955 [0.886, 1.000] | 0.955 [0.886, 1.000] | 0 | – |
| mab-sh/other | current@10 | 22 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Abs-hop1 | stale@10 | 95 / 95 | 0.011 [0.000, 0.032] | 0.000 [0.000, 0.000] | 1 | sw_004/after2 |
| meme/Abs-hop2 | stale@10 | 29 / 30 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Agg | current@10 | 95 / 0 | 0.756 [0.700, 0.809] | – | 0 | – |
| meme/Cas-hop1 | stale-first | 95 / 95 | 0.011 [0.000, 0.032] | 0.000 [0.000, 0.000] | 1 | pl_026/after1 |
| meme/Cas-hop1 | stale@10 | 95 / 95 | 0.011 [0.000, 0.032] | 0.000 [0.000, 0.000] | 1 | pl_026/after1 |
| meme/Cas-hop1 | current@10 | 95 / 95 | 0.968 [0.926, 1.000] | 0.968 [0.926, 1.000] | 0 | – |
| meme/Cas-hop2 | stale-first | 61 / 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop2 | stale@10 | 61 / 63 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop2 | current@10 | 63 / 63 | 0.968 [0.921, 1.000] | 0.968 [0.921, 1.000] | 0 | – |
| meme/Del | stale@10 | 95 / 95 | 0.021 [0.000, 0.053] | 0.000 [0.000, 0.000] | 2 | pl_015/after3, pl_036/after3 |
| meme/ER | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Tr | stale@10 | 0 / 95 | – | 0.000 [0.000, 0.000] | 0 | – |
| meme/Tr | history-named@10 | 92 / 93 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0 | – |
| meme/before-Abs-hop1 | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-Abs-hop2 | current@10 | 29 / 0 | 0.966 [0.897, 1.000] | – | 0 | – |
| meme/before-Cas-hop1 | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-Cas-hop2 | current@10 | 61 / 0 | 0.902 [0.820, 0.967] | – | 0 | – |
| meme/before-Del | current@10 | 76 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-ER | current@10 | 95 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |

