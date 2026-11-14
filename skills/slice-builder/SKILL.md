---
name: slice-builder
description: Build initial MindSlice slices from source documents using MindSlice-forge, then connect the generated workspace or mount its slices in an existing workspace. Use for distilling handbooks, project docs or lore; direct Markdown mounting and existing-memory maintenance use MindSlice itself.
---

# slice-builder

Use [MindSlice-forge](https://github.com/pancerZH/MindSlice-forge) to turn source documents into
a new MindSlice workspace containing one or more slices. Forge owns planning, chunking, agent
sessions, recorded lookups, validation, repairs and checkpoints. This skill handles the user's
scope, the conversion instructions, checking the result and connecting it to MindSlice.

## Choose the entry point

- **Search existing Markdown unchanged:** use `mindslice -w <workspace> mount <notes-directory>`.
  Plain Markdown and YAML-frontmatter notes need no conversion or Forge installation.
- **Use an existing workspace:** open it with `-w <workspace>` and connect its MCP server;
  do not mount the entire workspace root as a slice.
- **Start empty or from a short conversation:** follow
  [mindslice-setup](../mindslice-setup/SKILL.md); `mindslice init` and overlay writes suffice.
- **Distill source documents into cards:** follow the Forge workflow below.
- **Update existing memory, repair lineage or bake:** use
  [slice-maintainer](../slice-maintainer/SKILL.md).

## Prepare the build

Use the user's sources, intended questions, language, exclusions and destination. Ask only for
missing choices that materially affect the build. Reuse a specified harness, model and sampling
limit. Reading chunks are not slice boundaries: choose slices by independent use and evolution.

Forge needs Python 3.12+, `mindslice`, `git`, and an authenticated agent harness that can run a
session unattended from the command line. Reuse installed tools and local checkouts; otherwise
install Forge following its
[installation instructions](https://github.com/pancerZH/MindSlice-forge#install).
If a prerequisite cannot be made available, report the blocker; do not silently replace the
Forge build with a second manual extraction workflow.

Forge knows no particular harness. You give it, as `--harness-cmd`, the command line that runs
one agent session, and it runs that command once per step. Use the harness and model the user
names; otherwise the harness you are running in. `mindslice-forge --help` states what the command
must do, and `--dry-run` lists the directories a session must reach. Take the options for a
non-interactive session, for approving tool use without prompts, for the model and for directory
access from that harness's own help, not from memory, and write paths as absolute paths. Build
sessions act without anyone approving their tool calls: unless the user gave the command
themselves, tell them so and get their agreement before the first run. Forge checks a new command
with one short session before the build; when that check fails, correct the command from its
message and the session log it names, and run again.

Select the input boundary **before** running even `--dry-run`: Forge recursively reads non-hidden
files and detects text encodings; it does not implement project-specific ignore rules or forbidden
directory markers. Pass selected allowed files or prepare a separate snapshot preserving relative
paths when exclusions matter. Prune forbidden directories before traversal, keep a source mapping,
and leave originals unchanged. Convert PDF/Word to text separately if needed.

Choose the destination by the user's goal:

- **New workspace:** give Forge the intended workspace path as `-o`; do not run `mindslice init`
  there first. Forge initializes and mounts its own output.
- **Add knowledge to an existing workspace:** build in a separate, new directory outside that
  workspace and its mounted sources. Forge cannot take over a nonempty workspace it did not create.
- **Deliver slices only:** still build in a new workspace, then deliver the individual
  `slices/*.slice` directories and the report. Connecting a live workspace is a separate scope.

Keep output and build instructions outside the source directories so they cannot be ingested on
resume. Write a task-specific conversion prompt; [prompt-template.md](prompt-template.md) is a
starting point for `--prompt`, not a replacement build procedure. Include audience, scope, source
authority, useful slice boundaries and how to preserve conditions, contradictions and changes
over time. Use `--dict` for optional navigation or terminology, not as a substitute fact source.

## Run Forge

For example, after selecting the actual paths and composing the harness command:

```bash
mindslice-forge ./selected-sources --prompt ./conversion-prompt.md \
  -o ./knowledge.workspace --dry-run
mindslice-forge ./selected-sources --prompt ./conversion-prompt.md \
  -o ./knowledge.workspace --harness-cmd '<command for one unattended agent session> {message}'
```

Use `--sample N` when the user requests a trial or a processing limit. Report partial coverage;
do not silently raise the limit. The same command resumes completed steps. To finish an agreed
trial, remove the sample limit when authorized. If sources, prompt, dict or chunk size change,
choose an explicit `--from plan|split|extract|finalize` appropriate to the change, or a new output.
Retain `<output>.forge/` while the build may resume: it contains state, chunks, lookups, prompts,
logs, ledgers, handoffs and the report. Failed checks and repairs are handled by Forge; do not
delete state or bypass the recorded-lookup check to make a failed run appear successful.

## Check and connect the result

Read `<output>.forge/report.md`, the chunk manifest and relevant ledger entries. Confirm processed
versus total chunks, skipped material and remaining issues. Run `mindslice -w <output> validate`
and `status`. Check a few source-backed questions with `search` and `read`, including a condition,
exception or change over time. Record expected facts, source locators, retrieved addresses and
observed gaps in a sibling acceptance note. Format and lookup checks do not prove factual
completeness; the model's own report is not independent verification.

For a **new workspace**, pass the generated workspace path to
[mindslice-setup](../mindslice-setup/SKILL.md) for MCP and standing-memory setup when requested.
For an **existing workspace**, inspect its mounts and the generated slices' aliases and dependencies
first. Mount the selected individual `.slice` directories with `--precedence 50 --role curated`,
then validate and try retrieval in that destination. Do not mount the build workspace, its `slices/`
parent or its `.forge/` directory. Keep aliases used by cross-slice links; if they collide with
existing mounts, resolve the integration explicitly rather than silently replacing a mount or
renaming only one side of a reference.

Mounted directories must remain at stable paths. Before further Forge rebuilds, copy the selected
slices to a durable library or the destination's `slices/` directory and mount those copies; check
dependencies and retrieval there. Leave existing directories intact. This keeps a later build
rollback from changing a live mounted baseline.

Deliver the workspace/slice paths, observed counts, coverage, validation and retrieval results,
material gaps and links to the Forge report, ledgers and acceptance note. Include a few checked
questions with brief expected facts and source links. Distinguish generated artifacts, successful
mounts and actual client-session verification. Keep source evidence and build state outside slices.
The [card-format reference](references/card-format.md) remains available for manual authoring and
maintenance; Forge supplies its own card instructions during builds.
