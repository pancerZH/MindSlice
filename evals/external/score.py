"""Scoring: retrieval metrics per record, group means with bootstrap intervals, AUROC, Mode B state metrics.

Retrieval metrics are ``evals/retrieval/metrics.py``'s, with every judged card at grade 2 (binary
relevance; nDCG is unchanged by the scale, and MRR then means "first judged card"). Two levels:

* ``card``: the ranked cards themselves, judged when they hold an evidence turn (round and turn corpora).
* ``session``: the ranked cards' sessions, first occurrence kept, judged against the evidence sessions.

``All@10`` (every judged item on the first page) is added because multi-evidence questions need all of it.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Iterable, Sequence

from evals.retrieval.metrics import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    interval,
    mrr_at,
    ndcg_at,
    percentile,
    recall_at,
    resamples,
    verdict,
)

METRICS = ("recall@5", "recall@10", "mrr@10", "ndcg@5", "all@10")


def retrieval(ranked: Sequence[str], judged: Iterable[str]) -> dict[str, float]:
    rel = {a: 2 for a in judged}
    return {"recall@5": recall_at(ranked, rel, 5), "recall@10": recall_at(ranked, rel, 10),
            "mrr@10": mrr_at(ranked, rel, 10), "ndcg@5": ndcg_at(ranked, rel, 5),
            "all@10": 1.0 if rel and set(rel) <= set(ranked[:10]) else 0.0}


def levels(rec: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Scores at each level that applies to this record (none when it has no judgments there)."""
    out = {}
    if rec["granularity"] != "session" and rec["gold"]:
        out["card"] = retrieval(rec["ranked"], rec["gold"])
    if rec["gold_sessions"] and rec["dataset"] != "mab-sh":  # its facts form one list: no session level
        sessions = list(dict.fromkeys(s for s in rec["sessions"] if s is not None))
        out["session"] = retrieval(sessions, rec["gold_sessions"])
    return out


def mean_ci(values: Sequence[float], seed: int = BOOTSTRAP_SEED) -> dict[str, float]:
    if not values:
        return {"mean": float("nan"), "low": float("nan"), "high": float("nan"), "n": 0}
    m, lo, hi = interval(list(values), resamples(len(values), BOOTSTRAP_REPLICATES, seed))
    return {"mean": round(m, 4), "low": round(lo, 4), "high": round(hi, 4), "n": len(values)}


def paired_ci(a: Sequence[float], b: Sequence[float]) -> dict[str, float]:
    """Mean of ``a - b`` (paired by position), with the shared-resample interval."""
    return mean_ci([x - y for x, y in zip(a, b)])


# ---------------------------------------------------------------------------
# AUROC (does a signal separate answerable from unanswerable questions?)
# ---------------------------------------------------------------------------


def auroc(positives: Sequence[float], negatives: Sequence[float]) -> float:
    """P(score of a random answerable question > score of a random unanswerable one), ties counting half."""
    if not positives or not negatives:
        return float("nan")
    ranked = sorted([(s, 1) for s in positives] + [(s, 0) for s in negatives])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + 1 + j) / 2  # average 1-based rank of the tie block
        rank_sum += avg * sum(1 for _, y in ranked[i:j] if y == 1)
        i = j
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def auroc_ci(positives: Sequence[float], negatives: Sequence[float],
             replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED) -> dict[str, float]:
    """AUROC with a 95% percentile bootstrap, resampling within each class (stratified)."""
    point = auroc(positives, negatives)
    rng = random.Random(seed)
    reps = []
    for _ in range(replicates):
        p = [positives[rng.randrange(len(positives))] for _ in positives]
        n = [negatives[rng.randrange(len(negatives))] for _ in negatives]
        reps.append(auroc(p, n))
    return {"mean": round(point, 4), "low": round(percentile(reps, 0.025), 4),
            "high": round(percentile(reps, 0.975), 4), "positives": len(positives), "negatives": len(negatives)}


# ---------------------------------------------------------------------------
# Mode B: stale facts and current facts on the first page
# ---------------------------------------------------------------------------


def state(rec: dict[str, Any]) -> dict[str, float]:
    """For a question about current state (``current`` and/or ``stale`` cards are known).

    * ``current@10``: share of the current-value cards on the first page.
    * ``stale@10``: a stale-value card is on the page *unwarned* (status ``active`` and no
      ``baseline_superseded_by``): the agent is shown an outdated fact as if it held.
    * ``stale-first``: an unwarned stale card ranks above every current card (questions with a current card).
    """
    ranked, warned = rec["ranked"], rec["warned"]
    stale, current = set(rec.get("stale", [])), set(rec.get("current", []))
    first_stale = next((i for i, a in enumerate(ranked) if a in stale and not warned[i]), math.inf)
    first_current = next((i for i, a in enumerate(ranked) if a in current), math.inf)
    out = {"stale@10": 1.0 if first_stale < math.inf else 0.0}
    if current:
        out["current@10"] = recall_at(ranked, {a: 2 for a in current}, 10)
        out["stale-first"] = 1.0 if first_stale < first_current else 0.0
    if "value_leak" in rec:
        out["value-leak@10"] = 1.0 if rec["value_leak"] else 0.0
    if rec.get("history"):
        out["history@10"] = recall_at(ranked, {a: 2 for a in rec["history"]}, 10)
        named = list(ranked) + [v for vs in rec.get("via", []) for v in vs]
        out["history-named@10"] = recall_at(named, {a: 2 for a in rec["history"]}, len(named) or 1)
    return out


def verdict_of(stat: dict[str, float], line: float) -> str:
    if stat.get("n", 1) == 0 or math.isnan(stat["mean"]):
        return "no data"
    return verdict(stat["mean"], stat["low"], line)


def group_by(records: Iterable[dict[str, Any]], key: Callable[[dict[str, Any]], Any]) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = {}
    for r in records:
        k = key(r)
        if k is not None:
            out.setdefault(k, []).append(r)
    return out
