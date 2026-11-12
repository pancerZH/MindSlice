# Getting started

[Home](../README.md) · [Connect your agent](integrations.md) · [Review and bake](workflow.md)

Python 3.12 or newer is required. MindSlice runs on Linux, macOS and Windows.
The shell examples below use Bash; on Windows, use the corresponding PowerShell paths and environment syntax.

## Let your agent set it up

Paste this into your coding agent (Claude Code, Antigravity, Cursor, Codex, or any agent with terminal access):

```text
Clone https://github.com/pancerZH/MindSlice.git (or use this repo if already cloned), read skills/mindslice-setup/SKILL.md, install MindSlice, connect it to this agent with automatic session-start loading, and walk me through seeding my initial memory.
```

Following [`skills/mindslice-setup/SKILL.md`](../skills/mindslice-setup/SKILL.md), the agent will:

1. Install `mindslice` and confirm **where to store your memory workspace** (default `~/mindslice`), **what to name the MCP instance** (default `mindslice`, or e.g. `mindslice-work` / `mindslice-rpg` if you keep separate memories), and **how you want to seed it**: connect an existing workspace/`.slice`, mount existing Markdown notes / distill project docs, or start from scratch with 2–3 plain-language questions.
2. Register the MCP server **plus** automatic session-start loading for your specific harness (such as a `SessionStart` hook when the client lazy-loads MCP instructions), so you don't have to paste a startup prompt into every chat.
3. Create and validate your initial cards so your next session starts with your memory ready.

To disconnect or uninstall later, paste:
`Read skills/mindslice-setup/uninstall.md in the MindSlice repo and revert my MindSlice setup` (the agent will ask whether to keep or delete your memory workspace folder).

## Manual installation

```bash
git clone https://github.com/pancerZH/MindSlice.git
cd MindSlice
pipx install -e .
```

This installs the `mindslice` command. If you don't have pipx yet, install it first (on Debian or Ubuntu:
`sudo apt install pipx && pipx ensurepath`, then open a new terminal).

Without pipx, use a virtual environment instead:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export PATH="$PWD/.venv/bin:$PATH"   # add this line to ~/.bashrc to keep it in new terminals
```

A plain `pip install` fails on many Linux systems (`externally-managed-environment`), because they keep
the system Python for the system's own packages.

## Create or import your memory

Initialize a workspace folder (or reuse one you already have):

```bash
mindslice init ~/mindslice
export MINDSLICE_WORKSPACE=~/mindslice   # tells the commands below where your memory is
```

Your memory is now `~/mindslice`. What the agent learns goes into `~/mindslice/overlay/`, one Markdown file per
topic. From here there are three ways to seed it:

- **Mount notes you already have.** Point MindSlice at any folder of Markdown files (Obsidian notes, a team
  handbook, a `docs/` folder); it indexes them as they are and never edits them:
  ```bash
  mindslice mount ~/notes   # mounted read-only as @notes; mount as many folders as you like
  ```
  To distill multiple source files or a single long document into one or more structured slices, point an agent
  at the [slice-builder skill](../skills/slice-builder/SKILL.md), or use its standalone
  [prompt template](../skills/slice-builder/prompt-template.md).
- **Mount a shared `.slice`.** If someone sent you a slice folder, run `mindslice mount path/to/topic.slice`.
- **Start from scratch, in conversation.** Leave `~/mindslice` empty and connect your agent ([connection guide](integrations.md)). When a
  workspace has no cards or mounted slices yet, MindSlice includes a cold-start onboarding prompt in its MCP
  startup instructions (and in `manifest()`), so you can greet your agent and describe your reply preferences,
  preferred tools, and current projects in plain words — the agent formats and writes the cards for you, and the
  onboarding prompt disappears once your first card is saved.

## Connect your agent

Follow the [connection guide](integrations.md) for your app, including session-start loading.
Then tell it: “Remember that I use uv, not pip.” In a later conversation, ask how to install packages.

## Standing preferences

You don't have to write standing notes by hand: just tell your connected agent *"From now on, reply in Simplified
Chinese, keep answers short, and show code instead of describing it."* The agent saves a `load = "always"` card
for your approval ([review changes](workflow.md#review-changes)).

Because everything is plain Markdown, you can also create or edit standing notes yourself in `overlay/` or **any
mounted slice** — for example `~/mindslice/overlay/about-me.md`:

```markdown
+++
title = "How to talk to me"
load = "always"
+++

Reply in Simplified Chinese, keep answers short, and show code instead of describing it.
```

Check what MindSlice supplies at session start:

```bash
mindslice -w ~/mindslice boot               # full session startup payload
mindslice -w ~/mindslice boot --cards-only  # just standing card content, as Markdown
```

To keep your preferences in a reusable slice instead, save the note under a slice folder and **mount it once**:

```bash
mkdir -p ~/mindslice/slices/persona.slice
# Save about-me.md in that folder, then mount it:
mindslice -w ~/mindslice mount ~/mindslice/slices/persona.slice --alias persona
mindslice -w ~/mindslice boot
```

Putting a folder under `slices/` does not activate it until mounted. A slice can also live elsewhere on disk, and
a plain folder of Markdown files needs no special manifest. If relocating an existing note, remove its old overlay
copy after confirming the mounted copy appears in `boot`, so the same instructions are not loaded twice. Agent
writes still go to `overlay/`; mounted slices are read-only to the agent.

Without MCP, start Claude Code with `claude --append-system-prompt "$(mindslice -w ~/mindslice boot --cards-only)"`, or copy
the `boot --cards-only` output into your web chat's system prompt or Saved Info. That supplies standing notes for the chat,
without live search or write-back.

Next: [review changes, bake versions and share slices](workflow.md).
