---
name: slice-builder
description: Build, refine and consolidate MindSlice memory slices. Use when bootstrapping a .slice from project docs (README, CLAUDE.md, ADRs, runbooks, source), when recording durable learnings into @overlay, or when distilling overlay/ into a clean, shareable slice with pack().
---

# slice-builder

MindSlice stores long-term memory as plain Markdown **cards** inside **slices** (directories).
The engine only stores, indexes and resolves; *you* supply the judgment: what is worth
remembering, how to split it, and how to consolidate it. This skill covers the three
lifecycle stages from the design doc (section 7).

All commands below use the `mindslice` CLI (`python -m mindslice` works too); add
`-w <workspace>` unless you are inside the workspace. Everything is also available as
Python methods on `mindslice.Workspace` and (manifest/search/read/write) as MCP tools.

## Card format (the only thing you must get right)

```markdown
+++
title = "Python Backend Error Handling Conventions"
aliases = ["error-handling", "exception-policy"]
tags = ["python", "backend", "reliability"]
extends = []                    # @alias/path or slice-relative path
supersedes = []                 # @alias/path or slice-relative path
+++

All backend services raise typed AppError subclasses and translate them to RFC 7807 only at the HTTP boundary.

- Define domain exceptions in `core/errors.py` inheriting from `AppError`.
- Map `AppError` subclasses to status codes only in the exception middleware (see [[architecture/http-middleware]]).
```

Rules:

1. **One focused sub-topic per card**: 5-15 atomic bullet statements, roughly 10-50 lines.
   Split anything longer (`validate()` warns past 50 lines).
2. **Summary paragraph** directly under the closing `+++`: 1-2 sentences, <= 240 chars.
   It is what `search()` shows, so make it a high-signal abstract, not a heading.
3. **Bullets are atomic**: one fact/rule per `- ` line, self-contained, greppable, diffable.
4. **Frontmatter is flat TOML**: only strings and lists of strings. `title` is weighted highest
   in search; `aliases` are synonyms (also usable as `[[alias]]` link targets, see below); `tags`
   are facets.
5. **Paths are addresses**: `architecture/async-patterns.md` is `architecture/async-patterns`.
   Use lowercase-kebab-case, group by topic folders, keep paths stable (links depend on them).
6. **Links**: `[[path]]` or `[[path|label]]`. Without an `@alias/` prefix a link resolves *only
   inside the same slice* - never into other mounts. Use `[[@persona/tone]]` to reach across slices
   and declare that slice in `slice.toml` `dependencies`.
7. Never put secrets, tokens, machine-specific absolute paths or session noise in cards.

## Aliases: the words someone will search with

`search()` is lexical: a card is found only by words it contains (stemmed, case-folded; Chinese,
Japanese and other unspaced scripts match by character pairs). Someone who has never read the card
searches with *their* words, not yours. `aliases` are indexed just below the title, so they are the
place to put the other words for the same thing. Write 3-8 per card, each 1-4 words:

- **Synonyms and near-synonyms** of the title's key terms (`exception policy` for error handling).
- **The asker's phrasing**: the symptom, task or goal that sends someone to this card, as they
  would say it (`500 errors`, `what to return when a request fails`), including colloquial wording.
- **Abbreviations and expansions** both ways, and spelling variants (`RFC 7807`, `problem details`).
- **Former names** of renamed things, and names from tools people know (`error middleware`).
- **The team's other working language**, if it has one: the terms a colleague would use for this
  topic in that language (`错误处理` on an English card, `error handling` on a Chinese one).

Avoid:

- Words already in the title or summary: they are indexed already.
- Generic words that fit most cards (`process`, `policy`, `guide`, `team`, `规范`, `流程`): they make
  unrelated cards match.
- An alias another card in the same slice already uses (`validate()` warns), or one that equals
  another card's path: aliases are also link and `read()` targets.

## Stage 1 - Cold start: bootstrap a slice from raw sources

1. **Inventory** the sources (README, CLAUDE.md, ADRs, runbooks, `docs/`, key source modules).
   Note the 4-10 natural topics; these become top-level folders.
2. **Plan the card list** before writing: `folder/card-name` + one-line purpose each. Prefer
   many small cards over a few large ones. Each card should answer one question an agent would ask.
3. **Write cards** into `<name>.slice/` following the format above. Extract durable rules,
   conventions, decisions (with rationale), gotchas and procedures; skip things the code makes
   obvious. Link related cards with `[[...]]`.
4. **Write `overview.md`**: a short map of the slice - what it covers, the folders, and the 3-5
   cards to read first (as `[[links]]`).
5. **Write `slice.toml`**:
   ```toml
   name = "python-backend"
   version = "0.1.0"
   description = "Conventions and architecture of the Python backend (<= 160 chars)."
   alias = "@backend"
   dependencies = []
   ```
6. **Validate** and fix every error (warnings are judgment calls):
   `mindslice validate path/to/python-backend.slice`
7. **Mount** it read-only: `mindslice mount path/to/python-backend.slice --precedence 50 --role curated`

## Stage 2 - Daily refining: record learnings in @overlay

Navigate progressively: `manifest` (what exists) -> `search "<terms>"` (previews) -> `read <address>`
(full card, composed with extensions and replacements). Base slices are read-only; every runtime
write lands in `@overlay` (or `staging/` with `--stage` for human review).

Pick the right operation:

| Situation | Operation |
| :-- | :-- |
| New durable fact on an existing overlay card | `write <id> --op append --content "- fact"` (dedupes retries) |
| New topic | `write <id> --summary ... --content ...` (`create`) |
| Exception/detail to a base card (base stays valid) | `create` with `--extends @project/api/auth-flow` |
| Base card is now wrong/outdated | `create` with `--supersedes @project/api/auth-flow` |
| Rewrite an overlay card you just read | `--op replace --if-match <sha256 from read>` |
| Wrong memory | `--op delete` |

Prefer `append` over creating near-duplicates; `search` first to find the right card. Give new
cards aliases too (`--alias`, repeatable), following the rules above.

When a search comes back empty or weak, look at `unmatched_terms`: the query words no card contains.
Rephrase those (fix a typo, try a synonym or the team's other language), or reuse the vocabulary of
the cards you did find, before concluding the memory has nothing.

## Stage 3 - Consolidate, scrub & share

1. Review what accumulated: `mindslice diff --scope overlay` classifies every overlay card as
   `new`, `shadow` (same path as a base card, no lineage), `extends`, or `supersedes`, and lists
   **unrebased** extensions (an extension whose baseline was later superseded).
2. **Semantic consolidation** (your job, not the engine's): for each extends/supersedes cluster,
   read the cards and rewrite them into clean, self-contained cards - merge an extension into its
   baseline's replacement, drop statements a replacement made obsolete, resolve shadows. Rebase or
   delete unrebased extensions (`write E --op replace --extends <replacement>`). Use
   `--stage` + `mindslice diff` + `mindslice apply` when a human should review.
3. **Scrub**: remove secrets, personal data, absolute paths, ephemeral session details.
4. **Package**: `mindslice pack team.slice --prefix team/` (or `--tag ...`). References to
   excluded overlay cards abort the export; add `--include-deps` to pull them in. Cross-slice
   references become `dependencies`. Archives: `team.slice.tar.gz` / `team.zip` (deterministic).
5. **Verify**: `mindslice validate team.slice`, then publish the directory as a Git repo or archive.
