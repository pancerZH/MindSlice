# Uninstall or disconnect MindSlice

Revert harness MCP and session-start configurations cleanly, optionally uninstall the `mindslice` CLI, and **always ask before deleting any memory workspace on disk**.

## Step 1 - Inspect what is currently installed and connected

Before changing anything, check:

1. **Connected MCP instances and startup hooks/rules** in the active harness:
   - Look for any MCP server entry named `mindslice`, `mindslice-*`, or whose command/args invoke `mindslice ... mcp`.
   - Record each instance's **server name** (`<server_name>`) and **workspace path** (`<workspace>`, passed after `-w`).
   - Find everything else setup added for that instance: hooks that run `mindslice ... boot` (at session start and after context compaction), and always-on rules that tell the agent to call the instance's `manifest` tool.
2. **Workspace contents** for each discovered `<workspace>`:
   - Check whether `<workspace>/mounts.toml` exists, whether `<workspace>/overlay/` or `<workspace>/staging/` contains cards/drafts, and what external folders are listed in `<workspace>/mounts.toml`.
3. **CLI installation**:
   - Find the `mindslice` executable the harness configuration points to and how it was installed.

## Step 2 - Confirm with the user before removing anything (mandatory)

Present what you found and ask the user (in their language) to confirm three separate choices:

1. **Which MCP instance(s) to disconnect** — if multiple MindSlice instances are configured (e.g. `mindslice` and `mindslice-rpg`), ask whether to disconnect a specific instance or all of them.
2. **Whether to uninstall the `mindslice` CLI command** — keep it installed if they still have other MindSlice workspaces or want to use `mindslice` from the terminal.
3. **Whether to ALSO delete the memory workspace folder `<workspace>` on disk (default: keep it!)**:
   - Always state the exact `<workspace>` path and note if `overlay/`, `staging/`, or `<workspace>/slices/` has files.
   - Make clear that keeping `<workspace>` leaves all their plain Markdown notes intact on disk, while deleting `<workspace>` permanently removes `overlay/`, `staging/`, and `<workspace>/slices/`.
   - **Never delete external folders mounted via `mounts.toml`** (such as `~/notes` or external `.slice` folders outside `<workspace>`), even when deleting `<workspace>`.

Do not proceed to destructive steps until the user answers.

## Step 3 - Revert harness MCP and startup settings

Setup configures each harness with that harness's own mechanisms, so remove exactly what Step 1
found, using the harness's own commands for editing its configuration where it has them:

- **The MCP server entry** `<server_name>`, in every scope it was added to.
- **Hooks** that run `mindslice ... boot` for `<workspace>`, both session-start and post-compaction.
- **Always-on rules** added for `<server_name>` (calling `manifest` at session start or after compaction).
- **Anything pasted by hand**, such as `boot` output in a chat app's system prompt: remind the user to clear it.

Edit surgically so every other MCP server, hook, rule and setting stays valid; leave a config file
in place unless setup created it and it is now empty. If the app caches its configuration, tell the
user to restart it.

## Step 4 - Uninstall CLI and/or delete workspace (only as confirmed)

1. **CLI uninstall (only if confirmed in Step 2)**:
   - Uninstall it the way it was installed, and remove any `PATH` or `MINDSLICE_WORKSPACE` line that setup added to a shell profile, leaving every other line untouched.
2. **Workspace deletion (only if the user explicitly asked to delete `<workspace>` in Step 2)**:
   - **Safety check first**: verify `<workspace>` is not `$HOME` or `/`, and verify `<workspace>/mounts.toml` exists (`test -f "<workspace>/mounts.toml"`) so you never delete a non-MindSlice folder.
   - Check `<workspace>/mounts.toml` to ensure you only delete `<workspace>` itself and **never** touch any external mounted directory (such as `~/notes`).
   - Delete `<workspace>`.
   - If the user chose **not** to delete `<workspace>`, leave it untouched and confirm its path so they know where their Markdown files are kept.

## Step 5 - Verify clean state

1. Verify every edited config file still parses and the harness no longer lists `<server_name>` (its own list command, or a JSON/TOML parser).
2. If the CLI was uninstalled, check that `mindslice --version` no longer runs.
3. Summarize what was reverted/uninstalled and whether `<workspace>` was preserved or deleted, and remind the user to start a new session (`/new` or restart the app) so the active session drops the disconnected tools.
