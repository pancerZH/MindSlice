# Examples

`cards/` contains individual card templates you can read and customize before adding them to
your memory. These examples are not installed or mounted automatically.

## Proactive memory policy

- [English — proactive-memory-en.md](cards/proactive-memory-en.md)
- [简体中文 — proactive-memory-cn.md](cards/proactive-memory-cn.md)

These are two language versions of the same standing policy. **Choose one**; do not mount
the entire `examples/` or `examples/cards/` directory, which would load both policies.
两份模板表达相同的策略，请只选择一个语言版本，按需修改后再启用。

MindSlice's default startup instructions already ask agents to record useful, confirmed
knowledge proactively. This optional card makes your workspace's preferences explicit and
editable—for example, which topics to remember or which kinds of changes should be staged.

To install through your connected agent, ask it to read your chosen template, adapt it to your
preferences, and create a card such as `prefs/memory-policy` through `write` with the template's
title, summary, body, aliases, tags, `load="always"` and a reason. If that card already exists,
review and update it rather than creating a duplicate. Standing-card changes wait for approval:

```bash
mindslice -w ~/mindslice review prefs/memory-policy
mindslice -w ~/mindslice boot --cards-only
```

If you prefer a read-only policy slice, copy **only the chosen card** into a new slice directory,
review its contents, and mount that directory. Explicitly mounting an authored slice activates
its standing cards immediately; it does not create a staging proposal.

Reconnect the MCP server after upgrading MindSlice, and verify that the client actually loads
startup instructions in a fresh conversation. See the
[first-session checklist](../docs/getting-started.md#verify-your-first-session).
`load="always"` cannot make a client inject context it does not forward. To enforce review for
every agent write, use `mcp --stage-writes`; a policy card alone is a model instruction.

To try the policy, state a confirmed preference or project decision without saying “remember
this”, inspect the resulting card or pending proposal, then ask about it in a new conversation.
Also try an unaccepted suggestion and a temporary task update: those should not produce durable
memories. These are behavioral checks, not a guarantee that every model will follow the policy.
