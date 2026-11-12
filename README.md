# MindSlice

**Portable memory for AI agents, with isolation and evolution built in.**

Keep project knowledge, personal preferences and shared handbooks in plain Markdown.
Mount what an agent needs, let it learn in its own workspace, and bake those learnings
into reusable versions. Connect through MCP, the CLI or Python.

## Why MindSlice?

**Isolation.** A *slice* is a folder of Markdown cards you can mount, unmount and share
independently. Mounted slices stay read-only through the engine; new learning goes into
a separate overlay. Multiple workspaces can reuse the same baseline while keeping their
own changes. Pending edits stay outside live memory until approved.

**Evolving memory.** Cards can explicitly extend or supersede earlier knowledge, so
retrieval follows recorded relationships under your trust rules. `bake` turns selected
changes into new slice versions, preserving the original folders and returning the new paths.

[Hot/cold memory](https://docs.letta.com/v1-sdk/memory/context-hierarchy) focuses on what stays
in context and what is retrieved later. [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
focuses on compiling sources into a maintained knowledge base. MindSlice makes **memory
boundaries and controlled evolution** first-class engine operations.
[How these approaches fit together →](docs/concepts.md)

Python 3.12+. No runtime dependencies, database server or LLM API calls inside the engine.

## Get started

Paste this into your coding agent:

```text
Clone https://github.com/pancerZH/MindSlice.git (or use the existing checkout).
Read skills/mindslice-setup/SKILL.md, install MindSlice, connect it to this agent
with session-start memory loading, and help me seed my initial memory.
```

The agent helps you choose a workspace, connect your app, and start from existing notes,
shared slices or a short conversation.

Prefer manual setup? With Python 3.12+ and pipx installed:

```bash
git clone https://github.com/pancerZH/MindSlice.git
cd MindSlice
pipx install -e .
mindslice init ~/mindslice
```

Then [connect your agent](docs/integrations.md) and tell it what to remember.
[Full setup guide](docs/getting-started.md) · [Review changes and bake slices](docs/workflow.md)

## Documentation

- [Concepts](docs/concepts.md) — isolation, evolution, and how MindSlice fits other memory architectures.
- [Reference](docs/reference.md) — commands, Python API, MCP tools and card formats.
- [Build slices](skills/slice-builder/SKILL.md) — turn one document or many into one or more slices.
- [Maintain memory](skills/slice-maintainer/SKILL.md) — consolidate knowledge and repair relationships.
- [Evaluations](docs/evaluations.md) · [Design](docs/design.md) · [Uninstall](skills/mindslice-setup/uninstall.md)
