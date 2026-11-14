---
name: mindslice-setup
description: Install MindSlice, connect its MCP server to the agent harness you are running in, make the user's standing memory load automatically at session start and again after context compaction, seed memory by connecting a workspace, mounting slices or Markdown, using Forge for document conversion, or starting from a short conversation, and validate with `mindslice doctor`.
---

# mindslice-setup

Set up MindSlice end-to-end so the user never has to hand-edit MCP configuration, memorize card
frontmatter, or paste a startup prompt into a chat.

The user may have said no more than "read this file to finish setup". That is a request for the
whole procedure, in this order:

1. **Install** the `mindslice` command.
2. **Agree on the workspace and seed it**: ask where the memory should live and how to start it.
3. **Connect this harness**: its MCP server, and the user's standing memory at session start and
   after context compaction.
4. **Validate** with `mindslice doctor`, then hand off.

This skill gives you the goal of each step and the way to validate it. How your own harness defines
MCP servers, hooks and always-on rules is yours to work out from the harness itself.

**When something fails, go by the error report.** A failing `mindslice` command prints
`error [code]: message` on stderr, often with `Next:` steps; `mindslice doctor` prints a `Next:` line
under every failed check. Follow those, fix the cause and re-run, rather than working around the
failure or guessing at a configuration.

## What done looks like

1. The `mindslice` command is installed, and you know its absolute path (`<mindslice_bin>`).
2. A workspace exists at a location the user confirmed (`<workspace>`, absolute), seeded the way they chose.
3. This harness can call MindSlice's MCP server and sees its four tools: `manifest`, `search`, `read`, `write`.
4. The model receives the user's standing memory **at the start of every session and again after
   every context compaction**, with no action from the user.
5. `<mindslice_bin> -w <workspace> doctor` passes, and items 3 and 4 were seen to work in a **new
   session** of the harness: one you started yourself where the harness allows it, otherwise one the
   user runs from the steps you hand over. Until then setup is pending, not done.

## Step 1 - Install the command

MindSlice is a Python package on PyPI, named `mindslice` (`Python >= 3.12`, no runtime
dependencies). Reuse an existing `mindslice`; otherwise install it into an isolated environment in
whatever way suits this machine, for example `pipx install mindslice` or `uv tool install mindslice`.
`<mindslice_bin> --version` confirms it runs.
Apps and background processes often start with a minimal `PATH`, so use absolute paths for the
executable and the workspace in everything you configure.

## Step 2 - Confirm location and how to seed the workspace

**Do not create `~/mindslice` silently before asking.** Unless the user already specified them, ask once (in their language) to confirm two things together — offering sensible defaults so they can simply accept defaults or customize:

- **Workspace directory (`<workspace>`)**: where the memory folder should live on disk (suggest `~/mindslice` by default, or their chosen path such as `~/memories/work` or `~/worlds/doskvol`). Resolve it to an absolute path.
- **How to start**:

1. **Connect an existing MindSlice workspace**
   - If the supplied path has `mounts.toml`, use it directly as `<workspace>` and continue to Step 3.
     Do not reinitialize it or mount its root directory as a slice.
2. **Mount existing slices or Markdown folders**
   - Initialize the confirmed workspace only if needed (`<mindslice_bin> init <workspace>`).
   - Mount each provided `.slice` or notes directory (`<mindslice_bin> -w <workspace> mount <directory>`).
     Plain Markdown and YAML-frontmatter notes are indexed read-only as is; Forge is not needed.
3. **Distill source documents into cards with MindSlice-forge**
   - Follow [slice-builder](../slice-builder/SKILL.md), which runs
     [MindSlice-forge](https://github.com/pancerZH/MindSlice-forge).
   - For a new workspace, let Forge create `<workspace>` itself; do not initialize it first.
   - For an existing workspace, build in a separate new directory, then integrate the selected
     generated slices and their dependencies as the builder describes. Never point Forge at the
     existing workspace as its build output.
   - Continue to Step 3 using the resulting new workspace or the existing destination. Keep any
     sample coverage limit and content gaps visible; connecting MCP does not make a partial build complete.
4. **Start from scratch in plain language**
   - Initialize the confirmed path if needed (`<mindslice_bin> init <workspace>`).
   - Ask 2-3 brief, concrete questions in plain language — no syntax required from the user:
     - How should the agent communicate with you? (reply language, tone, conciseness, standing rules)
     - What tools, languages, or conventions do you use by default? (e.g. `uv` vs `pip`, test commands, formatting)
     - What projects or ongoing topics are you working on right now?
   - Turn their answers into clean atomic cards:
     - **Standing reply rules (`load = "always"`)**: keep short; confirm the summary with the user and write directly via CLI with `--load always --no-stage` (e.g. `prefs/communication`) so it is active immediately without requiring a separate `mindslice apply`.
     - **Topic cards (`load = "as-needed"`)**: one focused sub-topic per card in `@overlay`, named by durable slot (`tooling/python`, `projects/overview`), never by a transient value (`tooling/uv`), with 3-8 search `aliases`.

## Step 3 - Connect this harness

Merge into existing configuration; never overwrite other MCP servers, hooks or rules.

**MCP server.** Register a stdio server that runs `<mindslice_bin> -w <workspace> mcp`, available
wherever the user works with this harness unless they ask otherwise. Use the harness's own command
for adding a server where it has one, in a location its documentation names, and then confirm that
its own listing shows the server. An entry the harness does not list is not a finished registration,
even if it happens to load. Append `--stage-writes` when the user runs a small local model, so every
write it makes waits for their review.

Do not ask the user to choose a server name. Honor a name they already provided; otherwise reuse a
MindSlice entry that targets the confirmed workspace, or use `mindslice`. If that name belongs to
another instance, keep that instance and pick a free descriptive name such as `mindslice-work`.

**Standing memory.** `<mindslice_bin> -w <workspace> boot` prints the startup payload on stdout:
MindSlice's usage instructions, then the user's `load = "always"` cards. The model needs it in
context at two moments:

- **Session start**, before its first reply.
- **After each context compaction.** When the harness summarizes or truncates a long conversation,
  anything injected earlier as a message or tool result is gone, and the user's standing
  instructions go with it.

The MCP server also sends the payload as its `initialize` instructions, but what a harness does with
those is not something to assume: one puts them in the system prompt, another cuts them at a length,
another keeps them in a file the model never opens. You cannot see from this session what the model
of the next one will be given. So leave neither moment to server instructions. Configure both of
these, for every harness:

1. **A standing rule, always.** Every harness has always-on instructions, and they outlast a
   compaction. Add this to them, with the real server name:

   > MindSlice (the `<server_name>` MCP server) is this user's long-term memory. If its usage
   > instructions and its "Always-loaded memory" cards are not in your context, at the start of a
   > session or after the conversation was compacted or summarized, call its `manifest` tool before
   > you reply, then follow the `instructions` and `always_loaded` cards it returns.

   `manifest` returns the whole startup payload, so the rule is a complete delivery by itself. It is
   conditional, so it costs nothing where the payload arrived another way.
2. **A hook as well, where the harness has one.** A rule depends on the model following it; a hook
   does not. If the harness can run a command when a session starts and hand its output to the
   model, run `boot` there and pass its stdout in the form the hook expects. Do the same after a
   compaction: some harnesses have a separate event for it, others fire the session-start event
   again with a compaction reason, and where there is neither the rule covers it.

A payload that arrives twice costs a few thousand characters. A payload that does not arrive is a
failed setup. So do not drop either mechanism to avoid a duplicate. The one saving worth making
comes after Step 4 has shown, in a new session, that another delivery arrives whole (down to the
last standing card): then the hook can run `boot --cards-only`, the cards without the usage
instructions.

## Step 4 - Validate and hand off

Run `<mindslice_bin> -w <workspace> doctor`. It checks the runtime, workspace, mounts, cards, index,
startup payload and a real MCP handshake; exit code 1 means a check failed, and each failure prints
a `Next:` line. Fix every failure and explain remaining warnings.

`doctor` cannot see your harness. Two of its lines are about it, and both are settled only by a new
session:

- **`client_connection`** names the app that last started this workspace's MCP server and the tools
  it called; the server records this itself. `[PENDING]` means no app has. After the harness has
  reloaded its configuration and opened a session, it must name your harness. If it does not, the
  registration is not being loaded, whatever the configuration file says.
- **`[MANUAL] client_session`** lists the checks: the server and its four tools, the **startup
  check** (a temporary standing card holding a phrase the model cannot guess, asked for in a new
  session, then removed), a real memory lookup, and the standing memory after a compaction.

Before them, run every hook command you configured by hand and check its output is what the hook
expects.

**Start the new session yourself when the harness can.** Most command-line harnesses have a
one-shot, non-interactive mode that takes a prompt and prints the reply (see the harness's `--help`).
A session started that way loads the same MCP configuration, rules and hooks as one the user opens,
so it is a real test, and you can read its answer and its tool calls. Run the startup check through
it exactly as `doctor` prints it: plant the phrase, ask in the new session, read the result, remove
the card.

- The phrase comes back: standing memory reaches the model. Then ask the memory-lookup question the
  same way.
- `NONE`, or the model had to `search` or `read` for it: delivery failed. Fix Step 3 and ask again
  in another new session. Do not report setup as done on a configuration you have not seen work.

Where the harness has no way to start a session from here, say that setup is **pending acceptance**
and hand the user those same steps with the exact commands and prompt, instead of claiming it passed.
A compaction can rarely be triggered from outside a conversation: hand that check over unless the
harness has a command for it.

Then run `<mindslice_bin> -w <workspace> status` for the mounts, card counts and pending review you
report, and give a compact handoff in the user's language:

- State what is ready: workspace path, connected app/server name, slice/card counts and standing-card count. Distinguish built artifacts from successfully mounted slices.
- Summarize checks and any material gaps or pending proposals. Separate local engine checks, source/retrieval spot checks and actual client-session verification; passing one does not prove the others.
- Explain how to reconnect and open a fresh session, how standing context loads at session start and after compaction (the `manifest` rule, and the hook where there is one), which of the new-session checks you ran yourself with what result, and what remains unverified. Provide a standing-context check when applicable and a source-backed retrieval question for document imports. Reuse the builder's acceptance examples, with brief expected facts and links to source evidence; do not hand over questions whose answers the user has no way to check.
- Link the Forge report, ledgers and acceptance note for converted documents and the [review/bake workflow](../../docs/workflow.md). Mention `review` when proposals are pending; avoid a full command tutorial or a list of every card/configuration path. Keep slice paths, dependencies, detailed results and setup configuration details in the ledger when one exists.

Aim for a short summary, a few actionable checks and links to details. Do not repeat the builder's
entire report when this setup skill calls it. Be clear that active overlay memory is already saved;
bake creates reusable versions, and future standing-card edits wait for approval. For later
disconnection or removal, use [`uninstall.md`](uninstall.md).
