# Isolation and evolving memory

[Home](../README.md) · [Getting started](getting-started.md) · [Reference](reference.md)

MindSlice treats memory as independently reusable knowledge that changes over time.
Its engine defines where changes may land, how cards relate, and how a new version is
published. The agent decides what to remember and which facts extend or replace others.

## Isolation: reuse knowledge without sharing every change

A slice is a directory of Markdown cards, with its own mount alias. A workspace combines
selected slices with a writable `overlay/`. For example, two project workspaces can mount
the same `@handbook`; a local exception learned in one project's overlay leaves the shared
handbook and the other workspace unchanged.

- **Independent composition.** Mount and unmount slices separately. Qualified addresses
  such as `@handbook/deployment` identify the source even when another slice uses the same path.
- **Separate writes.** Engine writes target the workspace's overlay or staging area.
  They never modify mounted baselines in place.
- **Review before activation.** Staged proposals are excluded from live reads and searches
  until `apply`. Standing instructions are staged by default; `mcp --stage-writes` stages
  all agent writes. Ordinary writes can go straight to the overlay.

These boundaries govern MindSlice operations. They are not filesystem permissions or a
sandbox for an agent with shell access. All slices mounted in a workspace are available to
that workspace's queries; use separate workspaces when their active memory should differ.

## Evolution: represent what changed and preserve the baseline

Suppose a handbook says a session expires after 15 minutes. A project moves to 30 minutes.
The agent can write an overlay card with `supersedes = ["@handbook/auth/session"]`, plus a
reason explaining the migration. The handbook remains unchanged while retrieval can follow
the replacement. An `extends` relationship instead adds context to an existing card.

The engine resolves explicit relationships using the caller's trust policy, reports competing
replacements, and retains access to the baseline. It does not infer truth or automatically
recognize every stale fact: the agent or author must record the relationship correctly.

When the changes are ready to keep or share, `bake`:

1. Plans destinations for overlay cards, including existing slices and new ones.
2. Leaves staged proposals pending and lets the user defer unfinished overlay work.
3. Builds new slice directories and switches the workspace's mounts to those versions.
4. Returns the new physical paths, so external callers can record version pointers.

The old directories remain available to mount again. This restores a slice baseline;
it does not undo unrelated overlay changes. The engine records write reasons and lifecycle
events in the workspace's `.history/changes.jsonl`, separately from exported card content.
See [review and bake](workflow.md) for the complete workflow.

## How this fits hot/cold memory and LLM Wiki

These approaches address different concerns and can be combined. The comparison below
describes their organizing ideas, rather than claiming every implementation has the same features.

| Approach | Main concern | Relationship to MindSlice |
| --- | --- | --- |
| Hot/cold memory | Which information stays in context, and which is retrieved on demand? | MindSlice supplies standing cards at startup and retrieves other cards through search/read. Slice boundaries and versioning apply to both kinds. |
| LLM Wiki | How does an agent turn source material into maintained, linked knowledge? | An agent can build wiki-style knowledge into one or more slices, then use overlays and explicit relationships for subsequent changes. |
| MindSlice | Which knowledge is active, where may changes land, and how does it evolve into reusable versions? | Mounts, isolated writes, staging, lineage and baking are engine operations available through its interfaces. |

For a concrete example of context tiers, Letta documents in-context memory blocks, searchable
files and archival memory. This distinction concerns access to context.
See [Letta's context hierarchy](https://docs.letta.com/v1-sdk/memory/context-hierarchy).

Karpathy's LLM Wiki pattern already preserves raw sources and maintains an evolving Markdown
wiki with links, logging and checks for stale claims. MindSlice adds a particular storage and
versioning mechanism for independently mounted knowledge packages; it can support that authoring
workflow. See the [original LLM Wiki description](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

To distill one large document or multiple sources, use the optional
[MindSlice-forge](https://github.com/pancerZH/MindSlice-forge) tool through
[slice-builder](../skills/slice-builder/SKILL.md), or pass the
[conversion prompt](../skills/slice-builder/prompt-template.md) to Forge directly. Forge creates
a new workspace; connect it or mount its individual slices in an existing workspace. Choose slice
boundaries by independent use and evolution; source-file boundaries need not match slice boundaries.
Empty initialization, direct workspace connections and raw Markdown mounting remain engine operations.
