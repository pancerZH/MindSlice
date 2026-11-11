# MindSlice

**Long-term memory for AI agents, kept as plain Markdown files you can read, edit and share.**

MindSlice gives an AI agent (Claude Code, or any app that supports MCP) a memory that lasts from one
conversation to the next. The agent looks things up when it needs them and writes down what it learns.
Everything lives in ordinary folders of Markdown files: open them in any editor, keep them in Git, or zip one
up and send it to a friend.

- **Your notes stay yours.** Point MindSlice at a folder you already have (Obsidian notes, a docs folder, a
  team handbook) and the agent can search it right away, with no conversion. What the agent learns goes into a
  separate folder of its own, and MindSlice never edits your folders: when you want to keep the agent's notes,
  it builds a new version next to them.
- **Some memory is always on.** Mark a note `load = "always"` (a persona, the language you want replies in,
  rules for every answer) and MindSlice supplies it as startup context to your connected agent. The chat app
  must pass that context to the model (see step 4). The agent can't change
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

#### With a local model through an agent app (Strata)

MindSlice doesn't care which model the agent runs on, so a model you serve yourself works too. With
Strata serving a local model (for example Qwen):

1. Start the model server: `strata launch`.
2. Point your app at it, for example Claude Code: `strata connect claude-code --write`. Strata can also set up
   opencode, Codex and others (run `strata connect` to list them). Add `--check` to confirm that the model
   can make tool calls, since that is how the agent reaches its memory.
3. Add MindSlice to that app as shown above (for Claude Code, the same `claude mcp add` command).

Small local models follow MindSlice's instructions less reliably than large hosted ones. To keep everything
they write under your review, add `--stage-writes` when you connect MindSlice:

```bash
claude mcp add mindslice -- mindslice -w ~/mindslice mcp --stage-writes
```

Every change the agent makes then waits for you in step 5.

**Chat in the app you connected.** `claude mcp add` connects MindSlice to Claude Code only. Strata's web
chat has its own MCP configuration (below), even when both apps use the same Qwen model.
`--stage-writes` controls review of memory writes; it does not connect other apps or control loading of
existing notes.

#### With Strata's web chat

Strata supports this directly; see its [Tools from MCP servers guide](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md#tools-from-mcp-servers).
The steps below were verified with Strata Terminal 0.1.58 and its Qwen web chat on Linux.

**1. Find the model configuration.** For a source installation, use `strata-<model>.json`. For an
installed Terminal launch, look at `source_config` in the matching profile under
`~/.config/strata/profiles/`. For example, a `launch-iq3_s-256k` profile points to
`~/.local/state/strata/launch/iq3_s-256k.json`.

Terminal 0.1.58 can regenerate that launch file from the installed model configuration. Add the MCP
entry to both the current launch file and its base model file (for example,
`~/.local/share/strata/install/strata-iq3_s.json`) so a future `strata launch` keeps it. Paths and model
names depend on your installation. Back up each file before editing it.

**2. Add MindSlice.** Merge this block into those JSON files, keeping the existing settings and any
other MCP servers. Replace `command` with the full path printed by `which mindslice`, and replace the
workspace path with the folder you initialized in step 1 above. Use absolute paths in the JSON:

```json
{
  "mcp_servers": {
    "mindslice": {
      "command": "/home/you/.local/bin/mindslice",
      "args": ["-w", "/home/you/mindslice", "mcp", "--stage-writes"]
    }
  }
}
```

**3. Restart and check the connection.** Stop the running Strata server, then start it with your usual
launch command. Refresh the web page and enable **Use tools from MCP servers** in chat settings.
In **Monitor**, MindSlice should be connected with four tools: `manifest`, `search`, `read`, and `write`.
Editing a configuration file or refreshing the page alone does not reload the server's MCP configuration.

**4. Load your preferences.** Strata 0.1.58's MCP client loads tools but does not forward MCP
`initialize.instructions` to the model. Begin each new chat with:

> Call `mindslice__manifest` first and follow the preferences in `always_loaded` for this conversation.

Confirm that an actual tool call appears in the chat and its result includes your notes. This retrieves
the current notes; `load = "always"` alone cannot make an app inject them automatically. The model can
then use MindSlice's search, read and write tools, with writes staged for review in step 5 below.

**If the model says the tool is unavailable:** check **Monitor** first. Strata's `/mcp` endpoint also
reports the loaded servers and tool count; `{"servers": [], "tools": 0}` means the running server has no
MCP tools configured. Check the active model's configuration and restart Strata. If MindSlice is listed
but failed to start, check the server log and the command/workspace paths. If it is connected with four
tools, refresh the page, enable the MCP toggle and retry in a new chat.

If the tool works but your note is missing, run `mindslice -w /your/workspace boot` and check that the
same workspace path is configured above. The note must be a `.md` file in `overlay/` or a mounted slice.

### 3. Add notes you already have

```bash
mindslice mount ~/notes
```

Any folder of Markdown files works as it is, and MindSlice only reads it. Each mounted folder gets a short name
(here `@notes`). Mount as many folders as you like.

### 4. Tell the agent what it should always know

Always-loaded notes can live in `overlay/` or **any mounted slice**. For a quick start, create
`~/mindslice/overlay/about-me.md`:

```markdown
+++
title = "How to talk to me"
load = "always"
+++

Reply in Simplified Chinese, keep answers short, and show code instead of describing it.
```

Check that MindSlice finds the note in the workspace you connected:

```bash
mindslice -w ~/mindslice boot
```

The output should contain your note. If your workspace is elsewhere, use that path in both the MCP
configuration and the command above.

To keep your preferences in a reusable slice instead, create a folder and save the same note as
`~/mindslice/slices/persona.slice/about-me.md`:

```bash
mkdir -p ~/mindslice/slices/persona.slice
# Save about-me.md in that folder, then mount it:
mindslice -w ~/mindslice mount ~/mindslice/slices/persona.slice --alias persona
mindslice -w ~/mindslice boot
```

Putting a folder under `slices/` does not activate it: **mount it once** to include its cards. A slice
can also live elsewhere on disk, and a plain folder of Markdown files needs no special manifest.
If relocating an existing note, remove its old overlay copy after confirming the mounted copy appears
in `boot`, so the same instructions are not loaded twice. Agent writes still go to `overlay/`; mounted
slices are read-only to the agent.

Over MCP, MindSlice includes these notes in its startup instructions and in the `manifest` tool result.
The app must pass the instructions or tool result to the model; registering an MCP server alone does not
guarantee that every app does this. Start a new session in the connected app after setup. If the note is
missing from the model's context, ask the agent to call MindSlice's `manifest` tool and read `always_loaded`.

Without MCP, start Claude Code with
`claude --append-system-prompt "$(mindslice -w ~/mindslice boot)"`, or copy the boot output into your web
chat's system prompt if it has one, or into the first message of a new conversation. This supplies the
notes for that conversation only; it does not enable memory search, saving, or automatic updates.

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

### 6. Turn what the agent learned into slices

Over time the agent's notes pile up in `~/mindslice/overlay/`. Every so often, move the good ones into slices.

**Start a new slice** from the agent's notes on one topic:

```bash
mindslice pack ~/mindslice/slices/python-tips.slice --prefix python/   # copies the notes under python/
mindslice mount ~/mindslice/slices/python-tips.slice                   # and moves them: the copies leave overlay/
```

**Add to a slice you already have.** Say you mounted a team handbook as `@handbook`, and the agent has since
corrected some of its notes and added to others. Bake those changes into a new version of the handbook:

```bash
mindslice bake @handbook --dry-run   # see which notes would move, and where the new version goes
mindslice bake @handbook             # build it, and mount it as @handbook in place of the old one
```

The new version is a copy of the handbook with the agent's notes added, in `~/mindslice/slices/` (or wherever
`--output` says). Your original folder is left exactly as it was, just no longer mounted: to go back, mount it
again. By default, bake takes the agent's notes that build on that slice; `--prefix python/` picks notes by
folder instead.

A slice is just a folder of Markdown files, so you can also write one by hand and mount it, or let an agent with
the [slice-builder skill](skills/slice-builder/SKILL.md) build one from your project's docs.

### 7. Share a slice

Share a slice folder however you like (Git, a zip file). Whoever receives it runs
`mindslice mount python-tips.slice`.

### Going further

- [Reference](docs/reference.md): the note format, every command and option, the MCP tools, and how search and
  replacement work.
- [The slice-builder skill](skills/slice-builder/SKILL.md): lets an agent turn project docs into a
  well-organized slice and keep it tidy.
- [Evaluations](docs/evaluations.md): benchmark results, and where MindSlice stops.
- [Design](MindSlice_design.md): the full design.

## Use cases

<!-- Specific, worked use cases go here. -->
