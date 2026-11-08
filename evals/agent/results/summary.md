# Agent-in-the-loop lineage test: results

Tier 1 as run: MEME `nofiller`, 95 episodes (1,136 questions), four cells, 2026-11-08. Full tables:
[tier1.md](tier1.md) (`python -m evals.agent report --run tier1 --flat-from gate1 --oracle-from gate1
--variance tier1-var1,tier1-var2,tier1-var3`); findings: [../REPORT.md](../REPORT.md).

## G1-G5

**Every cell is reported as unreliable** under the audit rule (more than 20% matching errors in its `lost`
sample; PLAN.md section 6). Values are descriptive; brackets are 95% bootstrap intervals (2,000 replicates,
seed 20261106), differences paired by unit.

| Cell | G1 cut (≥ 0.30) | G2 `retired` (≥ 0.70) | G3 `current@10` diff (≥ −0.05) | G4 `lost` (≤ 0.05) | G5 `forgotten` (≥ 0.90) | Lines |
| --- | --- | --- | --- | --- | --- | --- |
| `agent-default` @ `gemini-4-argon-medium` | 0.321 [0.244, 0.397] | 0.833 [0.787, 0.876] | +0.019 [−0.013, 0.051] | 0.012 [0.008, 0.016] | 1.000 [1.000, 1.000] | **unreliable** |
| `agent-policy` @ `gemini-4-argon-medium` | 0.327 [0.256, 0.404] | 0.857 [0.814, 0.895] | +0.032 [0.006, 0.063] | 0.007 [0.004, 0.010] | 0.987 [0.961, 1.000] | **unreliable** |
| `agent-overlay` @ `gemini-4-argon-medium` | 0.321 [0.250, 0.397] | 0.934 [0.903, 0.961] | +0.032 [0.006, 0.063] | 0.002 [0.000, 0.004] | 0.961 [0.908, 1.000] | **unreliable** |
| `agent-policy` @ `gemini-3.8-flash-medium` | 0.321 [0.250, 0.397] | 0.756 [0.702, 0.806] | −0.013 [−0.057, 0.032] | 0.079 [0.069, 0.090] | 0.987 [0.961, 1.000] | **unreliable** |
| `oracle` (reference) | 0.321 | 0.891 | 0.000 | 0.000 | 0.921 | |

Raw verdicts, had the lines been readable: G1 point pass in every cell (the largest cut possible on MEME is
flat's 0.327; the oracle's own is 0.321); G2 and G5 confirmed in every cell; G3 confirmed on Argon, a point
pass on Flash; G4 confirmed on Argon, a miss on Flash.

## Audit (6.3)

| Cell | `retired` matching errors | `lost` matching errors | `retired` raw / corrected | `lost` raw / corrected |
| --- | --- | --- | --- | --- |
| `agent-default` @ Argon | 6 / 43 (14%) | 30 / 34 (88%) | 0.833 / 0.857 | 0.012 / 0.001 |
| `agent-policy` @ Argon | 5 / 37 (14%) | 15 / 19 (79%) | 0.857 / 0.876 | 0.007 / 0.001 |
| `agent-overlay` @ Argon | 6 / 17 (35%) | 3 / 5 (60%) | 0.934 / 0.957 | 0.002 / 0.001 |
| `agent-policy` @ Flash | 8 / 50 (16%, sample of 63) | 50 / 50 (100%, sample of 222) | 0.756 / 0.795 | 0.079 / 0.000 |

Worksheets and verdicts: [audit/tier1/](audit/tier1/) (MEME is CC BY 4.0). Matching errors in `lost`: MEME's
annotation formats restated in the agent's words, verbatim error logs kept with escaped line breaks. In
`retired`: another entity's value containing the old value's name (MEME's software episodes reuse one
vocabulary), and lines that mark the old value as past.

## Comparisons (paired by unit)

| Comparison | `retired` | `lost` | `current@10` | `forgotten` |
| --- | --- | --- | --- | --- |
| `agent-policy` minus `agent-default` (Argon) | +0.023 [−0.012, 0.058] | −0.005 [−0.009, −0.001] | +0.013 [0.000, 0.032] | −0.013 [−0.040, 0.000] |
| `agent-overlay` minus `agent-policy` (Argon) | +0.077 [0.039, 0.120] | −0.005 [−0.008, −0.002] | 0.000 [0.000, 0.000] | −0.026 [−0.079, 0.026] |
| Argon minus Flash (`agent-policy`) | +0.101 [0.058, 0.147] | −0.072 [−0.082, −0.063] | +0.044 [0.019, 0.076] | 0.000 [−0.040, 0.040] |

Run-to-run (`agent-policy` @ Argon, 20 episodes, 4 runs): `retired` 0.870-0.907 (SD 0.018); `lost`
0.005-0.009; `stale-first` 0, `current@10` 1, `forgotten` 1 in every run.

## Other generated files

| File | What | LLM |
| --- | --- | --- |
| [tier1.md](tier1.md), [tier1.json](tier1.json) | Tier 1: every group, telemetry, audit, comparisons, variance | yes |
| [smoke.md](smoke.md), [smoke.json](smoke.json) | Smoke tier, three arms × two models (no lines) | yes |
| [projection.json](projection.json) | Tier-1 runtime and token projection from the smoke tier | from smoke |
| [scorer_validation.md](scorer_validation.md) and its two tables | The runner against `evals/external`; value-based vs card-level judgments | no |
| [gate1.md](gate1.md) | Gate 1: the scripted agents against `flat` and `oracle` on all of tier 1 | no |
| [freeze.json](freeze.json) | Everything PLAN.md freezes | |
