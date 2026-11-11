---
name: mindslice-setup
description: Install MindSlice, wire its MCP server and automatic session-start boot into the active agent harness (Claude Code, Antigravity, Cursor, Codex, Strata, or generic MCP apps), and guide the user through seeding initial memory from an existing workspace/slice, existing notes/docs, or a short plain-language conversation.
---

# mindslice-setup

Set up MindSlice end-to-end so the user never has to hand-edit MCP JSON, memorize card frontmatter, or paste a manual startup prompt into every chat.

## Step 1 - Locate or install `mindslice`

1. Check whether `mindslice` is already installed (`command -v mindslice` or `~/.local/bin/mindslice`).
2. If not installed and you are inside (or can clone) the MindSlice repository (`Python >= 3.12` required):
   - Prefer `pipx install -e .` if `pipx` is available;
   - Otherwise create a virtualenv in the repo: `python3 -m venv .venv && .venv/bin/pip install -e .`.
3. Record the **absolute path** to the `mindslice` executable (`<mindslice_bin>`). GUI apps and background daemons often run with a minimal `PATH`, so always use `<mindslice_bin>` and absolute workspace paths in MCP and hook configs.

## Step 2 - Confirm location, name, and how to seed the workspace

**Do not create `~/mindslice` silently before asking.** Unless the user already specified them, ask once (in their language) to confirm three things together — offering sensible defaults so they can simply accept defaults or customize:

- **Workspace directory (`<workspace>`)**: where the memory folder should live on disk (suggest `~/mindslice` by default, or their chosen path such as `~/memories/work` or `~/worlds/doskvol`). Resolve it to an absolute path.
- **Instance / MCP server name (`<server_name>`)**: the name registered in MCP and startup hooks (default `mindslice`, or e.g. `mindslice-rpg` / `mindslice-work` if they want multiple separate memory instances; if an entry with that name already exists in the harness config, ask whether to update it in place or register a new name).
- **How to start**:

1. **Connect an existing MindSlice workspace or `.slice`**
   - If `<workspace>` already has `mounts.toml`, open it directly; otherwise run `<mindslice_bin> init <workspace>`.
   - Mount any `.slice` folder(s) the user provides (`<mindslice_bin> -w <workspace> mount <slice_path>`).
2. **Import existing Markdown notes or project docs**
   - Initialize the confirmed path if needed (`<mindslice_bin> init <workspace>`).
   - **Plain Markdown / Obsidian notes folder**: mount it directly (`<mindslice_bin> -w <workspace> mount <notes_dir>`). MindSlice indexes plain `.md` and YAML-frontmatter notes read-only with no conversion.
   - **Project or worldbuilding docs (`README.md`, `CLAUDE.md`, `docs/`, ADRs, lore files)**: read [`../slice-builder/SKILL.md`](../slice-builder/SKILL.md), distill the durable knowledge into `<workspace>/slices/<topic>.slice/`, validate it, and mount it (`--precedence 50 --role curated`).
3. **Start from scratch in plain language**
   - Initialize the confirmed path (`<mindslice_bin> init <workspace>`).
   - Ask 2-3 brief, concrete questions in plain language — no syntax required from the user:
     - How should the agent communicate with you? (reply language, tone, conciseness, standing rules)
     - What tools, languages, or conventions do you use by default? (e.g. `uv` vs `pip`, test commands, formatting)
     - What projects or ongoing topics are you working on right now?
   - Turn their answers into clean atomic cards:
     - **Standing reply rules (`load = "always"`)**: keep short; confirm the summary with the user and write directly via CLI with `--load always --no-stage` (e.g. `prefs/communication`) so it is active immediately without requiring a separate `mindslice apply`.
     - **Topic cards (`load = "as-needed"`)**: one focused sub-topic per card in `@overlay`, named by durable slot (`tooling/python`, `projects/overview`), never by a transient value (`tooling/uv`), with 3-8 search `aliases`.

## Step 3 - Connect MCP and automatic session-start loading

Detect which agent harness you are running in (or ask if ambiguous). Always **merge** into existing config files using `<server_name>` (default `mindslice`) — never clobber other MCP servers or hooks.

| Harness | MCP configuration | Automatic session-start loading (no manual greeting) |
| :-- | :-- | :-- |
| **Claude Code** | `claude mcp add --scope user <server_name> -- <mindslice_bin> -w <workspace> mcp` | Automatic: Claude Code forwards MCP `initialize.instructions` (which includes MindSlice's rules and `load = "always"` cards) into the session prompt. |
| **Antigravity (`agy` CLI / IDE / App)** | Merge `mcpServers.<server_name>` (`command`: `<mindslice_bin>`, `args`: `["-w", "<workspace>", "mcp"]`) into `~/.gemini/config/mcp_config.json`. | Antigravity lazy-loads MCP `instructions.md`. Add a `<server_name>-boot` `SessionStart` hook in `~/.gemini/config/hooks.json` (template below) running `<mindslice_bin> -w <workspace> boot --mcp-instructions` so every new session receives MindSlice's instructions and `always_loaded` cards automatically. |
| **Cursor** | Merge `mcpServers.<server_name>` into `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project). | Add a short global Cursor Rule instructing the agent to call `<server_name>` `manifest()` on the first turn when standing preferences are not already in context. |
| **OpenAI Codex CLI** | Add `[mcp_servers.<server_name>]` (`command = "<mindslice_bin>"`, `args = ["-w", "<workspace>", "mcp"]`) in `~/.codex/config.toml`. | If MCP instructions are not auto-inlined by the active Codex version, add a 2-line reminder in `~/.codex/AGENTS.md` to call `manifest()` at session start and record durable learnings with `write()`. |
| **Strata (local models)** | For CLI apps via Strata, configure the app above and add `"--stage-writes"` for small local models. For Strata web chat, merge `mcp_servers.<server_name>` into both the active launch JSON (`~/.local/state/strata/launch/...`) and base model JSON (`~/.local/share/strata/install/...`), then restart Strata. | Strata 0.1.58 web chat does not forward `initialize.instructions`; if the web UI has a system prompt setting, paste `<mindslice_bin> -w <workspace> boot --mcp-instructions`, otherwise start new web chats by asking the model to call `<server_name>__manifest`. |
| **Other MCP apps** | Merge `{"mcpServers": {"<server_name>": {"command": "<mindslice_bin>", "args": ["-w", "<workspace>", "mcp"]}}}` into the app's MCP config. | If the app forwards MCP `initialize.instructions`, nothing else is needed. Otherwise wire `<mindslice_bin> -w <workspace> boot --mcp-instructions` into its startup hook / system prompt, or add a global rule to call `manifest()` first. |

### Antigravity `~/.gemini/config/hooks.json` template

Merge this top-level entry into `~/.gemini/config/hooks.json` (substituting `<server_name>`, `<mindslice_bin>` and `<workspace>`):

```json
{
  "<server_name>-boot": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 -c 'import json, subprocess; out = subprocess.run([\"<mindslice_bin>\", \"-w\", \"<workspace>\", \"boot\", \"--mcp-instructions\"], capture_output=True, text=True).stdout.strip(); print(json.dumps({\"injectSteps\": [{\"systemMessage\": {\"systemMessage\": out}}]} if out else {}))'"
      }
    ]
  }
}
```

### Optional: `--stage-writes` for smaller local models

When the user runs a small local model that follows tool instructions less reliably, append `"--stage-writes"` to the MCP `args` (`["-w", "<workspace>", "mcp", "--stage-writes"]`) so every runtime write lands in `staging/` for `mindslice diff --patch` / `mindslice apply`.

## Step 4 - Verify and hand off

1. Run `<mindslice_bin> -w <workspace> validate` and fix any validation errors.
2. Run `<mindslice_bin> -w <workspace> boot --mcp-instructions` to verify that standing cards (or the empty-workspace onboarding prompt) render cleanly.
3. Tell the user:
   - Where their memory workspace lives on disk (`<workspace>/overlay/` for agent notes, `<workspace>/mounts.toml` for mounted slices).
   - How to start a fresh session in their app (e.g. `/new` in `agy` or Claude Code) so the new MCP server and startup hook take effect — **no manual startup command needed**.
   - That future agent edits to `load = "always"` cards are staged for safety and approved with `mindslice -w <workspace> diff --patch` and `mindslice -w <workspace> apply`.
   - To disconnect or uninstall later, tell the agent to follow [`uninstall.md`](uninstall.md).
