# Uninstall or disconnect MindSlice

Revert harness MCP and session-start configurations cleanly, optionally uninstall the `mindslice` CLI, and **always ask before deleting any memory workspace on disk**.

## Step 1 - Inspect what is currently installed and connected

Before changing anything, check:

1. **Connected MCP instances and startup hooks/rules** in the active harness:
   - Look for any MCP server entry named `mindslice`, `mindslice-*`, or whose command/args invoke `mindslice ... mcp`.
   - Record each instance's **server name** (`<server_name>`) and **workspace path** (`<workspace>`, passed after `-w`).
   - Check matching startup hooks or global rules (e.g. `<server_name>-boot` / `mindslice-boot` in `~/.gemini/config/hooks.json`, rules in `~/.cursor/`, `~/.codex/AGENTS.md`, etc.).
2. **Workspace contents** for each discovered `<workspace>`:
   - Check whether `<workspace>/mounts.toml` exists, whether `<workspace>/overlay/` or `<workspace>/staging/` contains cards/drafts, and what external folders are listed in `<workspace>/mounts.toml`.
3. **CLI installation**:
   - Check `command -v mindslice`, `pipx list`, or a `.venv/bin/mindslice` inside a local MindSlice checkout.

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

Edit config files surgically so every other MCP server, hook, and setting stays valid JSON/TOML:

| Harness | Revert MCP configuration | Revert session-start hook / rule |
| :-- | :-- | :-- |
| **Claude Code** | Run `claude mcp remove <server_name>` (matching the scope it was added in: `--scope user`, `local`, or `project`). | None needed (unless the user added a custom `CLAUDE.md` rule for `<server_name>`). |
| **Antigravity (`agy` CLI / IDE / App)** | Run `agy mcp remove <server_name>` (or delete only `mcpServers.<server_name>` from `~/.gemini/config/mcp_config.json`). | Remove `<server_name>-boot` (or the `mindslice-boot` entry targeting `<workspace>`) from `~/.gemini/config/hooks.json`. Validate the remaining JSON; if `hooks.json` now has `{}` and had no other hooks, remove `hooks.json`. |
| **Cursor** | Remove `mcpServers.<server_name>` from `~/.cursor/mcp.json` and/or `.cursor/mcp.json`. | Remove any Cursor Rule added specifically for `<server_name>`. |
| **OpenAI Codex CLI** | Remove `[mcp_servers.<server_name>]` from `~/.codex/config.toml`. | If no MindSlice instances remain, remove the MindSlice reminder line from `~/.codex/AGENTS.md`. |
| **Strata (local models)** | Remove `mcp_servers.<server_name>` from both the active launch JSON (`~/.local/state/strata/launch/...`) and base model JSON (`~/.local/share/strata/install/...`), then remind the user to restart Strata. | If `<mindslice_bin> ... boot` was pasted into a web chat system prompt, remind the user to clear it. |
| **Other MCP apps** | Remove `<server_name>` from `mcpServers` in the app's MCP config file, keeping all sibling keys intact. | Remove any startup hook or global rule referencing `<server_name>` or `<workspace>`. |

## Step 4 - Uninstall CLI and/or delete workspace (only as confirmed)

1. **CLI uninstall (only if confirmed in Step 2)**:
   - If installed via `pipx`: run `pipx uninstall mindslice`.
   - If installed in a repo `.venv`: remove `.venv/` if requested, and remove any `PATH` or `MINDSLICE_WORKSPACE` export line added to `~/.bashrc` / `~/.zshrc` (leaving all other shell lines untouched).
2. **Workspace deletion (only if the user explicitly asked to delete `<workspace>` in Step 2)**:
   - **Safety check first**: verify `<workspace>` is not `$HOME` or `/`, and verify `<workspace>/mounts.toml` exists (`test -f "<workspace>/mounts.toml"`) so you never delete a non-MindSlice folder.
   - Check `<workspace>/mounts.toml` to ensure you only delete `<workspace>` itself and **never** touch any external mounted directory (such as `~/notes`).
   - Delete `<workspace>`.
   - If the user chose **not** to delete `<workspace>`, leave it untouched and confirm its path so they know where their Markdown files are kept.

## Step 5 - Verify clean state

1. Verify every edited JSON/TOML config file parses cleanly (e.g. `agy mcp list`, `claude mcp list`, or `python3 -m json.tool` / `tomllib`).
2. If the CLI was uninstalled, check `command -v mindslice` returns nothing.
3. Summarize what was reverted/uninstalled and whether `<workspace>` was preserved or deleted, and remind the user to start a new session (`/new` or restart the app) so the active session drops the disconnected tools.
