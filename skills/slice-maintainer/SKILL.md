---
name: slice-maintainer
description: Maintain existing MindSlice memory, resolve overlay lineage and duplicate knowledge, and consolidate or bake new slice versions. Use for reviewing accumulated changes, updating dependent cards, and preparing slices for sharing; raw-document initialization belongs to slice-builder.
---

# slice-maintainer

Use this skill for deliberate maintenance and consolidation in an existing workspace. Routine
agent writes already receive guidance from the MCP server. For building one or more new slices from source
files or a long document, use [slice-builder](../slice-builder/SKILL.md).

Commands use the `mindslice` CLI (`python -m mindslice` also works); add `-w <workspace>` unless
inside the workspace. All operations have Python `Workspace` methods; MCP exposes only
`manifest`, `search`, `read` and `write`, so management operations need CLI or Python access.

When authoring or rewriting cards, read the shared
[card format and retrieval vocabulary](../slice-builder/references/card-format.md).
Preserve source qualifications and unresolved disagreements when merging existing cards; a newer
write alone does not prove that an older fact is false. Base slices stay read-only to runtime writes.

## Maintain existing memory

Navigate progressively: `manifest` (what exists) -> `search "<terms>"` (previews) -> `read <address>`
(full card, composed with extensions and replacements). Base slices are read-only; every runtime
write lands in `@overlay` (or `staging/` with `--stage` for human review).

Supply `reason` with each `write` (CLI `--reason`): briefly state the evidence, correction or
decision that motivates the change. The engine records it in `.history/changes.jsonl` and links
it through review and bake. Never write or edit `.history/` yourself, and do not put this change
metadata into card frontmatter. Review reasons with `status` or `diff --json`; text `diff` sends
them to stderr beside the patch on stdout.

Pick the right operation:

| Situation | Operation |
| :-- | :-- |
| New durable fact on an existing overlay card | `write <id> --op append --content "- fact"` (dedupes retries) |
| New topic | `write <id> --summary ... --content ...` (`create`) |
| Refines, adds an exception or if-then rule to, or depends on a card that stays valid | `create` with `--extends @project/api/auth-flow` |
| An overlay card turns out to depend on another | `--op append --extends <baseline>` (adds the edge, text unchanged) |
| A card is now wrong or outdated (changed value, correction) | `create` with `--supersedes @project/api/auth-flow` |
| Rewrite an overlay card you just read | `--op replace --if-match <sha256 from read>` |
| A request to forget, or a card that should never have been written | `--op delete` |
| The response lists `affected_backlinks` / `affected_extensions` | Update or rebase each one now (below) |
| A lasting preference about how the agent behaves (language, tone, persona) | `create` with `--load always` (staged for approval) |

Prefer `append` over creating near-duplicates; `search` first to find the right card. Give new
cards aliases too (`--alias`, repeatable), using the shared card-format reference.

Lineage is what keeps stale facts behind current ones, and only the writer can declare it:

- **`extends` is also a dependency.** A card extends its baseline when it refines it, adds an
  exception or an if-then rule, or holds only because the baseline does (a choice made because of
  a preference, a plan built on a constraint). If the baseline is later superseded or deleted,
  `read()` and `search()` flag the card (`baseline_superseded_by`, `missing_baselines`) along the
  whole `extends` chain. Declare it when you write the card.
- **When something changes, supersede it; don't delete it.** The old card stays searchable and
  forwards its hits to the replacement (`matched_via_superseded`), so its wording still finds the
  current fact. The replacement takes over every hit on the old card, so restate whatever in it is
  still true.
- **When unsure, extend.** A wrong `supersedes` hides a card that is still true; a wrong `extends`
  hides nothing. A sub-case, a refinement or a conditional rule replaces nothing.
- **Keep facts that change independently on separate cards**, since `supersedes` and `delete` act
  on whole cards, but keep each card concrete and preserve its conditions.
- **Finish what a supersede or delete starts.** Every `write` that supersedes or deletes a card
  returns the cards that still point at it: `affected_backlinks` (they `[[link]]` to it) and
  `affected_extensions` (they `extends` it), with `total_affected_*` counts. In the same session,
  for each one you can edit: rewrite a card that still states the old value as current, or that
  links to a card named after the old value; rebase an extension that still holds
  (`--op replace --extends <replacement>`), and supersede or delete one whose premise is gone. A
  link to a slot (`[[team/lead]]`) can stay. Items marked `read_only` live in base slices:
  supersede one from `@overlay` only if it states the old value as current (`read()` already flags
  extensions with `baseline_superseded_by`). The engine lists; it never edits them for you.

When a search comes back empty or weak, look at `unmatched_terms`: the query words no card contains.
Rephrase those (fix a typo, try a synonym or the team's other language), or reuse the vocabulary of
the cards you did find, before concluding the memory has nothing.

## Consolidate and bake

1. Review what accumulated: `mindslice status` summarizes mounts, pending review and unbaked changes.
   `mindslice diff --scope overlay --json` classifies every overlay card as
   `new`, `shadow` (same path as a base card, no lineage), `extends`, or `supersedes`, and lists
   **unrebased** extensions (an extension whose baseline was later superseded).
2. **Semantic consolidation** (your job, not the engine's): for each extends/supersedes cluster,
   read the cards and rewrite them into clean, self-contained cards - merge an extension into its
   baseline's replacement, drop statements a replacement made obsolete, resolve shadows. Rebase or
   delete unrebased extensions (`write E --op replace --extends <replacement>`). Use
   `--stage` + `mindslice diff` + `mindslice apply` when a human should review.
3. **Scrub**: remove secrets, personal data, absolute paths, ephemeral session details.
4. **Bake and mount**: `mindslice bake @team --prefix team/ --output team.slice` creates a new
   slice and mounts it as `@team`. A new alias requires `--prefix`, which selects overlay card paths;
   use `--prefix ''` to select all paths. `--tag ...` adds a tag filter. References to excluded overlay
   cards abort the bake; add `--include-deps` to pull them in. Cross-slice references become dependencies.
5. **Verify and share**: check the result's `validation`, or run `mindslice validate team.slice`, then
   report the artifact for sharing. Publish only when the user requested publication.
   `--output team.zip` / `team.tar.gz` produces a deterministic archive and a mounted directory under the workspace's `slices/`; the result reports
   the archive as `output` and the absolute mounted directory as `path`. Return these and
   `previous_path` to the caller so it can retain a version pointer.
6. **Review retirement**: bake removes the overlay copies and rewrites references from cards that stay
   (`[[team/lead]]` -> `[[@team/team/lead]]`). Check `retired_overlay_cards`, `rebased_references`,
   `shadowing_overlay_cards` (copies needed by staged cards) and `broken_references` (read-only slices).

**For an existing mount**, `mindslice bake @team --dry-run` shows which overlay cards would move (by
default the ones that extend or supersede a card of `@team`, or share a path with one) and where the
new version goes. `mindslice bake @team` builds that version, switches the mount while preserving its
alias, precedence and role, and retires the overlay copies. `--prefix` / `--tag` select other cards;
`--output` chooses another destination. The old folder stays unchanged and is no longer mounted.
Bake refuses an overlay card that extends the slice card at its own path (merge the two into one card
first, consolidation step 2) and a selected card with a staged change. Check `validation` before publishing.
