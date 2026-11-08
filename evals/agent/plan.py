"""What is judged, and when (agent_test.md 6.2), compiled from a haystack's annotations.

* **Questions** at their benchmark positions (MEME's before-change questions right after their session,
  everything else after the last session), searched with ``search(question, k=10)``.
* **Updates** (``retired``), judged right after the session that states the new value: MEME's value
  changes (Tracking steps, root changes, other re-stated values) and MemoryAgentBench's conflicts.
* **Deletions** (``forgotten``), judged right after the session holding the request.
* **Current values** (``lost``) at every question point: what holds at that point and was stated before it.
  MEME: each entity's latest value unless it was deleted, or it depends (``dependency_source``, at any
  depth) on a value that changed after it was stated; plus every if-then rule. MemoryAgentBench: each judged
  fact that no later fact contradicts.

A value is **matchable** only when its own flat card (the round or fact the dataset says conveys it) states
it; others can't be told apart from absent by any arm and are left out of that metric (and counted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evals.external.datasets import Haystack, Question
from evals.external.harness import Built

from .judge import CardText, card_text, states, states_any
from .sessions import AgentSession, session_of_unit

END = "end"


@dataclass
class Update:
    id: str
    kind: str  # tracking / root / update / conflict
    session: int
    stale: list[str]  # matchable stale values
    current: list[str]
    anchors: list[str] = field(default_factory=list)
    matchable: bool = True


@dataclass
class Deletion:
    id: str
    entity: str
    session: int
    values: list[str]


@dataclass
class Value:
    id: str
    category: str  # plain / dependent / rule (MEME), fact (MemoryAgentBench)
    value: str
    anchors: list[str] = field(default_factory=list)
    matchable: bool = True
    entity: str = ""  # MEME's entity (for the audit); MemoryAgentBench's question


@dataclass
class Plan:
    questions: dict[Any, list[Question]] = field(default_factory=dict)  # session index or END
    updates: dict[int, list[Update]] = field(default_factory=dict)
    deletions: dict[int, list[Deletion]] = field(default_factory=dict)
    values: dict[Any, list[Value]] = field(default_factory=dict)  # current values per question point
    matchable: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # question id -> role -> values


def _flat_text(b: Built, unit: str) -> CardText | None:
    c = b.card_of_unit.get(unit)
    if c is None:
        return None
    return card_text(c.title, [], c.summary, "\n".join(c.body))


def stated_by_unit(b: Built, unit: str, value: str, anchors=None) -> bool:
    t = _flat_text(b, unit)
    return t is not None and states(t, value, anchors)


def question_matchable(b: Built, q: Question) -> dict[str, list[str]]:
    """The question's values that some card of its own units states, per role."""
    units = set(q.gold) | {u for k in ("stale", "current", "history", "request") for u in q.meta.get(k, [])}
    texts = [t for t in (_flat_text(b, u) for u in sorted(units)) if t is not None]
    vals = q.meta.get("values", {})
    anchors = vals.get("anchors") or None
    return {role: [v for v in vals.get(role, []) if any(states(t, v, anchors) for t in texts)]
            for role in ("stale", "current", "history", "deleted")}


def build(h: Haystack, b: Built, sessions: list[AgentSession]) -> Plan:
    p = Plan()
    last = len(sessions) - 1
    for q in h.questions:
        p.questions.setdefault(q.at_session if q.at_session is not None else END, []).append(q)
        p.matchable[q.id] = question_matchable(b, q)
    if h.dataset.startswith("meme"):
        _meme(h, b, p, last)
    elif h.dataset == "mab-sh":
        _mab(h, b, p, session_of_unit(sessions))
    return p


def _order(unit: str) -> tuple[int, int]:
    s, t = unit.split("#")
    return int(s), int(t)


def _meme(h: Haystack, b: Built, p: Plan, last: int) -> None:
    timeline = h.info["timeline"]
    tracking = next((q.meta["entities"][0] for q in h.questions if q.meta.get("task") == "Tr" and q.meta.get("phase") == "after"), None)
    stored: dict[str, list[dict]] = {}
    for f in timeline:
        e = f["entity"]
        if f["kind"] == "delete":
            prev = stored.pop(e, [])
            vals = [x["value"] for x in prev if stated_by_unit(b, x["unit"], x["value"])]
            p.deletions.setdefault(f["session"], []).append(Deletion(f"{h.key}/delete/{e}", e, f["session"], list(dict.fromkeys(vals))))
        elif f["kind"] == "value":
            prev = stored.get(e, [])
            if prev:
                kind = "root" if e == h.info["root"] else ("tracking" if e == tracking else "update")
                stale = list(dict.fromkeys(x["value"] for x in prev if x["value"] != f["value"]
                                           and stated_by_unit(b, x["unit"], x["value"])))
                ok = bool(stale) and stated_by_unit(b, f["unit"], f["value"])
                p.updates.setdefault(f["session"], []).append(
                    Update(f"{h.key}/update/{f['unit']}", kind, f["session"], stale, [f["value"]], matchable=ok))
            stored.setdefault(e, []).append(f)
    points = sorted({q.at_session for q in h.questions if q.at_session is not None}) + [last]
    for t in dict.fromkeys(points):
        key = END if t == last else t
        p.values[key] = current_values(h, b, t)


def current_values(h: Haystack, b: Built, t: int) -> list[Value]:
    """MEME: the values that hold after session ``t`` (module docstring)."""
    facts = [f for f in h.info["timeline"] if f["session"] <= t]
    cur: dict[str, dict] = {}
    history: dict[str, list[dict]] = {}
    for f in facts:
        if f["kind"] == "delete":
            cur.pop(f["entity"], None)
        elif f["kind"] == "value":
            cur[f["entity"]] = f
            history.setdefault(f["entity"], []).append(f)

    def holds(f: dict, depth: int = 0) -> bool:
        s = f["source"]
        if s is None or depth > 16:
            return True
        if s not in cur:
            return False  # its premise was deleted
        before = [x for x in history.get(s, []) if _order(x["unit"]) <= _order(f["unit"])]
        if not before or before[-1] is not cur[s]:
            return False  # its premise changed after it was stated
        return holds(cur[s], depth + 1)

    out = []
    for e, f in cur.items():
        if holds(f):
            cat = "dependent" if f["source"] else "plain"
            out.append(Value(f"{h.key}/{f['unit']}", cat, f["value"], matchable=stated_by_unit(b, f["unit"], f["value"]), entity=e))
    for f in facts:
        if f["kind"] == "rule":
            out.append(Value(f"{h.key}/{f['unit']}", "rule", f["value"], matchable=stated_by_unit(b, f["unit"], f["value"]),
                             entity=f["entity"]))
    return out


def _mab(h: Haystack, b: Built, p: Plan, where: dict[str, int]) -> None:
    seen: set[tuple] = set()
    values = []
    for q in h.questions:
        v = q.meta["values"]
        anchors = v.get("anchors") or []
        (unit,) = q.gold
        if v.get("stale"):
            stale = [s for s in v["stale"] if any(stated_by_unit(b, u, s, anchors) for u in q.meta.get("stale", []))]
            ok = bool(stale) and bool(v["current"]) and stated_by_unit(b, unit, v["current"][0], anchors)
            p.updates.setdefault(where[unit], []).append(
                Update(f"{h.key}/update/{q.id}", "conflict", where[unit], stale, list(v["current"]), anchors, ok))
        if v.get("latest") and v.get("current"):
            key = (v["current"][0], tuple(anchors))
            if key not in seen:
                seen.add(key)
                values.append(Value(f"{h.key}/{q.id}", "fact", v["current"][0], anchors,
                                    stated_by_unit(b, unit, v["current"][0], anchors), entity=q.text))
    p.values[END] = values
