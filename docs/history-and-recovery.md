# Understand and recover memory

[Home](../README.md) · [Review and bake](workflow.md) · [Reference](reference.md)

Use `history` to inspect recorded changes and `explain` to understand a current read.
Use `rollback` to switch one slice's baseline, or restore a full backup into a new workspace.
The examples assume `MINDSLICE_WORKSPACE` points to your workspace; `-w /path/to/workspace`
works with each workspace command.

## What changed, and why?

```bash
mindslice history                          # workspace events, newest first
mindslice history @project/api/auth        # one card's recorded lifecycle and reasons
mindslice history @overlay/removed-card    # still works after deletion or bake retirement
mindslice history @project/api/auth --limit 10 --offset 10 --json
```

The engine links proposals, accepted writes, discarded proposals and baked cards through their
change IDs. A baked card's history can therefore include the original overlay write and its reason.
Card history also includes recorded rollbacks of its mount. Use qualified addresses when the
card is gone or several historical mounts used the same path. History describes address usage
over time; reusing an address does not create a separate immutable card identity.

**The JSONL log stores metadata, not old card text.** It cannot reconstruct an overwritten
overlay card, and editor changes outside the engine do not automatically create reason records.
Use preserved slice directories or a workspace backup for content recovery. History remains local
to the workspace and is not included in exported slices.

## Why does a read return this version?

```bash
mindslice explain api/auth
mindslice explain @project/api/auth --follow curated --json
mindslice explain api/auth --follow none
```

The explanation uses the same selection and lineage rules as `read`, without incrementing read
telemetry. It shows the initial selection, final resolved address, replacement chain, shadows,
composed baselines/extensions, trust notices, physical source paths and matching write reasons.
Pending edits are identified separately and do not affect the resolved result.

Reasons are attached only when the current bytes match a recorded overlay revision or a card
in the currently mounted baked version or its recorded unchanged ancestry. An externally edited or imported card may have no
matching history; MindSlice reports that instead of assigning an old reason to new content.
Extensions are paginated with `--max-extensions` and `--extensions-offset`.

## Switch one slice to an earlier version

```bash
mindslice rollback @project --dry-run
mindslice rollback @project
```

The default target is the recorded predecessor of the currently mounted baked version. If there
is no recorded predecessor, or you want a particular directory, specify it:

```bash
mindslice rollback @project --to /path/to/project-v1.slice --dry-run
mindslice rollback @project --to /path/to/project-v1.slice --yes --json
```

An interactive call previews the target, retained overlay cards, pending proposals and validation
issues before asking for confirmation. Noninteractive execution requires `--yes`. The engine
rechecks the preview before switching and journals the mount-table update with a `rolled_back`
history event. The alias, precedence and role stay the same; neither slice directory is modified.
Use an explicit `--to` to switch forward again to a preserved newer directory.

**Rollback changes only the mounted baseline.** Overlay overrides and staged proposals stay in
place. An overlay card can still take precedence over the restored baseline; use `explain` to
inspect the effective result. New broken references, missing dependencies or invalid destination
cards block the switch. Fix the dependent cards or choose a compatible version, then preview again.
Existing unrelated validation warnings remain visible.

Old directories must still exist. The history log is not evidence that their original contents
remain unchanged; the preview checks the actual files currently at the target path.

## Back up a complete workspace

```bash
mindslice backup ~/memory-backups/work-2026-11-11
```

The output is a new directory containing `backup.json`, `workspace/`, and, when necessary,
`external/`. It includes:

- Workspace files, including overlay, staging, change history, local slice versions and extra files.
- Every current mount, including an overlay or slices outside the workspace.
- Available older external version directories referenced by bake/rollback events.
- A file inventory with SHA-256 checksums, byte counts and empty directories.

The disposable workspace `.cache/` is excluded. Engine operations are locked during capture;
the copy is verified and source inventories are rechecked before publication. If an editor changes
the files during capture, the backup fails and can be retried. No existing output is overwritten.

Choose an output outside all captured source directories. Symlinks, special files and paths that
cannot be represented by this portable format are rejected rather than silently omitted. A mount
containing the workspace itself must be narrowed before backup. If an already missing historical
version cannot be included, the receipt lists it under `unavailable_versions`; a missing current
mount blocks the backup. This is a directory snapshot, not a compressed archive or an encrypted backup.

## Restore without overwriting current work

```bash
mindslice restore ~/memory-backups/work-2026-11-11 --output ~/mindslice-recovered
mindslice -w ~/mindslice-recovered doctor
mindslice -w ~/mindslice-recovered status
```

Restore verifies the manifest and all file checksums before publishing a new workspace. The
destination must not exist. Invalid paths, symlinks, extra/missing files, checksum mismatches and
unfinished transaction journals are refused. Checksums detect changes; they do not authenticate
who created a backup.

External sources are copied inside the restored workspace under `.restored-mounts/` (or a fresh
numbered variant) and mount paths are rewritten. Recorded version paths are translated through
a restore event, so history-based rollback can use captured old versions on the new machine.
Original history records remain intact. Staged content, reasons and preconditions are preserved,
including any conflicts that existed at backup time. The index rebuilds on first use.

The old reviewed bake plan is invalidated because it belongs to another workspace location.
Review destinations again before baking. After checking the restored workspace, update your
client's MCP workspace path and repeat the [new-session check](getting-started.md#verify-your-first-session).
App configuration and chat transcripts stored outside the workspace are not part of this backup.
