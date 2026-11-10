# Prompt template: build a MindSlice slice

Use this with any agent that has file read/write access (no skill support required).
Replace the `{{placeholders}}`.

---

You are building a **MindSlice memory slice**: a directory of small Markdown "cards" that give
future AI agents durable knowledge about {{domain}}.

**Sources to read:** {{sources, e.g. README.md, CLAUDE.md, docs/adr/, src/core/}}
**Output directory:** `{{name}}.slice/`
**Slice alias:** `@{{alias}}`

## Output format

Each card is `{{name}}.slice/<topic>/<card-name>.md` (lowercase-kebab-case paths) with this exact shape:

```markdown
+++
title = "<Specific, descriptive title>"
aliases = ["<synonym>", "<shorthand>"]
tags = ["<facet>", "<facet>"]
extends = []
supersedes = []
+++

<1-2 sentence summary, at most 240 characters, stating the single most important thing.>

- <Atomic statement: one rule, fact, decision (with why) or gotcha per bullet.>
- <Link related cards as [[topic/card-name]].>
```

Constraints:

- One focused sub-topic per card; 5-15 bullets; at most ~50 lines. Split larger topics.
- Name each card by the durable topic or slot it covers (`team/lead.md`, `subscriptions/streaming.md`), never
  by a value that can change (`team/lead-sarah-chen.md`): paths are link targets and outlive the values.
- Bullets keep the concrete values, names, dates, conditions and the sources' own wording: search is
  lexical and matches only words the card contains.
- `aliases`: 3-8 search synonyms of 1-4 words each (other phrasings, the words someone would ask with,
  abbreviations both ways, former names), none already in the title or summary.
- `extends`: cards this one refines, adds exceptions or if-then rules to, or depends on as a premise.
  `supersedes`: cards this one replaces (usually empty in a new slice).
- Frontmatter is TOML: only strings and lists of strings.
- `[[links]]` without an `@alias/` prefix refer to cards in this same slice; every link must resolve.
- Capture what is durable and non-obvious (conventions, decisions and their rationale, invariants,
  procedures, pitfalls). Skip what the code makes self-evident.
- No secrets, credentials, personal data, machine-specific absolute paths, or transient status.

Also write:

1. `{{name}}.slice/overview.md` - a short map: what the slice covers, its folders, and the 3-5 cards
   to read first (as `[[links]]`).
2. `{{name}}.slice/slice.toml`:
   ```toml
   name = "{{name}}"
   version = "0.1.0"
   description = "<at most 160 characters>"
   alias = "@{{alias}}"
   dependencies = []
   ```

## Procedure

1. Read the sources and list 4-10 topics (top-level folders).
2. Plan every card as `topic/card-name - purpose` before writing any file.
3. Write the cards, `overview.md` and `slice.toml`.
4. Run `mindslice validate {{name}}.slice` (if available) and fix all errors.
5. Report the card list and any knowledge you were unsure about.
