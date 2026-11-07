# MindSlice: Layered Pluggable LLM Memory Engine

## 1. Positioning & Core Principles
A **lightweight, zero-dependency, 100% human-readable** module for modeling and organizing long-term LLM memory. Rather than competing with monolithic agent runtimes or full-stack memory platforms, MindSlice acts as the filesystem layer for agent memory—exposing clean state primitives that any agent or upper-layer memory framework can embed.

#### Four Guiding Principles
1. **Mechanism Separated from Policy**: MindSlice contains no internal LLM API calls, no external database daemons, and no hardcoded "truth authority" heuristics. It handles layered storage, namespaced addressing, lineage resolution, lexical indexing, and transactional staging. High-level memory policies plug in cleanly through plain files, skills, and caller-supplied trust rules.
2. **Plain Markdown & TOML as the Single Source of Truth**: All memories and configurations live in human-readable `.md` and `.toml` files on disk. The local SQLite database (`.cache/index.sqlite`) is a disposable acceleration cache: its search index and link graphs are 100% reconstructible from disk at any time (whereas access telemetry such as `read_count` is intentionally best-effort ephemeral state).
3. **Immutable Baseline & Dynamic Growth**: Mounted base slices (`.slice/`) are strictly read-only. All runtime learnings, local exceptions, and overrides are written exclusively to a writable `overlay/` directory (or isolated in `staging/` prior to commit).
4. **Zero-Dependency Python 3.12+ Standard Library Only (POSIX v1)**: Built exclusively with the Python 3.12+ standard library (`sqlite3`, `tomllib`, `pathlib`, `hashlib`, `fcntl`, `unicodedata`). v1 targets POSIX systems (Linux/macOS) via `fcntl.flock` (with `msvcrt` lockfile byte-range locking as an optional Windows adapter). Using TOML (`+++`) for card frontmatter alongside `.toml` manifests eliminates third-party parser dependencies and allows direct use via `import`, CLI, or a thin 4-tool MCP server.

---

## 2. Directory Model & Filesystem Layout
**A Directory is a Slice**. There is no proprietary binary container format—a slice is simply a standard directory that can be versioned and shared directly as a Git repository or packaged as a `.zip`/`.tar.gz` archive. Furthermore, `overlay/` and `staging/` share the exact same internal layout as a `.slice/` directory.

### 2.1 Inside a Single Slice
A slice is a self-contained directory holding Markdown memory cards, organized flatly or grouped into topic subdirectories, alongside optional metadata and entry-point files:

```text
python-backend.slice/
├── slice.toml                  # (Optional) Slice manifest & dependency metadata
├── overview.md                 # (Optional) High-level domain map & entry point
├── coding-conventions.md       # Root-level memory card
├── architecture/               # Topic subdirectory
│   ├── async-patterns.md
│   └── http-middleware.md
└── observability/
    └── structured-logging.md
```

* **`slice.toml` *(Optional)***: Package manifest defining `name`, `version`, `description` (≤160 chars), recommended `alias`, and external slice `dependencies` (e.g., `["@persona"]`).
* **`overview.md` *(Optional)***: Human- and LLM-readable executive summary of the slice, inspectable on demand via `read("@alias/overview")` or `manifest(include_overview=True)`.
* **Memory Cards (`*.md`)**: Plain Markdown files with TOML frontmatter storing discrete units of long-term knowledge (addressed by relative path without `.md`, e.g., `architecture/async-patterns`).
* **Topic Subdirectories**: Nested folders used to categorize and scope memory cards by domain, module, or topic.

### 2.2 Full Workspace Layout
A complete MindSlice workspace coordinates multiple read-only base slices, a writable `overlay/`, an isolated `staging/` buffer, and a disposable SQLite index:

```text
workspace/
├── mounts.toml                 # Mount table: slice paths, @aliases, precedence, and role tags
├── slices/                     # Local directory of mounted read-only base slices
│   ├── core-persona.slice/     # Precedence: 10  | Alias: @persona | Role: baseline
│   │   ├── slice.toml
│   │   ├── overview.md
│   │   └── tone-and-style.md
│   └── project-kb.slice/       # Precedence: 50  | Alias: @project | Role: curated
│       ├── slice.toml
│       ├── overview.md
│       └── api/
│           └── auth-flow.md
├── overlay/                    # Writable layer (Precedence: 100 | Alias: @overlay | Role: runtime)
│   ├── overview.md
│   ├── user-preferences/
│   │   └── tooling.md
│   └── api/                    # Extends or supersedes cards in @project/api/
│       └── auth-edge-cases.md
├── staging/                    # Prospective final-state buffer (excluded from live index)
│   ├── .manifest.json          # Original base_sha256 preconditions & delete tombstones
│   ├── .apply_journal.json     # Present only during an in-flight apply() batch
│   └── api/
│       └── rate-limit-draft.md
└── .cache/                     # Disposable local state
    ├── index.sqlite            # Stdlib sqlite3 index, graph & best-effort telemetry
    └── workspace.lock          # Reader/writer lockfile (fcntl.flock LOCK_SH / LOCK_EX)
```

#### Workspace Components, Locking & Freshness Model
1. **`mounts.toml` (Mount Table & Separation of Concerns)**:
   Binds each slice's filesystem path to a namespace alias (`@alias`), a path-resolution `precedence` integer, and an opaque caller-defined `role` string.
   * **Decoupling Precedence from Authority**: `precedence` controls **only** which slice wins when a caller passes an *unqualified* relative path to the API (e.g., `read("api/auth-flow")`) and breaks exact BM25 score ties. It does **not** boost search relevance or dictate which conflicting statement the agent must believe. Instead, `role` (e.g., `"curated"`, `"runtime"`, `"baseline"`) is returned as provenance metadata—and can be passed to `follow_supersedes`—so the caller's policy decides whether runtime inferences may override curated knowledge.
   ```toml
   [overlay]
   path = "./overlay"
   alias = "@overlay"
   precedence = 100
   role = "runtime"

   [[mounts]]
   path = "./slices/project-kb.slice"
   alias = "@project"
   precedence = 50
   role = "curated"

   [[mounts]]
   path = "./slices/core-persona.slice"
   alias = "@persona"
   precedence = 10
   role = "baseline"
   ```
2. **`slices/` (Read-Only Base Slices)**:
   Default directory housing mounted `.slice/` folders, treated as immutable baselines at runtime.
3. **`overlay/` (Writable Memory Layer)**:
   The sole runtime write target for committed agent memories (`@overlay`).
4. **`staging/` (Prospective Final-State Buffer & Tombstones)**:
   Holds uncommitted mutations produced by `write(..., stage=True)`. **Staged files are strictly excluded from `.cache/index.sqlite` and never affect live `manifest()`, `search()`, or `read()` calls** until promoted via `apply()`.
   * **Prospective Final State**: Each file `staging/<id>.md` represents the complete prospective content of `overlay/<id>.md` after `apply()`. When `write(id, op="append" | "replace", stage=True)` targets an existing `overlay/<id>.md` that is not yet in `staging/`, MindSlice records the committed file's current `sha256` as `base_sha256` in `staging/.manifest.json` and (for `append`) copies `overlay/<id>.md` into `staging/<id>.md` before appending. Subsequent staged edits to `<id>` before `apply()` update `staging/<id>.md` while **preserving the original `base_sha256`** against `overlay/<id>.md`.
   * **Deletion Tombstones**: Calling `write(id, op="delete", stage=True)` on a card that exists in `overlay/<id>.md` removes `staging/<id>.md` (if present) and records an explicit tombstone entry in `staging/.manifest.json` (`{"op": "delete", "base_sha256": "<hash_of_overlay_file>"}`). If `<id>` existed only in `staging/`, both `staging/<id>.md` and its manifest entry are removed immediately.
5. **`.cache/workspace.lock` & `.cache/index.sqlite` (Reader/Writer Isolation & IDE Freshness)**:
   * **Shared/Exclusive Locking & Pending Journal Recovery**: All operations participate in `fcntl.flock` on `.cache/workspace.lock`. Read operations (`manifest`, `search`, `read`, `diff`) acquire a shared lock (`LOCK_SH`); write operations (`write`, `apply`, `discard`, `mount`, `unmount`) and index syncs acquire an exclusive lock (`LOCK_EX`). Before executing **any** operation, the engine checks whether `staging/.apply_journal.json` exists; if present (from an interrupted `apply()` in any process), it upgrades to `LOCK_EX`, finishes replaying the journal into `overlay/`, updates `.cache/index.sqlite`, and removes the journal before serving the request. Readers therefore never observe a partially applied batch.
   * **Automatic Detection of Normal Editor Changes**: While holding the lock before a query, MindSlice compares `(mtime_ns, size)` of mounted `.md`/`.toml` files against `.cache/index.sqlite`. If any normal editor save, file creation, rename, or deletion is detected, MindSlice upgrades to `LOCK_EX` and incrementally re-indexes the changed files in one SQLite transaction. For full cryptographic verification against edits that preserve both timestamp and byte size, callers can run `validate(rebuild_index=True)`.
   * **Ephemeral Telemetry**: Unlike FTS5 tables and link graphs, `read_count` and `last_read_at` in `.cache/index.sqlite` are best-effort ephemeral telemetry that cannot be reconstructed from Markdown if the cache is deleted.

---

## 3. Card Anatomy
Each `.md` file acts as a **Memory Card**. The target granularity is **one focused sub-topic per card** (5–15 atomic statements, ~10–50 lines), balancing context-window efficiency with semantic completeness.

### 3.1 Standard Card Example (TOML Frontmatter)
To uphold the zero-dependency Python 3.12+ standard library constraint (`tomllib`), cards use **`+++`-fenced TOML v1.0 frontmatter** restricted to a flat schema (`str` and `list[str]` fields):

```markdown
+++
title = "Python Backend Error Handling Conventions"
aliases = ["error-handling", "exception-policy"]
tags = ["python", "backend", "reliability"]
extends = []                    # Optional: @alias/path or slice-relative path
supersedes = []                 # Optional: @alias/path or slice-relative path
+++

All backend services must raise typed domain exceptions inherited from `AppError` and translate them into RFC 7807 Problem Details only at the HTTP boundary.

- Define domain-specific exceptions in `core/errors.py` inheriting from `AppError` rather than raising raw `ValueError` or `RuntimeError`.
- Never catch bare `Exception` inside service or repository layers unless wrapping a third-party SDK call with explicit context (`raise ExternalServiceError(...) from exc`).
- Map `AppError` subclasses to HTTP status codes exclusively inside the FastAPI exception middleware (see [[architecture/http-middleware]]).
- Log unexpected `5xx` unhandled exceptions with structured tracebacks and correlation IDs before returning a sanitized error payload (see [[observability/structured-logging]]).
- For retryable transient failures in async background workers, defer to the backoff rules in [[architecture/async-patterns]].
```

### 3.2 Purpose of Each Section & Address Scope Rules
1. **TOML Frontmatter (`+++ ... +++`) & Round-Trip Serialization**:
   * **Parsing & Serialization**: Parsed via `tomllib.loads()`. Because `json.dumps()` default escaping emits UTF-16 surrogates (`\ud83d...`) that TOML v1.0 rejects, MindSlice's serializer emits valid UTF-8 characters directly, escapes `\\`, `\"`, `\b`, `\t`, `\n`, `\f`, `\r`, and formats any remaining control characters (`U+0000`–`U+001F`, `U+007F`) as 4-digit `\uXXXX` scalars—verifying every generated frontmatter block with `tomllib.loads()` before writing to disk.
   * **`title`**: Canonical human-readable heading, indexed with highest weight in FTS5 BM25.
   * **`aliases`**: Synonyms or shorthand names used for lexical matching and `[[wikilink]]` resolution.
   * **`tags`**: Categorical labels for faceted filtering across slices.
   * **`extends` / `supersedes` *(Optional)***: Explicit lineage pointers to target cards.
2. **Address Scope Rules Inside Cards (`@alias/path` vs. Slice-Relative `path`)**:
   * References in `extends`, `supersedes`, and inline `[[wikilinks]]` support two forms:
     * **Namespace-Qualified (`@project/api/auth-flow`)**: Binds explicitly to the card in mount `@project`.
     * **Slice-Relative (`architecture/http-middleware`)**: When written inside a card without an `@alias` prefix, the reference resolves **strictly within the same containing slice** as the card itself—**never** via global workspace `precedence`. This guarantees that self-contained slices and `pack()` exports cannot have their internal links or lineage hijacked by unrelated cards with the same relative path in `@overlay` or other mounts.
3. **Summary Paragraph (1–2 Sentences, ≤240 chars recommended)**:
   * Placed immediately below the closing `+++` fence as a high-signal abstract returned in `search()` and neighbor previews.
4. **Body (Bulleted Atomic Statements + `[[Wikilinks]]`)**:
   * Discrete bullet points (`- ...`) that are easy to scan, diff in Git, and idempotently append or replace.

---

## 4. Multi-Slice Query Routing & Conflict Resolution

### 4.1 Three Read Modes & Per-Field Output Bounds
MindSlice structures retrieval as a three-stage funnel with **enforceable per-item field bounds, collection pagination, and explicit truncation flags** (`truncated: bool`, `total_*: int`, `next_offset: int | None`):

1. **Boot Context (`manifest`) — Paginated Mount & Folder Map**:
   * **Bounds**: Paginates mounts (`limit=20, offset=0`), truncates each mount's `description` to `160` chars, and caps top-level directory names at `max_folders_per_mount=10` (reporting `total_folders` and `truncated: bool`). Full `overview.md` files are omitted unless `include_overview=True` or read individually via `read("@alias/overview")`.
2. **Associative Search (`search`) — Paginated Card Previews**:
   * **Bounds**: Returns at most `k=10` cards (`offset=0` for pagination, plus `total_matches`). Each preview caps `summary` at `240` chars and 1-hop `[[wikilink]]` neighbors at `max_neighbors=3` (reporting `total_neighbors` and `truncated: bool`).
   * **Normalized BM25 Score**: Because SQLite's raw `bm25(fts, ...)` returns negative values where more negative is better, MindSlice defines `score = -bm25(fts, 10.0, 5.0, 3.0, 2.0, 1.0) > 0` (weighted across `title, aliases, tags, summary, body`) so higher scores always mean stronger matches.
   * **Lexical Analysis (Stdlib-Only, Script-Aware)**: Index and query text are NFKC-normalized. Spaced scripts use FTS5 `porter unicode61`. Scripts written without word spaces (Chinese, Japanese, Korean, Thai, Khmer, Myanmar, Tibetan) are rewritten by MindSlice before reaching FTS5: each run is indexed as grapheme unigrams plus overlapping bigrams, and each query run becomes OR-ed bigrams, so any substring matches without a dictionary or tokenizer extension. The analyzer version and Unicode database version are recorded in the index; a change triggers re-indexing.
   * **Coverage (Reported, Not Ranked)**: Each preview also reports `coverage`, the IDF-weighted share of the query it matches. Results stay ordered by `score`, then `precedence`: coverage-first ordering was evaluated and lost (`evals/retrieval/PLAN.md`).
   * **Query Feedback (Reported, Not Ranked)**: Every response also lists `unmatched_terms` (query words, or whole unspaced runs, that no card in scope contains). It tells an agent *why* a search came back empty or weak so it can rephrase; it never changes or reorders results. Spelling suggestions were evaluated and removed: they were mostly noise in small corpora, and the agent can correct a named word itself (`evals/retrieval/PLAN.md`).
3. **Exact Resolution (`read`) — Card Body + Paginated Lineage/Backlinks**:
   * **Bounds**: Returns the full card body (soft-linted by `validate()` at ≤50 lines, never hard-truncated mid-sentence), outbound `[[wikilinks]]`, up to `max_backlinks=10` (`backlinks_offset=0`, `total_backlinks`), and up to `max_extensions=5` (`extensions_offset=0`, `total_extensions`).

### 4.2 Unified Resolution Algorithm & Lineage Semantics
What does it mean to accept a `supersedes` edge? By default, writing a card to `overlay/` or mounting a slice authorizes its lineage edges (`follow_supersedes=True`). However, callers that do not trust lower-tier mounts (e.g., `role="runtime"`) to override curated mounts (`role="curated"`) can pass `follow_supersedes=["curated"]` (or `follow_supersedes=False`) to `search()` and `read()`, restricting automatic supersession forwarding to replacements whose mount `role` or `@alias` is in the trusted allowlist while still surfacing untrusted overrides in metadata: `superseded_by_untrusted` lists the untrusted replacements of the card returned, and `bypassed_replacements` (`{"address", "supersedes"}` items) those of every card the redirect passed through. Neither changes `status`: under the caller's policy, the card returned is the answer.

#### Step-by-Step `read(address, follow_supersedes=True)` Resolution Algorithm
1. **Initial Node Selection**:
   * If `address` is namespace-qualified (`@project/api/auth-flow`), select that exact node.
   * If `address` is an unqualified API argument (`api/auth-flow`), select the card at `api/auth-flow.md` from the mount with the highest `precedence`. (If other mounts also contain `api/auth-flow.md` without lineage links, record them in `shadows: ["@project/api/auth-flow"]`).
2. **Transitive Supersession Forwarding (`supersedes`)**:
   * Starting from the selected node `X`, follow active inbound `supersedes` edges (`X <- Y <- Z`, filtered by `follow_supersedes`) to the terminal replacement `Z`.
   * **Intra-Slice & Equal-Precedence Supersession**: Directed `supersedes` edges resolve within the same slice or `@overlay` (`@overlay/api/v2` supersedes `@overlay/api/v1`) by graph topology. Cycles are rejected at `write()` / `validate()` time.
   * **Competing Replacements**: If two active cards `Y1` and `Y2` both supersede `X` without one superseding the other, `read("X")` returns both previews under `competing_replacements` rather than guessing.
   * **Unrebased Extensions on a Superseded Baseline (`E extends B` + `R supersedes B`)**:
     * Extensions bind strictly to their **named target card (`B`)** and are **never silently rebased** onto `B`'s replacement `R` (since an exception written for `B` may be invalid or redundant under `R`).
     * When `read("B")` forwards to `R`, the response attaches `unrebased_extensions: ["@overlay/api/auth-edge-cases (extends @project/api/auth-flow)"]` so the caller knows `B` had an extension that has not been rebased onto `R`.
     * Conversely, if the caller explicitly calls `read("E")` (where `E` extends `B`, and `B` is superseded by `R`), `read("E")` composes `E` with its named baseline `B` and flags `baseline_superseded_by: ["@overlay/api/jwt-ttl"]` so the agent can inspect the original context and decide whether to rebase `E` onto `R` (`write(E, op="replace", extends=["@overlay/api/jwt-ttl"])`) or delete `E`.
     * The notice covers the whole `extends` closure: if `F extends E` and `E extends B`, `read("F")` also flags `baseline_superseded_by: ["@overlay/api/jwt-ttl"]`, and reports `missing_baselines` when a reference on the chain no longer resolves (a deleted baseline). `search()` previews carry the same two notices, so a dependent never looks plainly active on the results page while `read()` would flag it.
3. **Extension Composition (`extends` Closure on Active Baselines)**:
   * **Reading an Extending Card (`E extends B`)**: Whether `E` was reached via `read("@overlay/api/auth")` or via an unqualified `read("api/auth")` that selected `@overlay/api/auth`, `read()` fetches its named baseline `B` (`@project/api/auth`) and returns a **composed response** (`baseline: B` + `extension: E`) so a same-path extension never shadows away its own baseline.
   * **Reading a Base Card (`B`)**: If `B` has active inbound extensions (`E1, E2`), `read(B)` attaches up to `max_extensions` in its `extensions` list (ordered by `precedence` then `mtime_ns`, with `total_extensions` and `next_offset` if truncated).

#### Search Behavior: Match-Through Supersession & Implicit Contradictions
1. **Match-Through Redirection for `supersedes`**:
   * Superseded cards remain in FTS5 as retrieval routes. If `search("token expiration")` matches superseded card `A` (`@project/api/auth-flow`), and `A`'s trusted replacement `B` (`@overlay/api/jwt-ttl`) uses `"JWT TTL"`, `search()` redirects the hit to return `B` with `matched_via_superseded: "@project/api/auth-flow"`. If both `A` and `B` match the query directly, they are deduplicated into `B` using `max(score(A), score(B))` (where `score = -bm25(...) > 0`).
   * **Interaction with `source` Filtering**: When `search(query, source="@project")` matches `A` inside `@project` while its replacement `B` lives in `@overlay`, `search()` returns `A` (honoring the `source` filter) stamped with `status: "superseded_by: @overlay/api/jwt-ttl"`.
2. **Implicit Cross-Slice Contradictions (Co-Hits Without Lineage)**:
   * Co-matching cards without `extends` or `supersedes` links are **never silently filtered**. All matches are returned in `score` order stamped with `(@alias, role, precedence, mtime)`.

---

## 5. External Interface (9 Orthogonal Primitives)
MindSlice exposes **9 orthogonal primitives** across three groups. All 9 are available via Python and CLI; **Group A** forms the **4-tool MCP Server** exposed to runtime agents.

### Group A: Online Read/Write (Exposed to Agents / MCP)
1. **`manifest(limit=20, offset=0, max_folders_per_mount=10, include_overview=False)`**:
   * Acquires `LOCK_SH` (replaying any interrupted journal and syncing `(mtime_ns, size)` changes under `LOCK_EX` if needed) and returns the paginated mount table, `role` tags, card counts, 160-char descriptions, and bounded top-level folder lists.
2. **`search(query, source=None, tags=None, k=10, offset=0, max_neighbors=3, follow_supersedes=True)`**:
   * Runs an FTS5 query and returns up to `k` Card Previews (`address`, `role`, `precedence`, `coverage`, `score`, `title`, `tags`, 240-char `summary`, up to `max_neighbors` 1-hop `[[wikilinks]]`, `matched_via_superseded` / `superseded_by` status, `bypassed_replacements` for redirected hits, and the same `baseline_superseded_by` / `missing_baselines` notices as `read()`), plus `total_matches`, `truncated`, `next_offset` and `unmatched_terms`.
3. **`read(address, follow_supersedes=True, max_backlinks=10, backlinks_offset=0, max_extensions=5, extensions_offset=0)`**:
   * Resolves `address` via Section 4.2, returns the full card (plus composed baseline/extensions, `sha256` revision token, outbound `[[wikilinks]]`, paginated `backlinks`, and any `unrebased_extensions` / `bypassed_replacements` / `baseline_superseded_by` / `missing_baselines` notices), and updates ephemeral `read_count` / `last_read_at` in `.cache/index.sqlite`.
4. **`write(id, op="create" | "replace" | "append" | "delete", content=None, summary=None, title=None, tags=None, aliases=None, extends=None, supersedes=None, stage=False, if_match=None)`**:
   * Acquires `LOCK_EX` on `.cache/workspace.lock`, validates that no lineage cycle is introduced, verifies TOML frontmatter round-trip parsing, and mutates `<id>.md` in `overlay/` (or in `staging/` when `stage=True`):
     * **`op="create"`**: Creates a new card. Fails with `AlreadyExistsError` if the target already exists with different content; succeeds idempotently if byte-identical.
     * **`op="replace"`**: Replaces frontmatter, summary, and/or body. Accepts `if_match="<sha256>"` to reject updates if the target card changed since it was read.
     * **`op="append"`**: Appends bullet statement(s) (`- ...`) to an existing card (initializing `staging/<id>.md` from `overlay/<id>.md` first when `stage=True` and not yet staged), deduplicating identical bullet lines for idempotent retries.
     * **`op="delete"`**: Deletes `overlay/<id>.md` (or writes a deletion tombstone to `staging/.manifest.json` when `stage=True`).

### Group B: Slice Management, Linting & Packaging
5. **`mount(path, alias, precedence, role="baseline")` / `unmount(alias)`**:
   * Acquires `LOCK_EX`, updates `mounts.toml`, and incrementally syncs `.cache/index.sqlite`.
6. **`validate(slice_path=None, rebuild_index=False)`**:
   * When `rebuild_index=True`, acquires `LOCK_EX` and rebuilds `.cache/index.sqlite` from scratch using full `sha256` verification. Lints `+++` TOML frontmatter, summary presence, card length (>50 lines warning), broken `[[wikilinks]]`, and circular `extends`/`supersedes` chains.
7. **`pack(output_path, prefix=None, tags=None, include_deps=False)`**:
   * Deterministically exports selected cards from `overlay/` (filtered by `prefix` and/or `tags`) into a standalone `.slice/` directory or archive:
     * **Source-First Reference Resolution**: Every reference in `extends`, `supersedes`, and inline `[[wikilinks]]` (whether written as `@overlay/<path>` or as a slice-relative `<path>`) is first resolved against `@overlay` to its canonical target `(target_alias, target_path)`.
     * **Target Classification & Closure**:
       * *Included `@overlay` target*: Written as a slice-relative path (`<target_path>`) in the exported card, resolving strictly within the exported slice (Section 3.2).
       * *External slice target (`target_alias != "@overlay"`)*: Retained as a qualified `@alias/<target_path>` reference and recorded under `dependencies` in `slice.toml`.
       * *Excluded `@overlay` target* (e.g., `overlay/team/profile.md` references `"shared/preferences"` or `"@overlay/shared/preferences"` when exporting only `prefix="team/"`): By default (`include_deps=False`), `pack()` **rejects the export** with `UnresolvedExportDependencyError` listing the missing `@overlay` targets; if `include_deps=True`, `pack()` automatically includes the transitive `@overlay` dependencies in the exported slice.

### Group C: Transactional Sandbox Operations (`staging/`)
8. **`diff(scope="staging" | "overlay")`**:
   * Acquires `LOCK_SH` and returns a structured summary and unified diff of pending changes in `staging/` (checking `staging/.manifest.json` `base_sha256` preconditions against current `overlay/` files) or active overrides in `overlay/`.
9. **`apply()` / `discard()`**:
   * **`apply()`**: Acquires `LOCK_EX` on `.cache/workspace.lock`:
     1. **Precondition & Graph Verification**: Verifies every entry in `staging/.manifest.json` against `overlay/` (`current_sha256 == base_sha256`, or file must be absent when `base_sha256 is null`) and checks the combined graph for cycles. Aborts cleanly with a conflict report before touching `overlay/` if any check fails.
     2. **Ordered Journaled Promotion**:
        a. Writes and `fsync`s `staging/.apply_journal.json`.
        b. Moves staged `.md` files into `overlay/` and unlinks tombstoned `overlay/` files (tolerating already-moved or already-unlinked files during crash replay). During replay, an action whose `overlay/` target changed since it was journaled is skipped, never forced: its staged file or tombstone stays in `staging/`.
        c. Synchronizes `.cache/index.sqlite` in a single SQLite transaction.
        d. Removes `staging/.manifest.json` (and any empty `staging/` subdirectories), keeping only the entries of skipped actions with their original `base_sha256`, so `diff()` reports the conflict against the version the change was based on.
        e. **Removes `staging/.apply_journal.json` strictly last.**
        Because `.apply_journal.json` is removed only after `.manifest.json` and SQLite are finalized, any crash prior to step (e) leaves the recovery marker intact for the next reader or writer to finish idempotently under `LOCK_EX`.
   * **`discard()`**: Acquires `LOCK_EX` and clears `staging/` and `staging/.manifest.json`.

---

## 6. Worked Examples (Deterministic Behavior Matrix)
Assuming `@overlay` (`precedence=100, role="runtime"`) and `@project` (`precedence=50, role="curated"`):

| Scenario | State on Disk | `search()` Behavior | `read()` / `apply()` Behavior |
| :--- | :--- | :--- | :--- |
| **1. Unqualified Path Collision (No Lineage)** | `@project/api/auth` and `@overlay/api/auth` both exist; neither declares `extends` or `supersedes`. | `search("auth")` returns **both** cards ranked by `score = -bm25(...)`, tagged with `(@project, role="curated")` and `(@overlay, role="runtime")`. | `read("api/auth")` selects `@overlay/api/auth` (`precedence=100`) and lists `shadows: ["@project/api/auth"]`. Both remain addressable via `@alias/api/auth`. |
| **2. Same-Path Extension (`extends`)** | `@overlay/api/auth` declares `extends = ["@project/api/auth"]`. | `search("auth")` returns both cards with their `extends` link metadata. | Both `read("api/auth")` and `read("@project/api/auth")` return the **composed view**: `@project/api/auth` baseline + `@overlay/api/auth` delta statements. |
| **3. Supersession with Terminology Shift** | `@project/api/auth` has `"token expiration"`. `@overlay/api/jwt` has `supersedes = ["@project/api/auth"]` and `"JWT TTL"`. | `search("token expiration")` matches `@project/api/auth` and **redirects** to `@overlay/api/jwt` with `matched_via_superseded: "@project/api/auth"`. | `read("api/auth")` or `read("@project/api/auth")` returns `@overlay/api/jwt` (`redirected_from: "@project/api/auth"`). Passing `follow_supersedes=["curated"]` or `False` returns `@project/api/auth` with `superseded_by_untrusted`. |
| **4. Source-Scoped Search on Superseded Card** | Same as #3, but caller runs `search("token expiration", source="@project")`. | Returns `@project/api/auth` (honoring `source="@project"`) stamped with `status: "superseded_by: @overlay/api/jwt"`. | `read("@project/api/auth", follow_supersedes=False)` returns the `@project` card with the `superseded_by` header. |
| **5. Intra-Overlay Replacement Chain** | `@overlay/api/v2` supersedes `@overlay/api/v1`, which supersedes `@project/api/auth`. | `search()` redirects matches on `auth` or `v1` to the terminal leaf `@overlay/api/v2` using `max(score)`. | `read("@project/api/auth")` and `read("@overlay/api/v1")` transitively resolve to `@overlay/api/v2`. |
| **6. Replaced Baseline with Unrebased Extension (`E extends B`, `R supersedes B`)** | `E` (`@overlay/api/auth-edge`) has `extends = ["@project/api/auth"]`. Later, `R` (`@overlay/api/jwt`) has `supersedes = ["@project/api/auth"]`. | `search()` redirects hits on `B` to `R`; `E` remains searchable with `baseline_superseded_by: ["@overlay/api/jwt"]`. | `read("@project/api/auth")` returns `R` + `unrebased_extensions: ["@overlay/api/auth-edge"]` (**never silently applying `E` to `R`**). `read("@overlay/api/auth-edge")` composes `E` with its named target `B` and flags `baseline_superseded_by: ["@overlay/api/jwt"]`. |
| **7. Staged Op Transition (`append -> IDE edit -> delete`)** | `overlay/api/a.md` (`hash=h1`) is staged via `write("api/a", op="append", stage=True)` (recording `base_sha256=h1`), then edited in IDE (`hash=h2`), then deleted via `write("api/a", op="delete", stage=True)`. | Live `search()` is unaffected by `staging/`; lazy `(mtime_ns, size)` check immediately indexes `h2` for `overlay/api/a.md`. | The staged `delete` transitions `a.md` to a tombstone while **retaining `base_sha256=h1`**. `apply()` detects `h1 != h2` and aborts under `LOCK_EX` without deleting `overlay/api/a.md`. |
| **8. Staged Create (`base_sha256=null`) vs. External Creation** | `write("api/new", op="create", stage=True)` stages a new card (`base_sha256=null`, "must remain absent"). Before `apply()`, `overlay/api/new.md` is created externally (`hash=h2`). | Live `search()` indexes the externally created `overlay/api/new.md` (`h2`) on the next query. | `diff("staging")` flags an existence conflict (`expected absent, found h2`). `apply()` aborts without overwriting `overlay/api/new.md`. |
| **9. Filtered `pack()` with Excluded Relative Reference** | `overlay/team/profile.md` contains `extends = ["shared/prefs"]` (or `[[shared/prefs]]`). Caller runs `pack("team.slice", prefix="team/")`. | N/A (packaging operation). | `pack()` resolves `"shared/prefs"` against `@overlay` to `("@overlay", "shared/prefs")`, sees it is excluded by `prefix="team/"`, and **rejects the export** with `UnresolvedExportDependencyError` (unless `include_deps=True`, which pulls `shared/prefs.md` into `team.slice`). |
| **10. `pack` -> `validate` -> `mount` -> `read` (Slice-Relative Scope)** | `@overlay/db/pool` extends `@overlay/db/conn`. Exported via `pack("db.slice", prefix="db/")` and mounted as `@db` (`precedence=40`), while `@overlay/db/conn` is later modified. | `pack()` writes slice-relative `db/conn` in `db.slice/db/pool.md`. `validate("db.slice")` passes. | `read("@db/db/pool")` resolves `extends = ["db/conn"]` **strictly inside `@db`** (`@db/db/conn`), never binding to `@overlay/db/conn` despite `@overlay` having `precedence=100`. |
| **11. Crash During `apply()` Before Journal Removal** | Process crashes during `apply()` after moving files and removing `staging/.manifest.json`, but before removing `staging/.apply_journal.json`. | Next `search()` sees `.apply_journal.json` while acquiring `LOCK_SH`, upgrades to `LOCK_EX`, idempotently finishes index sync, removes `.apply_journal.json` last, and serves the search. | Next `read()` or `write()` performs the exact same journal recovery under `LOCK_EX` before executing, ensuring no reader or writer sees partial state or stale staging files. |

---

## 7. End-to-End Slice Lifecycle
This repository also ships a zero-dependency `slice-builder` `SKILL.md` (plus an exportable prompt template) so any agent can drive semantic consolidation and slice authoring outside the core storage mechanism:

1. **5-Minute Cold Start (Bootstrap from Raw Sources)**:
   * Point an agent equipped with the `slice-builder` skill at existing project artifacts (`README.md`, `CLAUDE.md`, ADRs, runbooks, or source directories).
   * The agent decomposes dense documentation into atomic memory cards with `+++` TOML frontmatter, generates `overview.md` and `slice.toml`, verifies structural integrity with `validate()`, and mounts the resulting `.slice/` via `mount()`.
2. **Organic Daily Refining (Runtime Growth in `overlay/` & `staging/`)**:
   * During everyday tasks, base slices remain read-only while the agent navigates memory progressively via `manifest() -> search() -> read()`.
   * New insights, debugging lessons, and user corrections are recorded via `write(op="create" | "replace" | "append" | "delete")` into `overlay/` (or isolated in `staging/` for review via `diff()` and `apply()`).
3. **Consolidate, Scrub & Share (Distill via `slice-builder` + `pack`)**:
   * When `overlay/` accumulates valuable domain knowledge, the user or agent runs a consolidation pass using `diff("overlay")`, the `slice-builder` skill, and `pack()`:
     * **Semantic Consolidation (via Agent Skill)**: Where `overlay/` contains `extends`, `supersedes`, or unrebased extensions, the `slice-builder` agent reads the cards and rewrites them into clean, self-contained cards—keeping semantic synthesis in the policy/skill layer rather than inside the storage engine.
     * **Scrub & Package**: Strip machine-specific paths, secrets, and ephemeral session noise, export with `pack(output_path, prefix="topic/")`, verify with `validate()`, and publish the `.slice/` directory as a Git repository or `.tar.gz`/`.zip` archive.
