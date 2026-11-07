# Mode C: write-time supersession candidates (holdout)

Rules: [PLAN.md](../PLAN.md), "Mode C". Each probe is `search(card text, k=5)` just before the write; a hint names up to 3 top results whose `coverage` is at least the threshold. No LLM is involved.

Selection on `dev`: `full`, coverage >= 0.30.

| Line | Claim | Point | 95% interval | Line | Verdict |
| --- | --- | --- | --- | --- | --- |
| H1 | Predecessor in the top 3 (`full` query, no threshold) | 0.685 | [0.633, 0.734] | 0.80 | **miss** |
| H2a | Predecessor hinted (`full`, coverage >= 0.30) | 0.506 | [0.451, 0.562] | 0.60 | **miss** |
| H2b | Plain writes with any hint (`full`, coverage >= 0.30); lower is better | 0.062 | [0.053, 0.070] | 0.20 | **confirmed** |

| Set | Positives | Plain | Extends | R@1 | R@3 | Recall | Fire (plain) | Fire (extends) | Extends hint names its baseline | Hinted per write |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pooled | 308 | 2942 | 258 | 0.542 | 0.685 | 0.506 | 0.062 | 0.833 | 0.570 | 0.353 |
| longmemeval-s | 36 | 1019 | 0 | 0.083 | 0.222 | 0.083 | 0.094 | – | – | 0.191 |
| mab-sh | 99 | 1014 | 0 | 0.949 | 0.980 | 0.980 | 0.000 | – | – | 0.246 |
| meme-filler32k | 173 | 909 | 258 | 0.405 | 0.613 | 0.324 | 0.094 | 0.833 | 0.570 | 0.569 |

