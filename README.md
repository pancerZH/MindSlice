# MindSlice

**Long-term memory for AI agents, kept as plain Markdown files you can read, edit and share.**

MindSlice gives an AI agent (Claude Code, or any app that supports MCP) a memory that lasts from one
conversation to the next. The agent looks things up when it needs them and writes down what it learns.
Everything lives in ordinary folders of Markdown files: open them in any editor, keep them in Git, or zip one
up and send it to a friend.

- **Your notes stay yours.** Point MindSlice at a folder you already have (Obsidian notes, a docs folder, a
  team handbook) and the agent can search it right away, with no conversion. MindSlice never changes that
  folder: what the agent learns goes into a separate folder of its own.
- **Some memory is always on.** Mark a note `load = "always"` (a persona, the language you want replies in,
  rules for every answer) and the agent reads it at the start of every conversation. The agent can't change
  these notes by itself: each change waits for your approval.
- **Old facts step aside.** When something changes, the agent records the new fact as replacing the old one,
  so the next search finds the current answer first.
- **Memory you can share.** Package a topic as a *slice* (just a folder) and anyone can plug it into their own
  agent.
- **Nothing extra to run.** No database server, no API key, no dependencies: Python 3.12 or newer, on Linux,
  macOS or Windows. Search works in any language, including Chinese, Japanese and Korean.

What you can use it for:

- A personal assistant that remembers your preferences, projects and plans between conversations.
- A coding agent that knows your project's conventions, past decisions and pitfalls.
- An agent with a character of its own, which you can share with others.
- Making the notes you already have searchable by your agent.
- A team handbook that every team member's agent can read.

## How to use

### Install

```bash
git clone https://github.com/pancerZH/MindSlice.git
cd MindSlice
pip install -e .
```

This installs the `mindslice` command.

### 1. Create your memory

```bash
mindslice init ~/mindslice
export MINDSLICE_WORKSPACE=~/mindslice   # tells the commands below where your memory is
```

Your memory is now the folder `~/mindslice`. What the agent learns goes into `~/mindslice/overlay/`, one
Markdown file per topic.

### 2. Connect your agent

For Claude Code:

```bash
claude mcp add mindslice -- mindslice -w ~/mindslice mcp
```

For other apps that support MCP, add this to their MCP settings (with your own path):

```json
{"mcpServers": {"mindslice": {"command": "mindslice", "args": ["-w", "/home/you/mindslice", "mcp"]}}}
```

If the app can't find the command, use the full path that `which mindslice` prints.

Then just talk to your agent. Tell it "Remember that I use uv, not pip", and in a later conversation ask "How
do I install packages in my projects?"

### 3. Add notes you already have

```bash
mindslice mount ~/notes
```

Any folder of Markdown files works as it is, and MindSlice only reads it. Each mounted folder gets a short name
(here `@notes`). Mount as many folders as you like.

### 4. Tell the agent what it should always know

Create a file `~/mindslice/overlay/about-me.md`:

```markdown
+++
title = "How to talk to me"
load = "always"
+++

Reply in Simplified Chinese, keep answers short, and show code instead of describing it.
```

The agent now reads this note at the start of every conversation. To see what it will read, run
`mindslice boot`. That command also works without MCP: start Claude Code with
`claude --append-system-prompt "$(mindslice boot)"`, or paste its output into any chat.

You can also just tell the agent "From now on, always answer in Chinese". The agent can then save a note like
this one, but the note waits for your approval (next step).

### 5. Review what the agent wants to change

Changes to always-on notes wait in a review area until you decide:

```bash
mindslice diff --patch    # see the proposed changes
mindslice apply           # accept them
mindslice discard         # or throw them away
```

Everything else the agent writes is saved directly as Markdown in `~/mindslice/overlay/`. You can open, edit or
delete any file there, and MindSlice picks up your changes automatically.

### 6. Share a slice

```bash
mindslice pack ~/shared/python-tips.slice --prefix python/
```

This copies the agent's notes under `python/` into a standalone folder. Share it however you like (Git, a zip
file); whoever receives it runs `mindslice mount python-tips.slice`.

### Going further

- [Reference](docs/reference.md): the note format, every command and option, the MCP tools, and how search and
  replacement work.
- [The slice-builder skill](skills/slice-builder/SKILL.md): lets an agent turn project docs into a
  well-organized slice and keep it tidy.
- [Evaluations](docs/evaluations.md): benchmark results, and where MindSlice stops.
- [Design](MindSlice_design.md): the full design.

## Use cases

<!-- Specific, worked use cases go here. -->
