+++
title = "Proactive memory policy"
load = "always"
tags = ["memory-policy"]
aliases = ["automatic memory", "when to remember", "memory recording preferences"]
+++

Actively maintain useful memory for future sessions without waiting for me to say “remember this”. Keep records grounded, focused and consistent with my requested scope and review settings.

- Record my explicitly stated lasting preferences, accepted project decisions, stable constraints, corrections to existing knowledge, and verified debugging lessons that can be reused.
- After such information is confirmed, and before completing a meaningful task phase, check for new or corrected knowledge worth saving. Write while the evidence is available; do not wait for a session-end signal. If nothing qualifies, do not write.
- Distinguish my decisions from suggestions you have made but I have not adopted. Do not automatically record guesses, one-off task state or entire conversations. Respect anything I ask you not to remember.
- Search for related memory and read likely matches unless you already checked them in this conversation. Prefer updating an existing card; skip information already represented instead of creating duplicates.
- Keep one independently changing topic per card. Preserve concrete facts, their scope and conditions; use only as much text as needed and do not invent detail to fill a template.
- When a fact changes, record the appropriate `supersedes` relationship and retain any still-valid information. Use `extends` for additional context or dependencies that do not replace the baseline.
- Supply a specific `reason` with every write, citing the confirmation, correction or observed result that prompted it. Let the engine maintain the history log.
- Use `load = "always"` for lasting instructions that should govern every session; ordinary knowledge stays `as-needed`. Honor staging and review requirements; automatic recording does not authorize applying proposals or baking slices.
- Check the tool result before reporting success. Briefly distinguish “saved and active” from “pending review”; do not claim a failed write was remembered or repeatedly ask whether to record information covered by this policy.
