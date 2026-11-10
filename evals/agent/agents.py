"""Memory writers ("agents"): a function from one session's task and a tool dispatcher to a finished session.

* ``flat`` and ``oracle`` are Mode A and Mode B: the harness writes the cards itself (``evals.external``'s
  bulk files and ``Workspace.write`` lineage), session by session.
* ``scripted-flat``, ``scripted-oracle`` and ``scripted-overlay`` (agent_test.md 3, 4.4) do the same through
  the four MCP tools only, exactly as an LLM agent would have to. They read the annotations, so they are
  checks of the runner (ordering, question timing, scoring), not baselines.
* The LLM arms are in ``agy.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from evals.external.corpus import Card, add_files, write_card
from evals.external.datasets import Haystack
from mindslice import Workspace

from .sessions import AgentSession

ToolCall = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass
class SessionTask:
    arm: str
    haystack: Haystack
    session: AgentSession  # cards carry the annotations' lineage for the oracle-type arms
    system_prompt: str
    message: str
    ws: Workspace
    workdir: Path
    deletes: dict[str, list[str]] = field(default_factory=dict)  # card path -> card paths it deletes (Mode B)


@dataclass
class SessionOutcome:
    reply: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)  # tool-call log rows
    meta: dict[str, Any] = field(default_factory=dict)  # tokens, latency, errors, finished reason
    failed: bool = False


def _args(card: Card) -> dict[str, Any]:
    return {k: v for k, v in card.write_args().items() if v is not None}


class DirectFlat:
    """Mode A: the round (or fact) cards, written as files."""

    tools = False

    def run_session(self, task: SessionTask, call: ToolCall | None = None) -> SessionOutcome:
        add_files(task.ws, task.session.cards)
        return SessionOutcome("DONE")


class DirectOracle:
    """Mode B, as ``evals.external.harness.run_haystack`` ingests it (plain files first, then lineage writes)."""

    tools = False

    def run_session(self, task: SessionTask, call: ToolCall | None = None) -> SessionOutcome:
        cards = task.session.cards
        add_files(task.ws, [c for c in cards if not (c.supersedes or c.extends or c.path in task.deletes)])
        for c in cards:
            if c.path in task.deletes:
                for target in task.deletes[c.path]:
                    task.ws.write(target, op="delete")
            elif c.supersedes or c.extends:
                write_card(task.ws, c)
        return SessionOutcome("DONE")


class ScriptedFlat:
    """Each round (or fact) as a card, through ``write``: reproduces ``flat``."""

    tools = True

    def run_session(self, task: SessionTask, call: ToolCall) -> SessionOutcome:
        for c in task.session.cards:
            call("write", {"id": c.path, "op": "create", **{k: v for k, v in _args(c).items() if k not in ("extends", "supersedes")}})
        return SessionOutcome("DONE")


class ScriptedOracle:
    """The annotations' lineage replayed through ``write``: reproduces ``oracle``."""

    tools = True

    def run_session(self, task: SessionTask, call: ToolCall) -> SessionOutcome:
        for c in task.session.cards:
            if c.path in task.deletes:
                for target in task.deletes[c.path]:
                    call("write", {"id": target, "op": "delete"})
            else:
                call("write", {"id": c.path, "op": "create", **_args(c)})
        return SessionOutcome("DONE")


class ScriptedOverlay:
    """``agent-overlay``'s cards from the annotations (agent_test.md 4.4): the flat cards are in ``@history``;
    each card that carries lineage in Mode B is copied to ``@overlay`` with that lineage, superseding its own
    ``@history`` card, and with every target mapped to its current card (preferring an ``@overlay``
    replacement). A forget card states only that the value was forgotten; it supersedes the cards Mode B
    deletes and the request's own ``@history`` card."""

    tools = True
    PREFIX = "lineage"

    def __init__(self) -> None:
        self.successor: dict[str, str] = {}

    def current(self, mode_b_address: str) -> str:
        a = "@history/" + mode_b_address.split("/", 1)[1]
        seen = {a}
        while a in self.successor and self.successor[a] not in seen:
            a = self.successor[a]
            seen.add(a)
        return a

    def run_session(self, task: SessionTask, call: ToolCall) -> SessionOutcome:
        timeline = task.haystack.info.get("timeline", [])
        for c in task.session.cards:
            own = f"@history/{c.path}"
            new_id = f"{self.PREFIX}/{c.path}"
            new = f"@overlay/{new_id}"
            if c.path in task.deletes:
                entity = next((f["entity"] for f in timeline if f["kind"] == "delete" and f["unit"] in c.units), "")
                what = entity.replace("_", " ") or "this"
                replaced = [self.current(f"@overlay/{p}") for p in task.deletes[c.path]] + [own]
                call("write", {"id": new_id, "op": "create", "title": f"Forgotten at the user's request: {what}",
                               "summary": f"The user asked me to forget their {what}; it is no longer remembered.",
                               "content": [f"The user asked me to forget their {what}."], "supersedes": replaced})
            elif c.supersedes or c.extends:
                replaced = [own] + [self.current(a) for a in c.supersedes]
                args = {"id": new_id, "op": "create", "title": c.title, "summary": c.summary, "content": c.body,
                        "tags": c.tags, "supersedes": list(dict.fromkeys(replaced))}
                if c.extends:
                    args["extends"] = list(dict.fromkeys(self.current(a) for a in c.extends))
                call("write", args)
            else:
                continue
            for old in replaced:
                self.successor[old] = new
        return SessionOutcome("DONE")


def make(arm: str, **kw: Any):
    if arm == "flat":
        return DirectFlat()
    if arm == "oracle":
        return DirectOracle()
    if arm == "scripted-flat":
        return ScriptedFlat()
    if arm == "scripted-oracle":
        return ScriptedOracle()
    if arm == "scripted-overlay":
        return ScriptedOverlay()
    from .agy import AgyAgent

    return AgyAgent(arm=arm, **kw)
