# Reader QA, comparison reader: Qwen on `flat` and `oracle` (PLAN.md section 11)

Pre-registered and frozen (`results/freeze_reader.json`) before the first call; run 2026-11-10 02:19Z-06:31Z on the local `qwen3.8-flash-next-iq3_s`, 1,552 calls. Qwen is the comparison reader: **no line is read on it** (R1-R3 are read on Argon, after the weekly Gemini reset). 95 MEME `nofiller` episodes; 378 target questions (Cascade, Absence and Deletion after the change) and their 378 before-change controls per arm. Brackets are 95% bootstrap intervals (2,000 replicates, seed 20261106), differences paired by question.

**Stage 1 gate: passed.** Invalid answers 0 of 796; control accuracy `flat` 0.931, `oracle` 0.934 (line 0.80); repeats 40 of 40 with the same status. **Hand checks:** 135 `current` answers the value rule rejected, judged before the comparison was printed (`results/audit/reader-qa/qwen.json`): 30 correct (the gold value in other words, 29 of them controls), 87 the stale value, 12 another value, 4 something where MEME expects "none", 2 a misspelled invented name.

| Set | `flat` | `oracle` | `oracle` − `flat` |
| --- | --- | --- | --- |
| Targets (378) | 0.479 [0.429, 0.526] | 0.762 [0.720, 0.804] | **0.283 [0.222, 0.341]** |
| Controls (378) | 0.966 [0.947, 0.984] | 0.974 [0.955, 0.989] | 0.008 [0.000, 0.018] |

By category, targets:

| Category | `flat` | `oracle` |
| --- | --- | --- |
| Cascade, hop 1 | 44/95 (0.46) | 76/95 (0.80) |
| Cascade, hop 2 | 24/63 (0.38) | 32/63 (0.51) |
| Absence, hop 1 | 29/95 (0.31) | 81/95 (0.85) |
| Absence, hop 2 | 1/30 (0.03) | 22/30 (0.73) |
| Deletion | 83/95 (0.87) | 77/95 (0.81) |

Controls are 0.84-1.00 by category for both arms; Cascade hop 2 is the lowest (`flat` 53/63, `oracle` 55/63).

**Deletion is the one category where `oracle` trails** (77/95 against 83/95), and not by leaking. `flat` still holds the user's "please forget X" turn in its raw history, so the reader sees the request and answers `removed` (82 of 95). `oracle` has deleted the fact's cards, request included: Qwen answers `unknown` (77), and otherwise mostly answers `current` from an unrelated card that matched the question's words (13; "regular appointments?" answered with the social meetup). The deleted value itself appears in 4 `oracle` answers and 6 `flat` ones.

**Known grader limit, no effect here:** when MEME's expected control answer is "none", the compiled gold value is empty and no answer can be graded correct; that is 2 control questions per arm, which Qwen answered with a wrong value in both arms.

