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

1. Install `mindslice` and confirm **where to store your memory workspace** (default `~/mindslice`) and **how you want to seed it**: connect an existing workspace, mount slices or Markdown unchanged, convert documents with optional MindSlice-forge, or start from scratch with 2–3 plain-language questions. The MCP instance is named `mindslice` unless you ask for another name (e.g. `mindslice-work` if you keep separate memories).
2. Register the MCP server and make your standing notes load **at session start and again after context compaction**: an always-on rule in every app, plus a hook where the app has one, so you never paste a startup prompt into a chat. The skill is the same for every app; the agent works out the configuration for the one it runs in.
3. Verify the selected memory, validate with `mindslice doctor`, and check a new session: it runs that check itself when the app can start one from the shell, and otherwise tells you what is left to check.

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

Choose how you want to start. MindSlice's basic paths work without Forge or an agent harness.

### Empty memory, existing workspace, or direct mounting

For a new empty workspace:

```bash
mindslice init ~/mindslice
export MINDSLICE_WORKSPACE=~/mindslice
```

For an existing workspace, set `MINDSLICE_WORKSPACE` to its path (or use `mindslice -w /path/to/workspace`);
no initialization is needed. Connect that workspace directly rather than mounting its root into another one.

- **Mount Markdown as is:** `mindslice mount ~/notes`. Plain Markdown and YAML-frontmatter notes
  are indexed read-only without conversion. You can mount several folders.
- **Mount shared slices:** `mindslice mount /path/to/topic.slice`. Mount individual slice directories,
  not a parent directory containing several slices or an entire workspace.
- **Start in conversation:** [connect your agent](#connect-your-agent) and describe your preferences,
  tools and projects. Empty workspaces include a cold-start hint in MCP startup instructions and
  `manifest()`; it disappears after the first card is saved or a slice is mounted. New learning
  goes into the workspace's `overlay/`.

### Convert source documents with Forge

[MindSlice-forge](https://github.com/pancerZH/MindSlice-forge) turns one long document or many files
into topic cards, handling chunks, fresh agent sessions, recorded searches, repairs and resume.
Install it separately when you want this conversion; it needs `mindslice`, `git` and an authenticated
agent harness. The [builder skill](../skills/slice-builder/SKILL.md) guides the process. Its
[conversion prompt template](../skills/slice-builder/prompt-template.md) can also be passed directly
to Forge's CLI.

For a **new workspace**, let Forge create it. Do not run `mindslice init` at that destination first:

```bash
# Select the actual source paths and model; keep the prompt outside the source directory.
mindslice-forge ./selected-sources --prompt ./conversion-prompt.md \
  --harness agy --model <model-id> -o ./knowledge.workspace
mindslice -w ./knowledge.workspace validate
export MINDSLICE_WORKSPACE="$PWD/knowledge.workspace"
```

Then [connect your agent](#connect-your-agent) to that workspace. Select allowed input files or an
allowed snapshot before running Forge: its recursive scan does not enforce repository ignore rules
or forbidden-directory markers, even with `--dry-run`.

For an **existing workspace**, build into a separate new directory, inspect the generated
`slices/*.slice`, their aliases and dependencies, and mount the selected slices in the existing
workspace. For example, if Forge produced `handbook.slice` with an unused `@handbook` alias:

```bash
mindslice -w ~/mindslice mount /path/to/knowledge.workspace/slices/handbook.slice \
  --precedence 50 --role curated
mindslice -w ~/mindslice validate
```

Keep those mounted paths stable. If you will rebuild the Forge output, first copy the slices to
new durable library directories and mount the copies. Preserve cross-slice aliases and include
their dependencies. Do not overwrite existing slices to resolve a naming collision.

The same Forge command resumes a build; `--sample N` produces a partial trial. Keep the sibling
`knowledge.workspace.forge/` directory while resuming or inspecting evidence. Its report and ledgers
describe coverage and checks. Independently check representative facts with search/read: successful
validation does not guarantee that the model preserved every fact.

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
compaction drops what was injected earlier as a message or tool result.

The server already sends that payload as its MCP instructions, but apps differ in what they do with
it: some show it to the model, some cut it at a length, some keep it in a file the model never
opens. Do not count on it. Set up both of these:

- **An always-on rule**, in the app's standing instructions file (every app has one, and it
  survives compaction):

  ```text
  MindSlice (the `mindslice` MCP server) is this user's long-term memory. If its usage instructions
  and its "Always-loaded memory" cards are not in your context, at the start of a session or after
  the conversation was compacted or summarized, call its `manifest` tool before you reply, then
  follow the `instructions` and `always_loaded` cards it returns.
  ```

  `manifest` returns the whole startup payload, so this works in any app, and it does nothing where
  the payload already arrived.
- **A hook, where the app has one**, that runs `boot` at session start (and after compaction, if
  there is an event for it) and passes its output to the model. A hook does not depend on the model
  following a rule.

A duplicate costs a few thousand characters; a missing payload means your standing notes are not in
effect. Trim only after the [new-session check](#verify-your-first-session) passes.

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

Two lines are about your app. `client_connection` names the app that last started this workspace's
MCP server and the tools it called (the server records this in `.cache/`); it stays `[PENDING]` until
an app really connects, whatever its configuration file says. `[MANUAL] client_session` prints the
new-session checks below with your workspace filled in.

**Local checks passing does not prove your app loaded memory into the model.** Finish with
a new conversation in the connected app. If the app can run a one-shot session from the shell,
that counts, and its output is easier to inspect:

1. Restart/reconnect the app as needed, open a conversation, and run `doctor` again:
   `client_connection` should name the app.
2. **Startup check.** Plant a phrase the model cannot guess as a temporary standing note:
   ```bash
   mindslice -w ~/mindslice write setup-check/startup --load always --no-stage \
     --summary "The MindSlice startup check phrase is amber maple 47." --reason "Temporary setup check."
   ```
   In a **new** conversation send only: *"What is the MindSlice startup check phrase? Answer from
   what you were given for this session; do not search or read memory for it. Say NONE if you do not
   have it."* The phrase means your standing notes reach the model. `NONE`, or a `search`/`read`
   call, means they do not: check how the app delivers them ([Connect your agent](#connect-your-agent)).
   Then remove the note:
   ```bash
   mindslice -w ~/mindslice write setup-check/startup --op delete --no-stage --reason "Setup check complete."
   ```
3. Ask about an ordinary saved fact without repeating its answer. Confirm an actual MindSlice
   `search`/`read` call and the expected card address in its result. This verifies retrieval
   independently of startup loading.
4. Open another new conversation and repeat the fact lookup. No source text or previous
   chat should need to be pasted again.
5. In a long conversation, let the app compact its context (or trigger it, if the app has a
   command for that) and ask for your standing reply preferences again. They should still be
   there: compaction drops what was injected at session start unless the app reloads it.

If you need a disposable fact for step 3, choose an unused card ID and write it explicitly:

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
