# Card format and retrieval vocabulary

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

1. **One focused sub-topic per card**: answer one independently useful question. Around 5-15
   statements is a guideline, not a quota; a short fact needs no padding. `validate()` warns past
   50 lines. Split by meaning while preserving prerequisites, exceptions and ordered procedures;
   use numbered steps, tables or code blocks when those represent the knowledge more faithfully.
2. **Summary paragraph** directly under the closing `+++`: 1-2 sentences, <= 240 chars.
   It is what `search()` shows, so make it a high-signal abstract, not a heading.
3. **Bullets are atomic, not stripped**: one fact/rule per `- ` line, self-contained, greppable,
   diffable. Keep the concrete values, names, dates, conditions and the source's own wording:
   search matches only words the card contains.
4. **Frontmatter is flat TOML**: only strings and lists of strings. `title` is weighted highest
   in search; `aliases` are synonyms (also usable as `[[alias]]` link targets, see below); `tags`
   are facets.
5. **Paths are addresses**: `architecture/async-patterns.md` is `architecture/async-patterns`.
   Use lowercase-kebab-case, group by topic folders, keep paths stable (links depend on them).
   **Name a card by the durable topic or slot it fills** (`team/lead`, `subscriptions/streaming`),
   never by the value it holds today (`team/lead-sarah-chen`, `subscriptions/xelvoria`). Ids and
   `[[links]]` outlive values: a link to a value-named card keeps stating the old value after it
   changes. When maintaining an existing overlay requires a separate replacement id, use a stable
   qualifier such as the change date (`team/lead-2026-11`), never the new value. Link to the slot
   (`[[team/lead]]`): `read()` follows `supersedes` from it to the current card.
6. **Links**: `[[path]]` or `[[path|label]]`. Without an `@alias/` prefix a link resolves *only
   inside the same slice* - never into other mounts. Use `[[@persona/tone]]` to reach across slices
   and declare that slice in `slice.toml` `dependencies`.
7. Never put secrets, tokens, machine-specific absolute paths or session noise in cards.
8. **`load = "always"`** (optional, after `title`) marks a card every session reads at start, with
   no query: an agent persona, the user's reply language, standing instructions. Use it sparingly
   (it costs context in every session) and keep such cards short. Everything else is the default,
   `load = "as-needed"`: found by search. Changes that touch an always-loaded card (editing,
   deleting, extending or superseding it, or marking a card always) are staged for the user's
   approval by default when made through `write`; the user approves with `mindslice apply`.
   Direct authoring of a new slice does not pass through that review buffer; do not infer standing
   instructions from source documents just because they contain imperative wording.

## Aliases: the words someone will search with

`search()` is lexical: a card is found only by words it contains (stemmed, case-folded; Chinese,
Japanese and other unspaced scripts match by character pairs). Someone who has never read the card
searches with *their* words, not yours. `aliases` are indexed just below the title, so they are the
place to put the other words for the same thing. Aim for 3-8 useful short aliases per card,
without padding when fewer suffice:

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

