"""Per-query metrics and a paired percentile bootstrap (standard library only).

Definitions follow common IR practice (and SpaceBridge's, which inspired this evaluation):

* ``nDCG@k``: linear gain (the grade itself), discount ``1 / log2(rank + 1)``, normalized by the
  ideal ordering of that query's judged cards. Unjudged results count as not relevant.
* ``Recall@k``: share of the query's judged cards (grade > 0) in the first k results.
* ``MRR@k``: ``1 / rank`` of the first result judged 2 (answers the query), 0 if none in the first k.

Means weight every query equally. Intervals are a 95% percentile bootstrap over queries: each
replicate draws one resample of the queries and every system (and every difference between two
systems) is recomputed on that same resample, so differences are paired.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

METRICS = ("ndcg@5", "recall@10", "mrr@10")
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20261106


def ndcg_at(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    dcg = sum(relevant.get(a, 0) / math.log2(i + 2) for i, a in enumerate(ranked[:k]))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def recall_at(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    judged = {a for a, g in relevant.items() if g > 0}
    return len(judged & set(ranked[:k])) / len(judged) if judged else 0.0


def mrr_at(ranked: Sequence[str], relevant: dict[str, int], k: int) -> float:
    for i, a in enumerate(ranked[:k]):
        if relevant.get(a, 0) >= 2:
            return 1.0 / (i + 1)
    return 0.0


def score(ranked: Sequence[str], relevant: dict[str, int]) -> dict[str, float]:
    return {"ndcg@5": ndcg_at(ranked, relevant, 5), "recall@10": recall_at(ranked, relevant, 10),
            "mrr@10": mrr_at(ranked, relevant, 10)}


def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default method)."""
    data = sorted(values)
    pos = (len(data) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def resamples(n: int, replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randrange(n) for _ in range(n)] for _ in range(replicates)]


def interval(values: Sequence[float], draws: list[list[int]]) -> tuple[float, float, float]:
    """(mean, 2.5th percentile, 97.5th percentile) of ``values`` under the shared resamples."""
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    reps = [sum(values[i] for i in draw) / n for draw in draws]
    return sum(values) / n, percentile(reps, 0.025), percentile(reps, 0.975)


def verdict(point: float, low: float, line: float) -> str:
    if low >= line:
        return "confirmed"
    if point >= line:
        return "point pass"
    return "miss"
