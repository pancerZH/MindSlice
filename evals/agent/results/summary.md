# Agent-in-the-loop lineage test: results

**Tier 1 has not been run** (paused for scheduling after the freeze: [`../PLAN.md`](../PLAN.md), section 7), so
there are no G1-G5 verdicts yet. Generated tables so far:

| File | What | LLM |
| --- | --- | --- |
| [scorer_validation.md](scorer_validation.md) | The runner against `evals/external`; value-based vs card-level judgments; scorer choices | no |
| [scorer_validation_tier1.md](scorer_validation_tier1.md), [scorer_validation_external.md](scorer_validation_external.md) | Per-group value-based vs card-level tables (tier 1; summary.md's configuration) | no |
| [gate1.md](gate1.md) | Gate 1: the scripted agents against `flat` and `oracle` on all of tier 1 | no |
| [smoke.md](smoke.md), [smoke.json](smoke.json) | Smoke tier, three arms, two models: metrics (no lines) and telemetry | yes |
| [projection.json](projection.json) | Tier-1 runtime and token projection measured on the smoke tier | from smoke |
| [freeze.json](freeze.json) | Everything PLAN.md freezes; tier 1 refuses to run if it changes | |
