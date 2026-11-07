"""The engine under test and the comparison versions, each undoing one design decision.

``mindslice`` is the unmodified engine. Every other system patches exactly one choice back out,
for the duration of a run on its own fresh workspace, so the paired difference measures what that
choice is worth on this data:

* ``coverage-first`` - results ordered by IDF-weighted coverage, then verbatim runs, then BM25:
                      the engine's ordering until the user reverted it on holdout-2's evidence.
* ``unweighted-coverage`` - coverage-first with every query word counted equally (the ordering
                      before the dev-informed IDF weighting; see PLAN.md's ledger).
* ``strict-phrase`` - CJK query runs must match verbatim (adjacent bigrams as one FTS5 phrase),
                      the approach basic-memory ships; OR-ed bigrams undone.
* ``v1-baseline``   - the analysis as of commit bc0e7ac: no script-aware analysis, no NFKC, raw
                      ``unicode61`` tokens (its ordering, BM25, is the engine's again).

The record of the coverage-first engine, where ``mindslice`` was coverage-first and ``bm25-order``
was today's ordering, is in ``results/archive/2026-11-06-coverage-first-engine/``.
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from typing import Iterator
from unittest import mock

from mindslice import index as index_module
from mindslice import query as query_module
from mindslice.index import Hit
from mindslice.lexical import QueryPlan, QueryUnit, analyze_query

SYSTEMS = ("mindslice", "coverage-first", "unweighted-coverage", "strict-phrase", "v1-baseline")
BASELINE = "mindslice"

_V1_WORD = re.compile(r"\w+(\*)?", re.UNICODE)


def _coverage_first_hit_key(self: Hit) -> tuple:
    r = self.row
    return (-self.coverage, -self.phrases, -self.score, -r["precedence"], r["mount"], r["path"])


def _coverage_first_result_order(address: str, group: dict, row) -> tuple:
    return (-group["coverage"], -group["phrases"], -group["score"], -row["precedence"], address)


def _unweighted_coverage_rank(self, plan: QueryPlan, rows) -> list[Hit]:
    if not plan.units:
        return [Hit(r, 0.0, 0.0, 0) for r in rows]
    term_ids = {t: self._matching_ids(t) for t in plan.terms}
    phrase_ids = {p: self._matching_ids(p) for p in plan.phrases}
    hits = []
    for r in rows:
        credit, phrases = 0.0, 0
        for unit in plan.units:
            if unit.phrase and r["id"] in phrase_ids[unit.phrase]:
                credit, phrases = credit + 1.0, phrases + 1
                continue
            credit += sum(1 for t in unit.terms if r["id"] in term_ids[t]) / len(unit.terms)
        hits.append(Hit(r, float(r["score"]), credit / len(plan.units), phrases))
    return hits


def _strict_phrase_plan(query: str) -> QueryPlan:
    plan = analyze_query(query)
    return QueryPlan(tuple(QueryUnit(u.text, (u.phrase,), None, u.unspaced) if u.phrase else u for u in plan.units))


def _v1_plan(query: str) -> QueryPlan:
    units, seen = [], set()
    for m in _V1_WORD.finditer(query or ""):
        term = '"' + m.group(0).rstrip("*").replace('"', "") + '"' + ("*" if m.group(1) else "")
        if term not in seen:
            seen.add(term)
            units.append(QueryUnit(m.group(0), (term,)))
    return QueryPlan(tuple(units))


@contextmanager
def system(name: str) -> Iterator[None]:
    if name not in SYSTEMS:
        raise ValueError(f"unknown system {name!r}; choose from {', '.join(SYSTEMS)}")
    with ExitStack() as stack:
        if name in ("coverage-first", "unweighted-coverage"):
            stack.enter_context(mock.patch.object(Hit, "rank_key", _coverage_first_hit_key))
            stack.enter_context(mock.patch.object(query_module, "result_order", _coverage_first_result_order))
        if name == "unweighted-coverage":
            stack.enter_context(mock.patch.object(index_module.Index, "_rank", _unweighted_coverage_rank))
        if name == "strict-phrase":
            stack.enter_context(mock.patch.object(index_module, "analyze_query", _strict_phrase_plan))
        if name == "v1-baseline":
            stack.enter_context(mock.patch.object(index_module, "index_text", lambda text: text))
            stack.enter_context(mock.patch.object(index_module, "analyze_query", _v1_plan))
        yield
