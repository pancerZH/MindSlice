"""The agent prompts, verbatim from ``evals/agent_test.md`` (4.2, 4.3, 4.4), and the session message.

The system prompt is the MCP server's ``INSTRUCTIONS`` string, a blank line, then the task prompt (plus,
per arm, the policy paragraph and the overlay addendum, each after a blank line). ``digests()`` gives
the SHA-256 of every piece and of each arm's full system prompt; PLAN.md freezes them.
"""

from __future__ import annotations

import hashlib

from mindslice.mcp_server import INSTRUCTIONS

TASK = (
    "You are the long-term memory keeper for one user. You will be shown their conversations with an "
    "assistant, one session at a time, in the order they happened. Use the MindSlice tools to record what is "
    "worth remembering about the user for future conversations, and keep that memory accurate and up to date. "
    "You will not be asked questions about it. When you have finished with this session, reply with DONE."
)

POLICY = (
    "Before you write, search for cards about the same thing. If the new information replaces something "
    "already recorded (a changed value, a new preference, a correction), write the new card with "
    "`supersedes` naming the old card's address, rather than leaving both active or deleting the old one, "
    "and restate anything in the old card that is still true. If it refines, adds an exception or an "
    "if-then rule to, or depends on something that stays true (a choice made because of an earlier "
    "preference or plan), write it with `extends` naming that card, so it is flagged if that card later "
    "changes. If you can't tell which, use `extends`: it hides nothing. If the user asks you to forget "
    "something, delete the cards that state it. Put each fact that can change on its own card, and keep its "
    "concrete values, names, dates, conditions and the user's own wording; the summary states the fact."
)

OVERLAY = (
    "Every session is already stored verbatim in the read-only `@history` slice. Don't copy it: write to "
    "`@overlay` only to keep that history accurate. When a value changes, write a card with the new value "
    "that `supersedes` every card stating the old one, in `@history` or `@overlay`. When something depends "
    "on or adds a rule to an earlier fact, write a card restating it that `extends` the card holding that "
    "fact and `supersedes` the `@history` card it came from. When the user asks you to forget something, "
    "write a card that `supersedes` each `@history` card stating it and restates the rest of that card "
    "(you can still delete your own `@overlay` cards). In every replacement, restate any other fact from "
    "the old card that is still true."
)

ARM_PARTS = {
    "agent-default": (INSTRUCTIONS, TASK),
    "agent-policy": (INSTRUCTIONS, TASK, POLICY),
    "agent-overlay": (INSTRUCTIONS, TASK, POLICY, OVERLAY),
}
# Scripted agents receive the same prompt as the LLM arm they stand in for (and ignore it).
SCRIPTED_PROMPT = {"scripted-flat": "agent-default", "scripted-oracle": "agent-policy", "scripted-overlay": "agent-overlay"}


def system_prompt(arm: str) -> str:
    arm = SCRIPTED_PROMPT.get(arm, arm)
    return "\n\n".join(ARM_PARTS.get(arm, ARM_PARTS["agent-default"]))


def session_message(i: int, n: int, date: str, transcript: str) -> str:
    """``Session {i} of {n}, {date}:`` (the date omitted when the dataset has none), a blank line, the transcript."""
    head = f"Session {i} of {n}, {date}:" if date else f"Session {i} of {n}:"
    return f"{head}\n\n{transcript}"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digests() -> dict[str, str]:
    out = {"INSTRUCTIONS": sha256(INSTRUCTIONS), "TASK": sha256(TASK), "POLICY": sha256(POLICY), "OVERLAY": sha256(OVERLAY)}
    out.update({f"system:{arm}": sha256(system_prompt(arm)) for arm in ARM_PARTS})
    return out
