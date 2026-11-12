# Connect your agent

[Home](../README.md) · [Install and seed memory](getting-started.md) · [Review and bake](workflow.md)

Initialize a workspace first. Use absolute executable and workspace paths in app configuration.
Verify session-start loading in a new conversation: the model should receive your standing notes
through MCP instructions, a startup hook running `mindslice boot`, or an initial `manifest` call.
After configuring the app, run `mindslice -w /path/to/workspace doctor` and complete the
[new-session verification](getting-started.md#verify-your-first-session). The local MCP probe
cannot establish that this particular app forwarded startup instructions to its model.

## Claude Code

Register the server:

```bash
claude mcp add --scope user mindslice -- mindslice -w ~/mindslice mcp
```

## Google Antigravity

For the `agy` CLI / IDE, add MindSlice to `~/.gemini/config/mcp_config.json` (use absolute
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
        "command": "python3 -c 'import json, subprocess; out = subprocess.run([\"/home/you/.local/bin/mindslice\", \"-w\", \"/home/you/mindslice\", \"boot\"], capture_output=True, text=True).stdout.strip(); print(json.dumps({\"injectSteps\": [{\"systemMessage\": {\"systemMessage\": out}}]} if out else {}))'"
      }
    ]
  }
}
```

## Other MCP apps

Add this to their MCP settings (with absolute paths):

```json
{"mcpServers": {"mindslice": {"command": "/home/you/.local/bin/mindslice", "args": ["-w", "/home/you/mindslice", "mcp"]}}}
```

If your app does not automatically inject MCP `initialize.instructions` into the model's context, wire
`mindslice -w /home/you/mindslice boot` into its startup hook / system prompt, or add a one-line
global rule instructing the agent to call MindSlice's `manifest` tool at session start.

Then just talk to your agent. Tell it "Remember that I use uv, not pip", and in a later conversation ask "How
do I install packages in my projects?"

## Local models through an agent app (Strata)

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

Every change the agent makes then waits for you in the [review workflow](workflow.md#review-changes).

**Chat in the app you connected.** `claude mcp add` connects MindSlice to Claude Code only. Strata's web
chat has its own MCP configuration (below), even when both apps use the same Qwen model.
`--stage-writes` controls review of memory writes; it does not connect other apps or control loading of
existing notes.

## Strata web chat

Strata supports this directly; see its [Tools from MCP servers guide](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md#tools-from-mcp-servers).
The steps below record the setup verified with Strata Terminal 0.1.58 and its Qwen web chat on Linux.
For newer releases, check the linked Strata guide for current configuration paths and startup behavior.

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
workspace path with the folder you initialized in the [setup guide](getting-started.md#create-or-import-your-memory). Use absolute paths in the JSON:

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
then use MindSlice's search, read and write tools, with writes staged for review in the [review workflow](workflow.md#review-changes).

**If the model says the tool is unavailable:** check **Monitor** first. Strata's `/mcp` endpoint also
reports the loaded servers and tool count; `{"servers": [], "tools": 0}` means the running server has no
MCP tools configured. Check the active model's configuration and restart Strata. If MindSlice is listed
but failed to start, check the server log and the command/workspace paths. If it is connected with four
tools, refresh the page, enable the MCP toggle and retry in a new chat.

If the tool works but your note is missing, run `mindslice -w /your/workspace boot` and check that the
same workspace path is configured above. The note must be a `.md` file in `overlay/` or a mounted slice.
