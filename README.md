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
  must pass that context to the model (see step 2 and step 3). The agent can't change
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

### Quick start: let your agent set it up

Paste this into your coding agent (Claude Code, Antigravity, Cursor, Codex, or any agent with terminal access):

```text
Clone https://github.com/pancerZH/MindSlice.git (or use this repo if already cloned), read skills/mindslice-setup/SKILL.md, install MindSlice, connect it to this agent with automatic session-start loading, and walk me through seeding my initial memory.
```

Following [`skills/mindslice-setup/SKILL.md`](skills/mindslice-setup/SKILL.md), the agent will:

1. Install `mindslice` and confirm **where to store your memory workspace** (default `~/mindslice`), **what to name the MCP instance** (default `mindslice`, or e.g. `mindslice-work` / `mindslice-rpg` if you keep separate memories), and **how you want to seed it**: connect an existing workspace/`.slice`, mount existing Markdown notes / distill project docs, or start from scratch with 2–3 plain-language questions.
2. Register the MCP server **plus** automatic session-start loading for your specific harness (such as a `SessionStart` hook when the client lazy-loads MCP instructions), so you don't have to paste a startup prompt into every chat.
3. Create and validate your initial cards so your next session starts with your memory ready.

To disconnect or uninstall later, paste:
`Read skills/mindslice-setup/uninstall.md in the MindSlice repo and revert my MindSlice setup` (the agent will ask whether to keep or delete your memory workspace folder).

---

### Manual setup

If you prefer to run the commands yourself (or are connecting a web chat UI without shell access):

#### Install

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

#### 1. Create or import your memory

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
  To distill a codebase's `README.md`, `CLAUDE.md` and `docs/` into a structured slice instead, point an agent
  at the [slice-builder skill](skills/slice-builder/SKILL.md).
- **Mount a shared `.slice`.** If someone sent you a slice folder, run `mindslice mount path/to/topic.slice`.
- **Start from scratch, in conversation.** Leave `~/mindslice` empty and connect your agent (step 2). When a
  workspace has no cards or mounted slices yet, MindSlice includes a cold-start onboarding prompt in its MCP
  startup instructions (and in `manifest()`), so you can greet your agent and describe your reply preferences,
  preferred tools, and current projects in plain words — the agent formats and writes the cards for you, and the
  onboarding prompt disappears once your first card is saved.

#### 2. Connect your agent

**Claude Code** (forwards MindSlice's startup instructions and always-loaded notes automatically):

```bash
claude mcp add --scope user mindslice -- mindslice -w ~/mindslice mcp
```

**Google Antigravity (`agy` CLI / IDE)** — add MindSlice to `~/.gemini/config/mcp_config.json` (use absolute
paths; run `which mindslice` for the binary path):

```json
{
  "mcpServers": {
    "mindslice": {
      "command": "/home/you/.local/bin/mindslice",
      "args": ["-w", "/home/you/mindslice", "mcp"]
    }
  }
}
```

Because Antigravity lazy-loads MCP server instructions on demand, add a `SessionStart` hook in
`~/.gemini/config/hooks.json` so every new session receives MindSlice's instructions and `load = "always"` notes
automatically without typing a manual startup prompt:

```json
{
  "mindslice-boot": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 -c 'import json, subprocess; out = subprocess.run([\"/home/you/.local/bin/mindslice\", \"-w\", \"/home/you/mindslice\", \"boot\", \"--mcp-instructions\"], capture_output=True, text=True).stdout.strip(); print(json.dumps({\"injectSteps\": [{\"systemMessage\": {\"systemMessage\": out}}]} if out else {}))'"
      }
    ]
  }
}
```

**Other apps that support MCP** — add this to their MCP settings (with absolute paths):

```json
{"mcpServers": {"mindslice": {"command": "/home/you/.local/bin/mindslice", "args": ["-w", "/home/you/mindslice", "mcp"]}}}
```

If your app does not automatically inject MCP `initialize.instructions` into the model's context, wire
`mindslice -w /home/you/mindslice boot --mcp-instructions` into its startup hook / system prompt, or add a one-line
global rule instructing the agent to call MindSlice's `manifest` tool at session start.

Then just talk to your agent. Tell it "Remember that I use uv, not pip", and in a later conversation ask "How
do I install packages in my projects?"

##### With a local model through an agent app (Strata)

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

Every change the agent makes then waits for you in step 4.

**Chat in the app you connected.** `claude mcp add` connects MindSlice to Claude Code only. Strata's web
chat has its own MCP configuration (below), even when both apps use the same Qwen model.
`--stage-writes` controls review of memory writes; it does not connect other apps or control loading of
existing notes.

##### With Strata's web chat

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
then use MindSlice's search, read and write tools, with writes staged for review in step 4 below.

**If the model says the tool is unavailable:** check **Monitor** first. Strata's `/mcp` endpoint also
reports the loaded servers and tool count; `{"servers": [], "tools": 0}` means the running server has no
MCP tools configured. Check the active model's configuration and restart Strata. If MindSlice is listed
but failed to start, check the server log and the command/workspace paths. If it is connected with four
tools, refresh the page, enable the MCP toggle and retry in a new chat.

If the tool works but your note is missing, run `mindslice -w /your/workspace boot` and check that the
same workspace path is configured above. The note must be a `.md` file in `overlay/` or a mounted slice.

#### 3. Tell the agent what it should always know

You don't have to write standing notes by hand: just tell your connected agent *"From now on, reply in Simplified
Chinese, keep answers short, and show code instead of describing it."* The agent saves a `load = "always"` card
for your approval (step 4).

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
mindslice -w ~/mindslice boot                     # just the always-loaded cards, as Markdown
mindslice -w ~/mindslice boot --mcp-instructions  # full MCP startup instructions + always-loaded cards
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

Without MCP, start Claude Code with `claude --append-system-prompt "$(mindslice -w ~/mindslice boot)"`, or copy
the `boot` output into your web chat's system prompt or Saved Info. That supplies standing notes for the chat,
without live search or write-back.

#### 4. Review what the agent wants to change

Changes to always-on notes (and all writes when `--stage-writes` is enabled) wait in a review area until you decide:

```bash
mindslice diff --patch    # see the proposed changes
mindslice apply           # accept them
mindslice discard         # or throw them away
```

Everything else the agent writes is saved directly as Markdown in `~/mindslice/overlay/`. You can open, edit or
delete any file there, and MindSlice picks up your changes automatically.

#### 5. Turn what the agent learned into slices

Over time the agent's notes pile up in `~/mindslice/overlay/`. Every so often, move the good ones into slices.

**Start a new slice** from the agent's notes on one topic:

```bash
mindslice bake @python-tips --prefix python/   # creates and mounts the slice, retiring the overlay copies
```

`--prefix` selects overlay card paths and is required when the alias is new. Use `--output` to choose
the output directory. An explicit `--prefix ''` selects all overlay cards.

**Add to a slice you already have.** Say you mounted a team handbook as `@handbook`, and the agent has since
corrected some of its notes and added to others. Bake those changes into a new version of the handbook:

```bash
mindslice bake @handbook --dry-run   # see which notes would move, and where the new version goes
mindslice bake @handbook             # build it, and mount it as @handbook in place of the old one
```

The new version is a copy of the handbook with the agent's notes added, in `~/mindslice/slices/` (or wherever
`--output` says). Your original folder is left exactly as it was, just no longer mounted: to go back, mount it
again. By default, bake takes the agent's notes that build on that slice; `--prefix python/` picks notes by
folder instead. For example, `mindslice bake @handbook --prefix python/ --output ./handbook-next.slice`
keeps the alias and mount settings while switching to the new directory.

A slice is just a folder of Markdown files, so you can also write one by hand and mount it, or let an agent with
the [slice-builder skill](skills/slice-builder/SKILL.md) build one from your project's docs.

#### 6. Share a slice

Share a slice folder however you like (Git, a zip file). Whoever receives it runs
`mindslice mount python-tips.slice`. Baking also supports `--output python-tips.zip` or `.tar.gz`: it
writes the archive and mounts a directory under `~/mindslice/slices/`. The result reports both paths.

### Going further

- [Reference](docs/reference.md): the note format, every command and option, the MCP tools, and how search and
  replacement work.
- [The mindslice-setup skill](skills/mindslice-setup/SKILL.md) (and [uninstall guide](skills/mindslice-setup/uninstall.md)):
  lets an agent install MindSlice, configure MCP and session-start loading for its own harness, walk you through
  seeding initial memory, or cleanly revert settings later.
- [The slice-builder skill](skills/slice-builder/SKILL.md): lets an agent turn project docs into a
  well-organized slice and keep it tidy.
- [Evaluations](docs/evaluations.md): benchmark results, and where MindSlice stops.
- [Design](MindSlice_design.md): the full design.

## Use cases

<!-- Specific, worked use cases go here. -->
