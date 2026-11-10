# Value-based vs card-level judgments (`external-compare`)

Same first pages, two judges: card-level marks a result stale or current when it is the card holding the annotated turn (evals/external, Mode B); value-based when its text states the value (agent_test.md 6.1). `Disagree` counts questions scored by both whose 0/1 (or share) differs.

## flat

| Group | Metric | n (value / card) | Value-based | Card-level | Disagree | Examples |
| --- | --- | --- | --- | --- | --- | --- |
| mab-sh/conflict | stale-first | 208 / 208 | 0.779 [0.721, 0.837] | 0.779 [0.721, 0.837] | 0 | – |
| mab-sh/conflict | stale@10 | 208 / 208 | 0.962 [0.933, 0.986] | 0.962 [0.933, 0.986] | 0 | – |
| mab-sh/conflict | current@10 | 208 / 208 | 0.966 [0.942, 0.990] | 0.966 [0.942, 0.990] | 0 | – |
| mab-sh/other | current@10 | 85 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Abs-hop1 | stale@10 | 100 / 100 | 0.990 [0.970, 1.000] | 0.990 [0.970, 1.000] | 0 | – |
| meme/Abs-hop2 | stale@10 | 29 / 30 | 0.931 [0.828, 1.000] | 0.900 [0.767, 1.000] | 0 | – |
| meme/Agg | current@10 | 100 / 0 | 0.385 [0.318, 0.452] | – | 0 | – |
| meme/Cas-hop1 | stale-first | 100 / 100 | 0.590 [0.500, 0.690] | 0.600 [0.500, 0.700] | 1 | sw_044/after1 |
| meme/Cas-hop1 | stale@10 | 100 / 100 | 0.960 [0.920, 0.990] | 0.960 [0.920, 0.990] | 0 | – |
| meme/Cas-hop1 | current@10 | 100 / 100 | 0.940 [0.890, 0.980] | 0.940 [0.890, 0.980] | 0 | – |
| meme/Cas-hop2 | stale-first | 62 / 64 | 0.161 [0.081, 0.258] | 0.172 [0.093, 0.266] | 1 | pl_030/after2 |
| meme/Cas-hop2 | stale@10 | 62 / 64 | 0.774 [0.677, 0.887] | 0.766 [0.656, 0.875] | 1 | pl_030/after2 |
| meme/Cas-hop2 | current@10 | 64 / 64 | 0.969 [0.922, 1.000] | 0.969 [0.922, 1.000] | 0 | – |
| meme/Del | stale@10 | 100 / 100 | 0.950 [0.900, 0.990] | 0.990 [0.970, 1.000] | 6 | pl_004/after3, pl_019/after3, pl_021/after5 |
| meme/ER | current@10 | 100 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Tr | stale@10 | 0 / 100 | – | 0.000 [0.000, 0.000] | 0 | – |
| meme/Tr | history-named@10 | 97 / 98 | 0.747 [0.682, 0.813] | 0.718 [0.646, 0.786] | 15 | pl_006/after0, pl_007/after0, pl_008/after0 |
| meme/before-Abs-hop1 | current@10 | 100 / 0 | 0.990 [0.970, 1.000] | – | 0 | – |
| meme/before-Abs-hop2 | current@10 | 29 / 0 | 0.966 [0.897, 1.000] | – | 0 | – |
| meme/before-Cas-hop1 | current@10 | 100 / 0 | 0.970 [0.930, 1.000] | – | 0 | – |
| meme/before-Cas-hop2 | current@10 | 62 / 0 | 0.806 [0.710, 0.903] | – | 0 | – |
| meme/before-Del | current@10 | 80 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-ER | current@10 | 100 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |

## oracle

| Group | Metric | n (value / card) | Value-based | Card-level | Disagree | Examples |
| --- | --- | --- | --- | --- | --- | --- |
| mab-sh/conflict | stale-first | 208 / 208 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| mab-sh/conflict | stale@10 | 208 / 208 | 0.038 [0.014, 0.062] | 0.000 [0.000, 0.000] | 8 | factconsolidation_sh_262k_no9, factconsolidation_sh_262k_no18, factconsolidation_sh_262k_no54 |
| mab-sh/conflict | current@10 | 208 / 208 | 0.966 [0.942, 0.990] | 0.966 [0.942, 0.990] | 0 | – |
| mab-sh/other | current@10 | 85 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Abs-hop1 | stale@10 | 100 / 100 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Abs-hop2 | stale@10 | 29 / 30 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Agg | current@10 | 100 / 0 | 0.393 [0.325, 0.463] | – | 0 | – |
| meme/Cas-hop1 | stale-first | 100 / 100 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop1 | stale@10 | 100 / 100 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop1 | current@10 | 100 / 100 | 0.940 [0.890, 0.980] | 0.940 [0.890, 0.980] | 0 | – |
| meme/Cas-hop2 | stale-first | 62 / 64 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop2 | stale@10 | 62 / 64 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0 | – |
| meme/Cas-hop2 | current@10 | 64 / 64 | 0.969 [0.922, 1.000] | 0.969 [0.922, 1.000] | 0 | – |
| meme/Del | stale@10 | 100 / 100 | 0.020 [0.000, 0.050] | 0.000 [0.000, 0.000] | 2 | pl_015/after3, pl_040/after4 |
| meme/ER | current@10 | 100 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/Tr | stale@10 | 0 / 100 | – | 0.000 [0.000, 0.000] | 0 | – |
| meme/Tr | history-named@10 | 97 / 98 | 0.935 [0.883, 0.979] | 0.929 [0.878, 0.980] | 1 | pl_042/after0 |
| meme/before-Abs-hop1 | current@10 | 100 / 0 | 0.990 [0.970, 1.000] | – | 0 | – |
| meme/before-Abs-hop2 | current@10 | 29 / 0 | 0.966 [0.897, 1.000] | – | 0 | – |
| meme/before-Cas-hop1 | current@10 | 100 / 0 | 0.970 [0.930, 1.000] | – | 0 | – |
| meme/before-Cas-hop2 | current@10 | 62 / 0 | 0.806 [0.710, 0.903] | – | 0 | – |
| meme/before-Del | current@10 | 80 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |
| meme/before-ER | current@10 | 100 / 0 | 1.000 [1.000, 1.000] | – | 0 | – |

