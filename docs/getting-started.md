# Getting started

[Home](../README.md) · [Review and bake](workflow.md)

Python 3.12 or newer is required. MindSlice runs on Linux, macOS and Windows.
The shell examples below use Bash; on Windows, use the corresponding PowerShell paths and environment syntax.

## Let your agent set it up

Paste this into your coding agent (Claude Code, Antigravity, Cursor, Codex, or any agent with terminal access):

```text
Clone https://github.com/pancerZH/MindSlice.git (or use this repo if already cloned).
Read skills/mindslice-setup/SKILL.md to finish setup.
```

Following [`skills/mindslice-setup/SKILL.md`](../skills/mindslice-setup/SKILL.md), the agent will:

1. Install `mindslice` and confirm **where to store your memory workspace** (default `~/mindslice`) and **how you want to seed it**: connect an existing workspace/`.slice`, mount existing Markdown notes / distill project docs, or start from scratch with 2–3 plain-language questions. The MCP instance is named `mindslice` unless you ask for another name (e.g. `mindslice-work` if you keep separate memories).
2. Register the MCP server and make your standing notes load **at session start and again after context compaction**, using whatever its own app provides (server instructions, hooks or an always-on rule), so you never paste a startup prompt into a chat. The skill states the goal; the agent works out the configuration for the app it runs in.
3. Create your initial cards, validate with `mindslice doctor`, and tell you what is left to check in a new session.

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
- **Start from scratch, in conversation.** Leave `~/mindslice` empty and [connect your agent](#connect-your-agent). When a
  workspace has no cards or mounted slices yet, MindSlice includes a cold-start onboarding prompt in its MCP
  startup instructions (and in `manifest()`), so you can greet your agent and describe your reply preferences,
  preferred tools, and current projects in plain words — the agent formats and writes the cards for you, and the
  onboarding prompt disappears once your first card is saved.

## Connect your agent

The agent-led setup above does this for you. By hand, your app needs two things, both configured
with absolute paths (`which mindslice` prints the executable's):

**1. The MCP server.** Register a stdio MCP server that runs `mindslice -w /path/to/workspace mcp`.
Most apps accept an entry of this shape in their MCP settings:

```json
{"mcpServers": {"mindslice": {"command": "/home/you/.local/bin/mindslice", "args": ["-w", "/home/you/mindslice", "mcp"]}}}
```

The registration applies to that app only. With a small local model, append `"--stage-writes"` to
`args` so every change the agent makes waits for you in the [review workflow](workflow.md#review-changes).

**2. Your standing notes, at session start and after compaction.** The model needs the output of
`mindslice -w /path/to/workspace boot` (usage instructions plus your `load = "always"` notes) before
its first reply, and again whenever the app summarizes or truncates a long conversation, because
compaction drops what was injected earlier as a message or tool result. Use the first of these your
app supports:

- **MCP instructions in the system prompt.** The server already sends that payload as its MCP
  instructions. If the app shows them to the model in a system prompt that survives compaction,
  nothing more is needed.
- **A hook** that runs `boot` at session start and after compaction and passes its output to the
  model. Use `boot --cards-only` where the usage instructions are already in the system prompt.
- **An always-on rule** telling the agent to call MindSlice's `manifest` tool before its first reply
  and again right after a compaction, then follow its `always_loaded` notes.

If a `mindslice` command fails while you set this up, read its error, then run
`mindslice -w /path/to/workspace doctor`: each failed check prints a `Next:` line.
Then tell the agent: “Remember that I use uv, not pip.” In a later conversation, ask how to install packages.

## Verify your first session

Run the local checks after connecting the app:

```bash
mindslice -w ~/mindslice doctor
```

`doctor` checks the runtime, mount directories, cards, synchronized index, startup payload,
and the real MCP stdio handshake and `manifest` call. It does not change your app configuration
or create test memories. Normal index synchronization and interrupted-transaction recovery still
apply. `doctor --json` provides the report for scripts; exit code 1 means a local check failed.
Warnings include pending standing-card changes that have not taken effect.

**Local checks passing does not prove your app loaded memory into the model.** Finish with
a new conversation in the connected app:

1. Choose a standing preference and an ordinary fact already saved during setup. Check that
   they are active with `status`; accept any intended pending cards with `review` first.
2. Restart/reconnect the app as needed and start a fresh conversation. Ask which standing
   reply preferences it received at startup, before using any tools. Compare with
   `mindslice -w ~/mindslice boot --cards-only` and, where available, the client's context/hook
   logs. A model's claim alone is not proof of injection.
3. Ask about the saved fact without repeating its answer. Confirm an actual MindSlice
   `search`/`read` call and the expected card address in its result. This verifies retrieval
   independently of startup loading.
4. Open another new conversation and repeat the fact lookup. No source text or previous
   chat should need to be pasted again.
5. In a long conversation, let the app compact its context (or trigger it, if the app has a
   command for that) and ask for your standing reply preferences again. They should still be
   there: compaction drops what was injected at session start unless the app reloads it.

If you need a disposable fact for this check, choose an unused card ID and write it explicitly:

```bash
mindslice -w ~/mindslice write setup-check/first-session \
  --summary "The setup verification phrase is amber maple 47." --reason "Temporary setup check."
```

Ask the new conversation for the setup verification phrase, then remove only this test card:

```bash
mindslice -w ~/mindslice write setup-check/first-session --op delete --reason "Setup check complete."
```

If retrieval works but standing preferences are missing, at session start or after compaction,
check how the app delivers them ([Connect your agent](#connect-your-agent)). If both fail, compare the executable and
workspace paths in that app with the workspace reported by `doctor`.

## Standing preferences

For a customizable policy on when the agent should record information proactively, choose the
[English or Chinese standing-card example](../examples/README.md#proactive-memory-policy).
The default startup instructions already encourage proactive writes; the optional card expresses
your workspace's recording preferences. Choose one language version rather than loading both.

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
