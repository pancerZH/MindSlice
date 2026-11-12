# Review, bake and share memory

[Home](../README.md) · [Getting started](getting-started.md) · [Command reference](reference.md)

The examples use an existing workspace:

```bash
export MINDSLICE_WORKSPACE=~/mindslice
```

You can instead pass `-w /path/to/workspace` with each command.

## Review changes

Overlay cards are already saved on disk and available to retrieval. Staging holds proposed
changes that are not active yet; an existing card's applied version remains active meanwhile.
`bake` packages applied knowledge into reusable slice versions. It is not needed to save overlay
memory. Cards without a slice destination are valid saved memory, not an error.

Changes to always-on notes (and all writes when `--stage-writes` is enabled) wait in a review area until you decide:

```bash
mindslice status          # mounts, pending review, and slices with unbaked overlay changes
mindslice diff            # see the proposed changes as a patch
mindslice review          # accept, reject or leave each proposal pending; confirm the batch once
mindslice apply prefs/tone project/tooling    # accept only these pending cards
mindslice discard scratch/idea               # reject only this pending proposal
```

IDs are exact staging card paths, optionally `@overlay/path` or with a `.md` suffix.
`review ID...` limits the interactive review to those cards. Omitting IDs from `apply` or
`discard` retains the original behavior: accept or reject **all** pending changes.
Review requires a terminal; scripts can inspect `diff --json` and specify IDs explicitly.

Interactive review shows each patch, its reasons, references and affected live backlinks/extensions.
Enter leaves a proposal pending; cancelling or reaching EOF before final confirmation executes
none of the choices. A dependency check runs before confirmation. If card A needs a new staged
card B, accept both or leave A pending. A live version of B is sufficient even if B has another
pending edit. A selected deletion or alias change cannot break an existing live reference;
include its dependent edit or revise the reference. Pre-existing unresolved references do not
block independent approvals. Legacy `apply` without IDs continues to allow dangling references
as `write` does; use `validate` to inspect them.

The final confirmation rechecks the reviewed snapshot. If content, reasons, or relevant live
state changed, review again. Accepted and rejected choices share one recoverable transaction;
unselected cards retain their original content, preconditions and reasons through recovery.

`status --json` and `diff --json` provide structured output for scripts. `diff --scope overlay`
shows the applied overlay changes against mounted slices. In `status`, a dirty slice has related
overlay cards waiting to be baked; this does not track external edits to the slice's own files.

Agents supply a `reason` with `write` to explain each change; the CLI accepts `--reason "..."`.
`status` shows these reasons, and `diff` prints them on stderr alongside the patch on stdout
(`--json` includes structured `changes`). The engine keeps the record in `.history/changes.jsonl`,
including proposals, accepted writes, discarded proposals and baked versions. Pending cards stay
out of search and reads until applied, but their reasons survive discard and bake. The log is
workspace history, separate from card content and excluded from exported slices. Keep `.history/`
when backing up the workspace; unlike `.cache/`, it cannot be rebuilt from the cards.

To stop using a slice, run `mindslice unmount persona` (or `unmount @persona`). Its directory is
preserved. Mount aliases accept either form in `mount --alias`, `unmount`, `bake`, and `search --source`;
output consistently uses `@alias`.

CLI references also accept `read persona/tone` when it uniquely identifies `@persona/tone`. If a
relative card named `persona/tone` also exists in the workspace, use `read @persona/tone` for the mount
or `read ./persona/tone` for the relative path. The same shorthand works in `write --extends` and
`--supersedes`, where relative references are scoped to the overlay. Card aliases (`write --alias`)
and links inside card content keep their existing meaning.

Everything else the agent writes is saved directly as Markdown in `~/mindslice/overlay/`. You can open, edit or
delete any file there, and MindSlice picks up your changes automatically.

## Bake slice versions

Over time the agent's notes pile up in `~/mindslice/overlay/`. Every so often, move the good ones into slices.

**Review everything together:**

```bash
mindslice bake                         # choose destinations, inspect changes, then confirm once
mindslice bake --dry-run --json        # inspect the full plan without creating slices
```

Bake proposes existing slices where a card has one clear relationship. Unassigned or ambiguous
cards are grouped for review: choose an existing alias, name a new slice, split the group, or leave
it in overlay. A new card can join an existing slice. The final plan shows output paths, dependencies,
remaining overlay cards and excluded staging changes. Saved choices resume on the next `bake`;
`--fresh` starts a new review. Staged content is never approved automatically.

For scripts, assign destinations explicitly and use `--yes` after reviewing the plan:

```bash
mindslice bake --assign 'research/=@research' --defer 'scratch/' --dry-run --json > bake-plan.json
mindslice bake --plan bake-plan.json --yes --json
```

Every card needs a destination or an explicit deferral before execution. Input changes invalidate
a reviewed plan. The receipt lists every new version's alias, physical path and previous path.

**Target a single new slice** from the agent's notes on one topic:

```bash
mindslice bake @python-tips --prefix python/   # creates and mounts the slice, retiring the overlay copies
```

`--prefix` selects overlay card paths and is required when a named target alias is new.
Workspace review instead selects explicit cards for each destination, so it needs no `--prefix`. Use `--output` to choose
the output directory. An explicit `--prefix ''` selects all overlay cards.

**Add to a slice you already have.** Say you mounted a team handbook as `@handbook`, and the agent has since
corrected some of its notes and added to others. Bake those changes into a new version of the handbook:

```bash
mindslice bake @handbook --dry-run   # see which notes would move, and where the new version goes
mindslice bake @handbook             # build it, and mount it as @handbook in place of the old one
```

The new version is a copy of the handbook with the agent's notes added, in `~/mindslice/slices/` (or wherever
`--output` says). Your original folder is left exactly as it was, just no longer mounted: to go back, mount it
again. By default, bake takes the agent's notes that build on that slice; `--prefix python/` picks notes by
folder instead. For example, `mindslice bake @handbook --prefix python/ --output ./handbook-next.slice`
keeps the alias and mount settings while switching to the new directory.

A slice is just a folder of Markdown files, so you can also write one by hand and mount it, or let an agent with
the [slice-builder skill](../skills/slice-builder/SKILL.md) build one or more from source files or a long document.
For consolidating existing overlay knowledge before bake, use
[slice-maintainer](../skills/slice-maintainer/SKILL.md).

## Share a slice

Share a slice folder however you like (Git, a zip file). Whoever receives it runs
`mindslice mount python-tips.slice`. Baking also supports `--output python-tips.zip` or `.tar.gz`: it
writes the archive and mounts a directory under `~/mindslice/slices/`. The result reports both paths.
