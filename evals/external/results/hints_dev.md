# Mode C: write-time supersession candidates (dev)

Rules: [PLAN.md](../PLAN.md), "Mode C". Each probe is `search(card text, k=5)` just before the write; a hint names up to 3 top results whose `coverage` is at least the threshold. No LLM is involved.

Selection on `dev`: `full`, coverage >= 0.30.

| Set | Positives | Plain | Extends | R@1 | R@3 | Recall | Fire (plain) | Fire (extends) | Extends hint names its baseline | Hinted per write |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pooled | 274 | 2868 | 283 | 0.606 | 0.748 | 0.540 | 0.063 | 0.855 | 0.548 | 0.368 |
| longmemeval-s | 34 | 985 | 0 | 0.147 | 0.353 | 0.118 | 0.101 | – | – | 0.204 |
| mab-sh | 106 | 999 | 0 | 0.887 | 0.943 | 0.943 | 0.000 | – | – | 0.269 |
| meme-filler32k | 134 | 884 | 283 | 0.500 | 0.694 | 0.328 | 0.093 | 0.855 | 0.548 | 0.580 |

## Grid (dev)

| Variant | t | Recall | Fire (plain) | Fire (extends) |
| --- | --- | --- | --- | --- |
| full | 0.00 | 0.748 | 0.627 | 1.000 |
| full | 0.05 | 0.748 | 0.620 | 1.000 |
| full | 0.10 | 0.748 | 0.569 | 1.000 |
| full | 0.15 | 0.737 | 0.417 | 1.000 |
| full | 0.20 | 0.697 | 0.235 | 0.996 |
| full | 0.25 | 0.631 | 0.126 | 0.943 |
| full | 0.30 | 0.540 | 0.063 | 0.855 |
| full | 0.35 | 0.489 | 0.036 | 0.682 |
| full | 0.40 | 0.416 | 0.021 | 0.505 |
| full | 0.45 | 0.376 | 0.012 | 0.286 |
| full | 0.50 | 0.347 | 0.007 | 0.113 |
| full | 0.55 | 0.332 | 0.005 | 0.035 |
| full | 0.60 | 0.310 | 0.002 | 0.014 |
| full | 0.65 | 0.255 | 0.001 | 0.000 |
| full | 0.70 | 0.204 | 0.001 | 0.000 |
| full | 0.75 | 0.179 | 0.001 | 0.000 |
| full | 0.80 | 0.077 | 0.001 | 0.000 |
| full | 0.85 | 0.026 | 0.000 | 0.000 |
| full | 0.90 | 0.015 | 0.000 | 0.000 |
| full | 0.95 | 0.000 | 0.000 | 0.000 |
| summary | 0.00 | 0.774 | 0.621 | 1.000 |
| summary | 0.05 | 0.774 | 0.616 | 1.000 |
| summary | 0.10 | 0.774 | 0.599 | 1.000 |
| summary | 0.15 | 0.774 | 0.558 | 1.000 |
| summary | 0.20 | 0.763 | 0.477 | 1.000 |
| summary | 0.25 | 0.730 | 0.368 | 0.986 |
| summary | 0.30 | 0.686 | 0.256 | 0.940 |
| summary | 0.35 | 0.628 | 0.174 | 0.869 |
| summary | 0.40 | 0.558 | 0.115 | 0.813 |
| summary | 0.45 | 0.507 | 0.079 | 0.774 |
| summary | 0.50 | 0.445 | 0.049 | 0.717 |
| summary | 0.55 | 0.387 | 0.036 | 0.654 |
| summary | 0.60 | 0.343 | 0.025 | 0.576 |
| summary | 0.65 | 0.277 | 0.017 | 0.396 |
| summary | 0.70 | 0.215 | 0.014 | 0.230 |
| summary | 0.75 | 0.182 | 0.009 | 0.120 |
| summary | 0.80 | 0.077 | 0.007 | 0.046 |
| summary | 0.85 | 0.026 | 0.006 | 0.011 |
| summary | 0.90 | 0.015 | 0.006 | 0.004 |
| summary | 0.95 | 0.000 | 0.006 | 0.000 |

