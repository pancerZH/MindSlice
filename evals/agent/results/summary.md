# Agent-in-the-loop lineage test: results

Tier 1 as run: MEME `nofiller`, 95 episodes (1,136 questions), four cells, 2026-11-08. Findings:
[../REPORT.md](../REPORT.md). Brackets are 95% bootstrap intervals (2,000 replicates, seed 20261106),
differences paired by unit.

## Confirmatory run (pre-registered): MemoryAgentBench 32k, `agent-policy` @ Argon

[confirm-mab32k-v2.md](confirm-mab32k-v2.md) (v2, registered; v3 identical: [confirm-mab32k-v3.md](confirm-mab32k-v3.md)).

| G1 cut (≥ 0.30) | G2 `retired` (≥ 0.70) | G3 `current@10` diff (≥ −0.05) | G4 `lost` (≤ 0.05) | 6.3 rule |
| --- | --- | --- | --- | --- |
| 0.795 [0.659, 0.909] **confirmed** | 0.909 [0.818, 0.977] **confirmed** (corrected 0.977) | 0.000 [0.000, 0.000] **confirmed** | 0.000 [0.000, 0.000] **confirmed** | unreliable: 3 of 4 `retired` failures are matching errors (one-word subject anchors); 0 of 15 passes missed |

## G1-G5 with matcher v3 (post-hoc re-score, audited both ways)

[tier1-v3.md](tier1-v3.md): `python -m evals.agent report --run tier1-v3 --flat-from gate1-v3 --oracle-from
gate1-v3 --variance tier1-var1-v3,tier1-var2-v3,tier1-var3-v3` (re-score: `python -m evals.agent.rescore3`;
agreement with every hand label: `python -m evals.agent.labels --run tier1-v3`).

| Cell | G1 cut (≥ 0.30) | G2 `retired` (≥ 0.70) | G3 `current@10` diff (≥ −0.05) | G4 `lost` (≤ 0.05) | G5 `forgotten` (≥ 0.90) | 6.3 rule |
| --- | --- | --- | --- | --- | --- | --- |
| `agent-default` @ Argon | 0.327 [0.256, 0.404] point pass | 0.779 [0.730, 0.826] **confirmed** | +0.032 [0.006, 0.063] confirmed | 0.004 [0.002, 0.007] confirmed | 0.989 [0.967, 1.000] confirmed | reliable |
| `agent-policy` @ Argon | 0.327 [0.256, 0.404] point pass | 0.730 [0.676, 0.779] point pass | +0.032 [0.006, 0.063] confirmed | 0.002 [0.001, 0.004] confirmed | 0.978 [0.946, 1.000] confirmed | unreliable (`lost` 2/7: one value) |
| `agent-overlay` @ Argon | 0.321 [0.250, 0.397] point pass | 0.922 [0.890, 0.950] **confirmed** | +0.032 [0.006, 0.063] confirmed | 0.003 [0.001, 0.005] confirmed | 0.946 [0.891, 0.989] point pass | reliable |
| `agent-policy` @ Flash | 0.327 [0.256, 0.404] point pass | 0.676 [0.619, 0.730] **miss** | +0.032 [0.006, 0.063] confirmed | 0.004 [0.002, 0.007] confirmed | 0.978 [0.946, 1.000] confirmed | reliable |
| `oracle` (reference) | 0.321 | 0.875 | 0.000 | 0.001 | 0.924 | |

`lost` errors are one-directional, so raw `lost` is an upper bound: G4 holds in every cell. G1 is capped on
MEME by flat's own `stale-first` (0.327).

### Audits, [audit/tier1-v3/](audit/tier1-v3/)

| Cell | `retired` matching errors | `lost` matching errors | Missed in 15 passes | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- | --- |
| `agent-default` @ Argon | 0 / 50 | 2 / 12 | 0 | 0.779 / 0.779 | 0.004 / 0.003 |
| `agent-policy` @ Argon | 0 / 50 | 2 / 7 | 1 | 0.730 / 0.681 | 0.002 / 0.002 |
| `agent-overlay` @ Argon | 0 / 22 | 0 / 8 | 0 | 0.922 / 0.922 | 0.003 / 0.003 |
| `agent-policy` @ Flash | 1 / 50 | 2 / 13 | 0 | 0.676 / 0.683 | 0.004 / 0.004 |

Matchers against every hand verdict: stale-card cases v2 288/291, v3 289/291; fact cases v2 150/179, v3
173/179; page cases v2 11/87, v3 59/87. Fresh labels for v3 (cases no audit had judged): 20/20 cleared pages
right. Its first new flags were wrong, and the two rules behind them were removed or fixed before the freeze. v3 is
identical to v2 on `flat` and `oracle`.

Absence pages (a stale dependent unwarned on the first page) can't be read from any matcher: on Argon, frozen
58-83%, v2 35-42%, v3 6-23%, and most flags are cards that mark the change in their title and quote the old
statement below (22 of 25 v3 flags audited after its freeze). Estimated from every flag and label: about 3%,
1%, 2% (Argon `agent-default`, `agent-policy`, `agent-overlay`), 5% (Flash).

## Comparisons, v3 (paired by unit)

| Comparison | `retired` | `lost` | `current@10` | `forgotten` |
| --- | --- | --- | --- | --- |
| `agent-policy` minus `agent-default` (Argon) | −0.050 [−0.100, 0.004] | −0.002 [−0.004, 0.000] | 0.000 | −0.011 [−0.033, 0.000] |
| `agent-overlay` minus `agent-policy` (Argon) | +0.192 [0.146, 0.242] | 0.000 [−0.002, 0.003] | 0.000 | −0.033 [−0.098, 0.022] |
| Argon minus Flash (`agent-policy`) | +0.053 [0.000, 0.107] | −0.002 [−0.004, −0.000] | 0.000 | 0.000 [−0.033, 0.033] |

Run-to-run (`agent-policy` @ Argon, 20 episodes, 4 runs, v3): `retired` 0.733-0.800 (SD 0.030); `lost`
0.002-0.003; `stale-first` 0, `current@10` 1, `forgotten` 1 in every run.

Link-only failures (the old value only in a `[[link]]` to a card named after it): 37 of `agent-policy`'s 76
`retired` failures, 21 of `agent-default`'s 62, 15 of Flash's 91, 0 of `agent-overlay`'s.

## Matcher v2 (the confirmatory run's registered scorer)

[tier1-v2.md](tier1-v2.md); audit [audit/tier1-v2/](audit/tier1-v2/). Verdicts as v3's above, except
`agent-overlay` `retired` 0.918 and Flash `lost` 0.011. By the rule, Flash was unreliable as well (`lost` 22/33
matching errors: times, wording, long verbatim values).

## As pre-registered (frozen matcher): every cell unreliable

[tier1.md](tier1.md): `python -m evals.agent report --run tier1 --flat-from gate1 --oracle-from gate1
--variance tier1-var1,tier1-var2,tier1-var3`. Audit: [audit/tier1/](audit/tier1/).

| Cell | G2 `retired` | G4 `lost` | `retired` matching errors | `lost` matching errors |
| --- | --- | --- | --- | --- |
| `agent-default` @ Argon | 0.833 [0.787, 0.876] | 0.012 [0.008, 0.016] | 6 / 43 (14%) | 30 / 34 (88%) |
| `agent-policy` @ Argon | 0.857 [0.814, 0.895] | 0.007 [0.004, 0.010] | 5 / 37 (14%) | 15 / 19 (79%) |
| `agent-overlay` @ Argon | 0.934 [0.903, 0.961] | 0.002 [0.000, 0.004] | 6 / 17 (35%) | 3 / 5 (60%) |
| `agent-policy` @ Flash | 0.756 [0.702, 0.806] | 0.079 [0.069, 0.090] | 8 / 50 (16%, sample of 63) | 50 / 50 (100%, sample of 222) |

The frozen matcher also had false passes its audit didn't sample (an old value written other than verbatim),
which is why its `retired` is higher than v2's.

## Other generated files

| File | What | LLM |
| --- | --- | --- |
| [tier1-v3.md](tier1-v3.md), [tier1-v3.json](tier1-v3.json) | Tier 1 re-scored with matcher v3: every group, telemetry, the two-way audit, comparisons, variance | from tier 1 |
| [tier1-v2.md](tier1-v2.md), [tier1-v2.json](tier1-v2.json) | The same with matcher v2 | from tier 1 |
| [tier1.md](tier1.md), [tier1.json](tier1.json) | Tier 1 with the frozen matcher | yes |
| [smoke.md](smoke.md), [smoke.json](smoke.json) | Smoke tier, three arms × two models (no lines) | yes |
| [projection.json](projection.json) | Tier-1 runtime and token projection from the smoke tier | from smoke |
| [scorer_validation.md](scorer_validation.md) and its two tables | The runner against `evals/external`; value-based vs card-level judgments | no |
| [gate1.md](gate1.md) | Gate 1: the scripted agents against `flat` and `oracle` on all of tier 1 | no |
| [confirm-mab32k-v2.md](confirm-mab32k-v2.md), [confirm-mab32k-v3.md](confirm-mab32k-v3.md) (and `.json`) | The confirmatory run, with v2 and v3 | yes |
| [freeze.json](freeze.json), [freeze_confirm.json](freeze_confirm.json), [freeze_v3.json](freeze_v3.json), [freeze_qwen.json](freeze_qwen.json) | Everything PLAN.md freezes; matcher v2 and the confirmatory run; matcher v3 as its secondary scorer | |
