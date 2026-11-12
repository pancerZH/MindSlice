---
name: mindslice-setup
description: Install MindSlice, connect its MCP server to the agent harness you are running in, make the user's standing memory load automatically at session start and again after context compaction, seed initial memory (existing workspace/slice, existing notes/docs, or a short conversation), and validate with `mindslice doctor`.
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
5. `<mindslice_bin> -w <workspace> doctor` passes, and you confirmed items 3 and 4 in the harness itself.

## Step 1 - Install the command

MindSlice is a Python package (`Python >= 3.12`, no runtime dependencies) installed from its
repository checkout. Reuse an existing `mindslice`; otherwise install it into an isolated
environment in whatever way suits this machine. `<mindslice_bin> --version` confirms it runs.
Apps and background processes often start with a minimal `PATH`, so use absolute paths for the
executable and the workspace in everything you configure.

## Step 2 - Confirm location and how to seed the workspace

**Do not create `~/mindslice` silently before asking.** Unless the user already specified them, ask once (in their language) to confirm two things together — offering sensible defaults so they can simply accept defaults or customize:

- **Workspace directory (`<workspace>`)**: where the memory folder should live on disk (suggest `~/mindslice` by default, or their chosen path such as `~/memories/work` or `~/worlds/doskvol`). Resolve it to an absolute path.
- **How to start**:

1. **Connect an existing MindSlice workspace or `.slice`**
   - If `<workspace>` already has `mounts.toml`, open it directly; otherwise run `<mindslice_bin> init <workspace>`.
   - Mount any `.slice` folder(s) the user provides (`<mindslice_bin> -w <workspace> mount <slice_path>`).
2. **Import existing Markdown notes or project docs**
   - Initialize the confirmed path if needed (`<mindslice_bin> init <workspace>`).
   - **Plain Markdown / Obsidian notes folder**: mount it directly (`<mindslice_bin> -w <workspace> mount <notes_dir>`). MindSlice indexes plain `.md` and YAML-frontmatter notes read-only with no conversion.
   - **Source material to distill (several project/lore files, or one long handbook/specification)**: follow [`../slice-builder/SKILL.md`](../slice-builder/SKILL.md) with `<workspace>/slices/` as the output root and this workspace as the one to seed; it covers building, checking and mounting the slices.
3. **Start from scratch in plain language**
   - Initialize the confirmed path (`<mindslice_bin> init <workspace>`).
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
wherever the user works with this harness unless they ask otherwise. Append `--stage-writes` when
the user runs a small local model, so every write it makes waits for their review.

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

For each moment, use the first of these your harness supports:

1. **Server instructions.** The MCP server already sends the payload as its `initialize` instructions.
   If the harness puts those in the model's system prompt, session start is covered. Compaction is
   covered only if that system prompt survives it; check, do not assume. The instructions also tell
   the model to call `manifest` again after a compaction.
2. **A hook.** Run `boot` from the session-start hook and the post-compaction hook, and pass its
   stdout to the model in the form the hook expects. Some harnesses have a separate event for
   compaction; others fire the session-start event again with a compaction reason.
3. **A standing rule.** Without a hook for that moment, add a rule to the harness's always-on
   instructions: call the `<server_name>` `manifest` tool before the first reply of a session and
   again right after the conversation is compacted, then follow its `always_loaded` cards.

Do not deliver the payload twice at the same moment. Where server instructions already arrive, skip
the session-start hook, and use `boot --cards-only` (the cards without the usage instructions) in
the post-compaction hook. Add that hook even then: cards that changed mid-session reach the model
in tool results, which compaction discards.

## Step 4 - Validate and hand off

Run `<mindslice_bin> -w <workspace> doctor`. It checks the runtime, workspace, mounts, cards, index,
startup payload and a real MCP handshake; exit code 1 means a check failed, and each failure prints
a `Next:` line. Fix every failure and explain remaining warnings.

`doctor` cannot see your harness: it always ends with a `[MANUAL] client_session` item. Confirm that
part yourself:

- **The server is connected**: the harness lists `<server_name>` with four tools, started by the
  same `<mindslice_bin>` you installed.
- **Each hook works**: run the configured command by hand and check its output is what the hook expects.
- **A fresh session has the standing memory** before any tool call. Compare what the model reports
  with `boot --cards-only`.
- **Compaction keeps it**: if the harness can compact on request, do so in a test conversation and
  check the standing cards are still there.

The [first-session checklist](../../docs/getting-started.md#verify-your-first-session) covers the
last two, with an actual memory lookup. If you cannot observe a new session or a compaction from
here, hand that check to the user explicitly instead of claiming it passed.

Then run `<mindslice_bin> -w <workspace> status` for the mounts, card counts and pending review you
report, and give a compact handoff in the user's language:

- State what is ready: workspace path, connected app/server name, slice/card counts and standing-card count. Distinguish built artifacts from successfully mounted slices.
- Summarize checks and any material gaps or pending proposals. Separate local engine checks, source/retrieval spot checks and actual client-session verification; passing one does not prove the others.
- Explain how to reconnect and open a fresh session, how standing context loads at session start and after compaction (server instructions, hook, or the `manifest` rule), and what remains unverified. Provide a standing-context check when applicable and a source-backed retrieval question for document imports. Reuse the builder's acceptance examples, with brief expected facts and links to source evidence; do not hand over questions whose answers the user has no way to check.
- Link the build ledger for document imports and the [review/bake workflow](../../docs/workflow.md). Mention `review` when proposals are pending; avoid a full command tutorial or a list of every card/configuration path. Keep slice paths, dependencies, detailed results and setup configuration details in the ledger when one exists.

Aim for a short summary, a few actionable checks and links to details. Do not repeat the builder's
entire report when this setup skill calls it. Be clear that active overlay memory is already saved;
bake creates reusable versions, and future standing-card edits wait for approval. For later
disconnection or removal, use [`uninstall.md`](uninstall.md).
