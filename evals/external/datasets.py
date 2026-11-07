"""Dataset compilers: each benchmark becomes haystacks (one workspace each) of sessions, plus questions.

Judgments come from the datasets' own annotations, as turn references ("units"):

* LongMemEval-S: ``answer_session_ids`` (sessions) and ``has_answer`` turns. Abstention (``_abs``)
  questions are excluded from retrieval scoring, as in LongMemEval's own retrieval evaluation.
* LoCoMo: ``evidence`` dialogue ids (``D3:7``); ids that name no turn are dropped and counted.
* MEME: ``gold_facts`` (the user turn conveying each fact) of the task's target entities, and for
  Cascade and Absence the facts along the dependency chain up to the root (``dependency_edges_used``).
* MemoryAgentBench (FactConsolidation, single-hop): no evidence annotations exist. The judged fact is
  derived from the answer (PLAN.md): the fact ending with an answer alias whose remaining text shares the
  longest run of words with the question, when that best match is unique.

Mode B lineage (``Lineage``) is compiled from the same annotations: which turn's card supersedes,
extends, or deletes which.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .corpus import Session, Turn
from .sources import MAB_COLUMNS, path_of


@dataclass
class Question:
    id: str
    dataset: str
    category: str
    text: str
    gold: set[str]  # turn refs
    gold_sessions: set[str]  # session refs
    answerable: bool = True
    at_session: int | None = None  # asked after sessions[: at_session + 1]; None = after all
    meta: dict[str, Any] = field(default_factory=dict)  # current / stale / history unit refs, hop, ...


@dataclass
class Lineage:
    """Mode B operations, keyed by the turn whose card carries them."""

    supersedes: dict[str, list[str]] = field(default_factory=dict)
    extends: dict[str, list[str]] = field(default_factory=dict)
    deletes: dict[str, list[str]] = field(default_factory=dict)  # this turn is not stored; it deletes these
    notes: dict[str, int] = field(default_factory=dict)


@dataclass
class Haystack:
    key: str
    dataset: str
    sessions: list[Session]
    questions: list[Question]
    lineage: Lineage | None = None
    granularities: tuple[str, ...] = ("session", "round")
    info: dict[str, Any] = field(default_factory=dict)


def _load_json(key: str, root: Path | None) -> Any:
    with open(path_of(key, root), encoding="utf-8") as fh:
        return json.load(fh)


def _chronological(dates: list[str]) -> list[int]:
    return sorted(range(len(dates)), key=lambda i: (dates[i], i))


# ---------------------------------------------------------------------------
# LongMemEval-S (cleaned)
# ---------------------------------------------------------------------------


def longmemeval(root: Path | None = None) -> Iterator[Haystack]:
    for q in _load_json("longmemeval-s", root):
        qid = q["question_id"]
        order = _chronological(q["haystack_dates"])
        sessions = []
        has_answer: dict[str, list[str]] = defaultdict(list)
        for i in order:
            sid = q["haystack_session_ids"][i]
            turns = []
            for j, t in enumerate(q["haystack_sessions"][i]):
                ref = f"{sid}#{j}"
                role = t["role"]
                turns.append(Turn(role.capitalize(), t["content"], ref, role))
                if t.get("has_answer"):
                    has_answer[sid].append(ref)
            sessions.append(Session(sid, q["haystack_dates"][i], tuple(turns)))
        abstention = qid.endswith("_abs")
        answer_sids = list(q["answer_session_ids"])
        gold = {r for sid in answer_sids for r in has_answer.get(sid, [])}
        question = Question(qid, "longmemeval-s", q["question_type"], q["question"], gold, set(answer_sids),
                            answerable=not abstention, meta={"answer": q["answer"]})
        lineage = None
        if q["question_type"] == "knowledge-update" and not abstention and len(answer_sids) == 2:
            dates = {sid: q["haystack_dates"][q["haystack_session_ids"].index(sid)] for sid in answer_sids}
            old, new = sorted(answer_sids, key=lambda s: (dates[s], s))
            question.meta.update(stale=list(has_answer.get(old, [])), current=list(has_answer.get(new, [])),
                                 suffix_order_agrees=old.endswith("_1") and new.endswith("_2"))
            if has_answer.get(old) and has_answer.get(new):
                lineage = Lineage(supersedes={has_answer[new][0]: list(has_answer[old])})
        yield Haystack(f"longmemeval-s/{qid}", "longmemeval-s", sessions, [question], lineage)


# ---------------------------------------------------------------------------
# LoCoMo
# ---------------------------------------------------------------------------

# Category numbers as LoCoMo's evaluation code treats them (task_eval/evaluation.py).
LOCOMO_CATEGORIES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def locomo(root: Path | None = None) -> Iterator[Haystack]:
    for sample in _load_json("locomo", root):
        conv = sample["conversation"]
        numbers = sorted(int(k.split("_")[1]) for k, v in conv.items()
                         if re.fullmatch(r"session_\d+", k) and isinstance(v, list))
        sessions, session_of = [], {}
        for n in numbers:
            ref = f"D{n}"
            turns = []
            for t in conv[f"session_{n}"]:
                extra = (t["blip_caption"],) if t.get("blip_caption") else ()
                turns.append(Turn(t["speaker"], t["text"], t["dia_id"], "", extra))
                session_of[t["dia_id"]] = ref
            sessions.append(Session(ref, conv.get(f"session_{n}_date_time", ""), tuple(turns)))
        questions, dropped, unjudged = [], 0, 0
        for i, qa in enumerate(sample["qa"]):
            refs = [e.strip() for e in qa.get("evidence", []) for e in str(e).split(";")]
            valid = {e for e in refs if e in session_of}
            dropped += len(set(refs) - valid)
            category = LOCOMO_CATEGORIES.get(qa["category"], str(qa["category"]))
            if not valid:
                unjudged += 1
            questions.append(Question(f"{sample['sample_id']}/q{i:03d}", "locomo", category, qa["question"], valid,
                                      {session_of[e] for e in valid}, answerable=qa["category"] != 5,
                                      meta={"answer": qa.get("answer", qa.get("adversarial_answer"))}))
        yield Haystack(f"locomo/{sample['sample_id']}", "locomo", sessions, questions,
                       granularities=("session", "turn"),
                       info={"dropped_evidence_ids": dropped, "questions_without_valid_evidence": unjudged})


# ---------------------------------------------------------------------------
# MEME
# ---------------------------------------------------------------------------


def meme(variant: str = "meme-filler32k", root: Path | None = None) -> Iterator[Haystack]:
    for ep in _load_json(variant, root):
        sessions = []
        facts: list[dict[str, Any]] = []  # chronological
        for i, s in enumerate(ep["sessions"]):
            sref = f"{i}"
            turns = tuple(Turn(t["role"].capitalize(), t["content"], f"{i}#{j}", t["role"])
                          for j, t in enumerate(s["conversation"]))
            sessions.append(Session(sref, s.get("timestamp", ""), turns))
            for f in s.get("gold_facts", []) if s["type"] == "evidence" else []:
                if f.get("conveyed"):
                    facts.append({**f, "unit": f"{i}#{f['conveyed_in_turn']}", "session_index": i})
        by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in facts:
            by_entity[f["entity"]].append(f)
        parent = {e["target"]: e["source"] for e in ep["dependency_edges_used"]}

        def chain(entity: str) -> list[str]:
            out = [entity]
            while out[-1] in parent and parent[out[-1]] not in out:
                out.append(parent[out[-1]])
            return out

        def units(entities, keep=lambda f: True, upto: int | None = None) -> set[str]:
            return {f["unit"] for e in entities for f in by_entity.get(e, [])
                    if keep(f) and (upto is None or f["session_index"] <= upto)}

        value = lambda f: not f.get("is_if_then") and f.get("type") != "delete"
        questions = []
        for phase in ("before", "after"):
            block = ep[f"{phase}_questions"]
            at = block["position_after_session"]
            for n, q in enumerate(block["questions"]):
                task, targets = q["task_type"], list(q["entity"])
                meta: dict[str, Any] = {"task": task, "phase": phase, "hop": q.get("hop"), "entities": targets}
                if phase == "before":
                    gold = units(targets, value, upto=at)
                elif task in ("Cas", "Abs"):
                    gold = units(chain(targets[0]))
                    meta["stale"] = sorted(units(targets, value))
                    meta["current"] = sorted(units(targets, lambda f: f.get("is_if_then"))) if task == "Cas" else []
                elif task == "Del":
                    gold = units(targets)
                    meta["stale"] = sorted(units(targets, value))
                    meta["deleted_values"] = sorted({str(f["value"]) for e in targets for f in by_entity[e] if value(f)})
                    meta["request"] = sorted(units(targets, lambda f: f.get("type") == "delete"))
                elif task == "Tr":
                    gold = units(targets)
                    meta["history"] = [f["unit"] for f in by_entity[targets[0]] if value(f)]
                else:
                    gold = units(targets)
                category = f"{task}-hop{q['hop']}" if task in ("Cas", "Abs") else task
                questions.append(Question(f"{ep['episode_id']}/{phase}{n}", variant, category, q["question"], gold,
                                          {u.split("#")[0] for u in gold}, at_session=at if phase == "before" else None,
                                          meta=meta))
        kinds = {e: [{"unit": f["unit"], "kind": "rule" if f.get("is_if_then") else
                      ("delete" if f.get("type") == "delete" else "value")} for f in fs] for e, fs in by_entity.items()}
        yield Haystack(f"{variant}/{ep['episode_id']}", variant, sessions, questions, _meme_lineage(facts),
                       info={"domain": ep["domain"], "root": ep["root"], "facts": kinds})


def _meme_lineage(facts: list[dict[str, Any]]) -> Lineage:
    """Updates supersede the entity's previous value; dependents extend their source's current value;
    if-then rules extend the dependent's current value; a delete request removes the entity's cards."""
    lin = Lineage(notes=defaultdict(int))
    current: dict[str, str] = {}  # entity -> unit of its current value card
    stored: dict[str, list[str]] = defaultdict(list)  # entity -> value cards still stored
    for f in facts:
        e, u = f["entity"], f["unit"]
        if f.get("type") == "delete":
            lin.deletes[u] = list(stored.pop(e, []))
            current.pop(e, None)
            lin.notes["delete"] += 1
            continue
        if f.get("is_if_then"):
            if e in current:
                lin.extends.setdefault(u, []).append(current[e])
                lin.notes["rule extends dependent"] += 1
            else:
                lin.notes["rule without a stored dependent"] += 1
            continue
        if e in current:
            lin.supersedes.setdefault(u, []).append(current[e])
            lin.notes["update supersedes previous value"] += 1
        source = f.get("dependency_source")
        if f.get("has_dependency") and source:
            if source in current:
                lin.extends.setdefault(u, []).append(current[source])
                lin.notes["dependent extends source"] += 1
            else:
                lin.notes["dependent without a stored source"] += 1
        current[e] = u
        stored[e].append(u)
    lin.notes = dict(lin.notes)
    return lin


# ---------------------------------------------------------------------------
# MemoryAgentBench: FactConsolidation, single-hop
# ---------------------------------------------------------------------------

_WORDS = re.compile(r"\w+")


def _tokens(text: str) -> list[str]:
    return _WORDS.findall(text.lower())


def _longest_run(a: list[str], b: list[str]) -> int:
    best = 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def label_fact(question: str, answers: list[str], facts: dict[int, str]) -> tuple[int | None, str, str | None]:
    """The derived judgment for one question: (fact number, reason, matched prefix)."""
    q = _tokens(question)
    cands = []
    for n, text in facts.items():
        low = text.lower()
        for a in answers:
            if low.endswith(" " + a.lower() + "."):
                prefix = text[: len(text) - len(a) - 1].rstrip()
                cands.append((_longest_run(q, _tokens(prefix)), n, prefix))
                break
    if not cands:
        return None, "no fact ends with an answer", None
    best = max(c[0] for c in cands)
    top = [c for c in cands if c[0] == best]
    if len(top) > 1:
        return None, "best subject match not unique", None
    _, n, prefix = top[0]
    return n, "labeled", prefix


def memoryagentbench(root: Path | None = None) -> Iterator[Haystack]:
    from .parquet import ParquetFile

    rows = ParquetFile(path_of("mab-cr", root)).rows(list(MAB_COLUMNS))
    for row in rows:
        source = row["metadata.source"]
        if "_sh_" not in source:
            continue  # multi-hop: intermediate hops can't be labeled from the answer (PLAN.md)
        facts = {int(m.group(1)): m.group(2) for m in re.finditer(r"^(\d+)\. (.*)$", row["context"], re.M)}
        numbers = sorted(facts)
        turns = tuple(Turn("Fact", facts[n], f"f{n}") for n in numbers)
        questions, lineage, reasons = [], Lineage(), defaultdict(int)
        for i, (text, answers) in enumerate(zip(row["questions"], row["answers"])):
            n, reason, prefix = label_fact(text, list(answers), facts)
            reasons[reason] += 1
            if n is None:
                continue
            siblings = [m for m in numbers if m != n and facts[m].lower().startswith(prefix.lower() + " ")]
            earlier, later = [m for m in siblings if m < n], [m for m in siblings if m > n]
            meta: dict[str, Any] = {"answer": list(answers), "fact": facts[n]}
            conflict = bool(earlier) and not later
            if conflict:
                meta.update(current=[f"f{n}"], stale=[f"f{m}" for m in earlier])
                lineage.supersedes[f"f{n}"] = [f"f{m}" for m in earlier]
                reasons["conflict (earlier sibling, none later)"] += 1
            elif later:
                reasons["answer is not the latest of its conflicting facts"] += 1
            else:
                reasons["no conflicting fact"] += 1
            questions.append(Question(row["metadata.qa_pair_ids"][i], "mab-sh", source.split("_")[-1], text,
                                      {f"f{n}"}, {"facts"}, meta=meta))
        yield Haystack(f"mab-sh/{source}", "mab-sh", [Session("facts", "", turns)], questions, lineage,
                       granularities=("turn",), info={"facts": len(facts), "label_reasons": dict(reasons)})


LOADERS = {
    "longmemeval-s": lambda root: longmemeval(root),
    "locomo": lambda root: locomo(root),
    "meme-filler32k": lambda root: meme("meme-filler32k", root),
    "meme-nofiller": lambda root: meme("meme-nofiller", root),
    "mab-sh": lambda root: memoryagentbench(root),
}
SOURCE_OF = {"longmemeval-s": "longmemeval-s", "locomo": "locomo", "meme-filler32k": "meme-filler32k",
             "meme-nofiller": "meme-nofiller", "mab-sh": "mab-cr"}
