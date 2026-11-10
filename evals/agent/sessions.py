"""What the agent reads: a haystack as a list of conversations (agent_test.md 4.2), and the tiers (section 5).

* MEME and LongMemEval: one conversation per dataset session, in order. The transcript is exactly the turn
  lines the harness writes into card bodies (``evals.external.corpus.bullet``: ``Speaker: text``,
  continuation lines indented, image captions as ``Speaker shared an image: ...``, ``[[`` as ``[ [``).
* MemoryAgentBench (one list of facts): batches of ``MAB_BATCH`` (10; the plan's 50 doesn't fit the call
  cap, see below) consecutive facts, one per line in dataset order,
  headed ``Facts {a}-{b} of {N}, in the order they were stated:``.

Each conversation also carries the flat cards of what it covers (rounds for MEME and LongMemEval, one card
per fact for MemoryAgentBench, as in Mode B): the ``flat`` and ``oracle`` arms write them, ``agent-overlay``
mounts them in ``@history``, and the scorer uses them to decide which values are matchable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.external.corpus import Card, bullet, clean
from evals.external.datasets import Haystack
from evals.external.harness import Built, built

# agent_test.md 4.2 says 50 facts per batch. The smoke tier showed that 50 can't fit the 40-call cap (4.5):
# at 50, 9 of 10 batches of agent-default (Flash) hit the cap and most facts went unwritten (PLAN.md ledger).
# The policy's procedure (search, read the old card, write) takes about 3 calls per fact, so 10 facts fit.
MAB_BATCH = 10
FLAT_GRANULARITY = {"meme-nofiller": "round", "meme-filler32k": "round", "longmemeval-s": "round", "mab-sh": "turn"}

TIERS = {
    # Smoke: plumbing and prompt checks; never scored for lines.
    "smoke": {"meme-nofiller": ("pl_001", "pl_002", "pl_003", "pl_004", "pl_005"), "mab-sh": ("factconsolidation_sh_6k",)},
    # Tier 1: the other 95 MEME nofiller episodes; MemoryAgentBench 32k.
    "1": {"meme-nofiller": "rest", "mab-sh": ("factconsolidation_sh_32k",)},
    # Not a tier: the configuration of evals/external/results/summary.md (Mode B), to compare the value-based
    # scorer with its card-level numbers (flat and oracle only; no LLM).
    "external": {"meme-filler32k": "all", "mab-sh": "all"},
}


@dataclass
class AgentSession:
    index: int  # 0-based position among the haystack's conversations
    total: int
    date: str
    transcript: str
    cards: list[Card] = field(default_factory=list)  # flat cards of what this conversation covers
    units: list[str] = field(default_factory=list)  # dataset turn refs it covers


def flat(h: Haystack) -> Built:
    return built(h, FLAT_GRANULARITY[h.dataset])


def turn_lines(turns) -> str:
    lines = []
    for t in turns:
        lines.append(bullet(t.speaker, t.text))
        lines += [bullet(f"{t.speaker} shared an image", x) for x in t.extra]
    return "\n".join(lines)


def agent_sessions(h: Haystack, b: Built | None = None) -> list[AgentSession]:
    b = b or flat(h)
    if h.dataset == "mab-sh":
        (session,) = h.sessions
        turns = session.turns
        n = len(turns)
        batches = [turns[i:i + MAB_BATCH] for i in range(0, n, MAB_BATCH)]
        out = []
        for j, batch in enumerate(batches):
            a = j * MAB_BATCH + 1
            head = f"Facts {a}-{a + len(batch) - 1} of {n}, in the order they were stated:"
            text = "\n".join([head, *(" ".join(clean(t.text).split()) for t in batch)])
            refs = [t.ref for t in batch]
            out.append(AgentSession(j, len(batches), "", text, [b.card_of_unit[r] for r in refs], refs))
        return out
    by_session: dict[str, list[Card]] = {}
    for c in b.cards:
        by_session.setdefault(c.session, []).append(c)
    return [AgentSession(i, len(h.sessions), s.date, turn_lines(s.turns), by_session.get(s.ref, []), [t.ref for t in s.turns])
            for i, s in enumerate(h.sessions)]


def session_of_unit(sessions: list[AgentSession]) -> dict[str, int]:
    return {u: s.index for s in sessions for u in s.units}


def tier_haystacks(tier: str, root=None) -> list[Haystack]:
    from evals.external.datasets import LOADERS

    spec = TIERS[tier]
    out: list[Haystack] = []
    for dataset, keys in spec.items():
        hs = list(LOADERS[dataset](root))
        if keys == "all":
            out += hs
        elif keys == "rest":
            used = {k for t, sp in TIERS.items() if t != tier and isinstance(sp.get(dataset), tuple) for k in sp[dataset]}
            out += [h for h in hs if h.key.split("/", 1)[1] not in used]
        else:
            by = {h.key.split("/", 1)[1]: h for h in hs}
            out += [by[k] for k in keys]
    return out
