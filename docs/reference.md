# MindSlice reference

How MindSlice works: the file formats, every primitive, and the engine's guarantees. To get started, see the
[setup guide](getting-started.md); for benchmark results, see [evaluations](evaluations.md). The full design, with its
behavior matrix, is [design specification](design.md).

## Principles

A **lightweight, zero-dependency, human-readable** layered memory engine for LLM agents.
MindSlice is the *filesystem layer* for agent memory: plain Markdown cards in directories
("slices"), a writable overlay, a transactional staging buffer, and a disposable SQLite
index. It holds no LLM calls and no built-in trust heuristics; memory *policy* plugs in
through files, skills and caller-supplied trust rules.

- **Python 3.12+ standard library only** (`sqlite3` FTS5, `tomllib`, `fcntl`); POSIX (Linux/macOS).
- **Markdown + TOML is the source of truth.** Delete `.cache/` at any time; it is rebuilt from disk
  (only best-effort `read_count` / `last_read_at` telemetry is lost).
- **Read-only base slices + writable `overlay/`**, with explicit `extends` / `supersedes` lineage.
- **Three-stage retrieval funnel**: `manifest()` -> `search()` -> `read()`, with hard output bounds.
- **Always-loaded cards** (`load = "always"`): persona, language and standing instructions reach
  every session at start, with no query; changes to them wait for the user's approval.
- **4-tool MCP server** (`manifest`, `search`, `read`, `write`) for agents.
- **Mount any folder of Markdown as is**: plain notes and legacy `---` YAML frontmatter are indexed without
  conversion; `+++` TOML cards are the native format.

## Command line and Python

The same workspace, driven from the command line and from Python:

```bash
mindslice init my-workspace && cd my-workspace

# Mount a read-only slice (any directory of cards)
mindslice mount ./slices/project-kb.slice --alias @project --precedence 50 --role curated
mindslice mount ~/notes                  # any Markdown folder, no conversion (alias from its name: @notes)

# Agents record what they learn into @overlay
mindslice write api/jwt-ttl --title "JWT TTL" \
  --summary "Sessions moved to signed JWTs with a 30 minute TTL." \
  --content "- The JWT TTL is 30 minutes." --supersedes @project/api/auth-flow \
  --reason "The auth migration replaced the previous session scheme."

mindslice manifest                       # boot context
mindslice search "token expiration"      # hits on the old card redirect to the replacement
mindslice read api/auth-flow             # composed view, with lineage notices
```

Python:

```python
from mindslice import Workspace

with Workspace("my-workspace") as ws:
    ws.write("user-preferences/tooling", summary="The user prefers uv over pip.",
             content=["Use `uv run` for scripts.", "Use `uv add` for dependencies."], tags=["tooling"])
    hits = ws.search("uv dependencies", k=5)
    card = ws.read(hits["results"][0]["address"])
    ws.write("user-preferences/tooling", op="append", content="- Pin Python with `uv python pin`.",
             if_match=card["sha256"], reason="The project now pins its Python version with uv.")
```

Every primitive is a `Workspace` method and a CLI subcommand (`mindslice <cmd> --help`).
Every command prints human-readable text by default; add `--json` (before or after the subcommand)
for the structured result, or `--compact` for single-line JSON. Errors go to stderr with a stable
`code`: `error [code]: message` by default, a JSON object with `--json`.

## Workspace layout

```text
workspace/
├── mounts.toml        # mount table: path, @alias, precedence, role
├── .bake-plan.json    # saved workspace bake review; excluded from exports
├── slices/            # read-only base slices (*.slice/ directories)
├── overlay/           # the only runtime write target (@overlay, precedence 100, role "runtime")
├── staging/           # prospective final state for overlay/ (never indexed until apply())
│   ├── .manifest.json       # base_sha256 preconditions + delete tombstones
│   └── .apply_journal.json  # exists only while an apply() batch is in flight
├── .history/          # durable, engine-owned change metadata; not a cache
│   ├── changes.jsonl  # proposals, applied/discarded changes and baked versions
│   └── .pending.json  # exists only during a recoverable history/content transaction
└── .cache/            # disposable: index.sqlite + workspace.lock
```

A slice is just a directory (version it with Git, ship it as `.zip` / `.tar.gz`):

```text
python-backend.slice/
├── slice.toml           # optional: name, version, description (<=160), alias, dependencies
├── overview.md          # optional: entry point, read("@alias/overview")
├── coding-conventions.md
└── architecture/
    └── async-patterns.md
```

## Cards

```markdown
+++
title = "Python Backend Error Handling Conventions"
aliases = ["error-handling", "exception-policy"]
tags = ["python", "backend", "reliability"]
extends = []                    # @alias/path or slice-relative path
supersedes = []
+++

One or two sentence summary (<= 240 chars), shown in search previews.

- Atomic statements, one per bullet, with [[architecture/http-middleware]] links.
```

**Plain Markdown needs no conversion.** A note without frontmatter is titled by its first `# heading` (or its
file name) and summarized by its first prose paragraph. Legacy `---` YAML frontmatter (Obsidian, Jekyll, Hugo)
is read as a flat subset: `title`, `aliases`, `tags`, `extends`, `supersedes` and other scalar keys (shown as
`meta`); nested mappings are skipped with a warning. Any existing file name is addressable
(`@notes/2024-01-01 (draft) & notes`), while new card ids stay link-safe. `write()` keeps a YAML block verbatim
on body edits and writes `+++` TOML when it changes the card's fields; `validate()` notes each such card's format.

Add `load = "always"` to a card that every session should read at start (see
[Always-loaded cards](#always-loaded-cards)). The default, `load = "as-needed"`, needs no line.

Address forms: `@alias/path` targets one mount. A bare `path` passed **to the API** resolves to
the highest-precedence mount; written **inside a card**, it resolves only within that card's own slice.

## The primitives

| Group | Primitive | Notes |
| :-- | :-- | :-- |
| A (MCP) | `manifest(limit=20, offset=0, max_folders_per_mount=10, include_overview=False, include_always=True)` | mounts, roles, counts, 160-char descriptions, bounded folder lists, always-loaded cards |
| A (MCP) | `search(query, source=None, tags=None, k=10, offset=0, max_neighbors=3, follow_supersedes=True)` | `score = -bm25(10,5,3,2,1) > 0`; supersession redirect; 240-char summaries |
| A (MCP) | `read(address, follow_supersedes=True, max_backlinks=10, backlinks_offset=0, max_extensions=5, extensions_offset=0)` | forwarding, extends composition, shadows, backlinks, `sha256` |
| A (MCP) | `write(id, op="create"\|"replace"\|"append"\|"delete", content, summary, title, tags, aliases, extends, supersedes, stage=None, if_match=None, load=None, reason=None)` | overlay only; cycle checks; verified TOML round-trip; `affected_backlinks` / `affected_extensions` when it supersedes or deletes; changes to always-loaded cards are staged |
| A | `boot()` | resolved always-loaded cards; CLI `boot` emits the full startup payload, `--cards-only` emits card content |
| B | `mount(path, alias, precedence, role, retire_overlay=True)` / `unmount(alias)` | updates `mounts.toml` and the index; retires overlay copies the slice holds unchanged |
| B | `status()` | all mounts, pending review files and conflicts, dirty slices and unassigned overlay cards |
| B | `card_history(address=None, limit=20, offset=0)` | recorded events and reasons, newest first; metadata only; deleted addresses remain inspectable |
| B | `explain(address, follow_supersedes=True, max_extensions=5, extensions_offset=0)` | read selection, lineage, physical sources and verified reasons; does not increment read telemetry |
| B | `rollback(alias, path=None, dry_run=False, revision=None)` | switch a slice pointer to a recorded predecessor or explicit directory; overlay/staging preserved; revision checks a reviewed preview |
| B | `backup(output)` / `Workspace.restore(source, destination)` | verified directory snapshot and restore to a new workspace, including external mounts and available recorded versions |
| B | `validate(slice_path=None, rebuild_index=False)` | lints from disk; rebuild re-hashes everything |
| B | `bake(alias=None, output_path=None, prefix=None, tags=None, include_deps=False, dry_run=False, plan=None)` | omitted alias executes a workspace plan; named new targets require `prefix`; old folders stay untouched |
| B | `plan_bake(assignments=None, resume=True)` | propose all overlay destinations; exact card IDs map to aliases or null (defer) |
| C | `diff(scope="staging"\|"overlay")` | structured summary + unified diffs |
| C | `apply(ids=None)` / `discard(ids=None)` | all pending cards by default; exact IDs select a subset; `[]` selects none; journaled and crash-recoverable |
| C | `review(accept, reject, *, revision, dry_run=False)` | mixed accept/reject batch using the staging `diff()` revision; dry-run returns dependencies/conflicts before execution |

### CLI overview and output modes

All commands print human-readable output by default, and `--json` is the only switch to structured
output; whether stdout is a terminal never changes the format. Recovery commands include
`history [CARD]`, `explain CARD`, `rollback ALIAS`, `backup DIRECTORY` and
`restore BACKUP --output NEW_WORKSPACE`.
Rollback supports `--to DIRECTORY`, `--dry-run` and `--yes`; it requires confirmation before
changing a mount. Backup and restore require new destinations and never overwrite existing ones.
The MCP server still exposes only its four online memory tools. See
[history and recovery](history-and-recovery.md) for semantics, limitations and examples.

`mindslice status` lists every mount (alias, directory, precedence, role and card count), pending
review files (create/modify/delete, approval reasons and staging conflicts), dirty slices, and
unassigned overlay cards. A **dirty slice** has applied overlay cards extending, superseding or
shadowing its cards, ready for a future bake. A card related to several slices is counted under each;
within one slice it is counted once in `total`, but may appear in several relation counts. Unassigned
cards have no such relation to a mounted slice. Changes still in staging appear under pending review.
External edits to mounted files are indexed normally but are not tracked as dirty against a baseline.
`status --json` returns the same overview as structured data, without card bodies or patches.
It also includes `memory_state` (saved overlay cards, mounted cards, pending changes and unassigned
cards) and `next_step`. Unassigned cards are already saved and available to retrieval; they simply
have no relationship assigning them to a mounted slice. Bake is optional packaging/versioning.

`mindslice doctor [--json]` checks local runtime/FTS5, mounts, validation, index integrity, boot
payload generation and a real subprocess MCP handshake plus `manifest`. It uses the same Python
interpreter and selected workspace, with a bounded subprocess timeout. Exit 0 means local checks
passed (warnings may remain), exit 1 means a check failed. The report always identifies client
session loading as unverified; it does not inspect or modify client settings. Follow the
[first-session check](getting-started.md#verify-your-first-session) to verify the connected app.

`mindslice review [ID...]` interactively collects accept/reject/leave-pending choices and checks
dependencies before one final confirmation. `apply ID...` and `discard ID...` are noninteractive
selections; omitting IDs affects every pending card. IDs refer to exact staging paths, with optional
`.md` suffix or `@overlay/` qualification. Selection does not resolve mounted-card aliases.
Selective application checks references against the resulting live state: dependencies on pending-only
cards and newly broken live links block the batch. Already broken references remain validation concerns.
Legacy apply-all preserves its existing permissive handling of dangling links.
Staging diffs expose `revision`, `references` and `impact` alongside patches and reasons.
`Workspace.review` rejects stale revisions before changing any selected files; `dry_run=True`
returns `ready`, `conflicts`, `accept`, `reject` and `pending`. A mixed review uses the same
recovery journal as apply. Unselected proposals survive completion and recovery.

`mindslice diff` prints a unified patch of staging changes. `--scope overlay` compares applied overlay
cards with their baselines. `diff --json` returns the structured report; reasons and conflicts in text mode are
reported on stderr. The redundant `--patch` flag is removed. `apply` approves staged changes and
`discard` drops them. `unmount alias` removes a mount while preserving its directory; the writable
overlay cannot be unmounted.

`mindslice boot` emits the session startup payload: usage instructions, resolved always-loaded cards,
and the onboarding hint when the workspace is empty. `boot --cards-only` emits only the composed card
content, with no instruction header or onboarding text; with no standing cards it emits nothing.
`--json` controls format independently: full mode includes `instructions` and the boot snapshot;
cards-only mode includes just `cards` and `total`. Approval reminders go to stderr in both formats.
The former `--mcp-instructions` flag is removed; startup hooks should call plain `boot`.

### CLI aliases and reference shorthand

Mount alias arguments accept `alias` and `@alias`: `mount --alias`, `unmount`, `bake`, and
`search --source` normalize them during CLI parsing. Output uses the canonical `@alias` form.
Path arguments (`mount`'s directory, `--output`, `--prefix`, and `write`'s overlay card id) remain paths.

In CLI `read`, `write --extends`, and `write --supersedes`, `alias/path` can abbreviate `@alias/path`
when that target exists and no relative card matches. Read checks relative paths and card aliases
across the workspace; write lineage checks them within the overlay. If both interpretations resolve,
the CLI returns `ambiguous_address`, listing the candidates. Use `@alias/path` to choose the mount or
`./alias/path` to force a relative reference. Unrelated files in the shell's current directory do not
create a reference conflict. Explicit qualified addresses always select the named mount.

This shorthand is confined to CLI reference arguments. `write --alias` still defines arbitrary card
aliases; `--follow` still accepts roles or explicit `@aliases`. Markdown links, persisted relative
lineage references, and Python/MCP addressing keep their original slice-relative rules.

### Lineage in one paragraph

`R supersedes B`: reads and search hits on `B` forward to `R` (transitively, to the terminal
replacement), annotated `redirected_from` / `matched_via_superseded`, so `B`'s wording still finds
`R`; prefer it to deleting `B` when a fact changes. Pass
`follow_supersedes=False` or an allowlist such as `["curated"]` (roles or `@aliases`) to stop
forwarding from untrusted mounts; untrusted replacements are still reported, in
`superseded_by_untrusted` for the card returned and in `bypassed_replacements` for the cards a
redirect passed through. Two rival replacements are never guessed between (`competing_replacements`).
`E extends B` (`E` refines `B`, adds an exception or if-then rule to it, or depends on it as a
premise): reading either returns the composed view (`baselines` / `extensions`). Extensions are
never silently rebased: if `B` is superseded, `read(B)` reports `unrebased_extensions` and
`read(E)` reports `baseline_superseded_by`. That notice covers the whole `extends` chain (a
baseline of a baseline counts), `missing_baselines` names a reference on it that no longer resolves
(a deleted baseline), and `search()` previews carry both.

### Who still points at a retired card

A `write()` that supersedes or deletes a card answers, under the same `LOCK_EX`, with the cards that still
point at it: `affected_backlinks` (`{"address", "links_to"}`: they `[[link]]` to it) and `affected_extensions`
(`{"address", "extends"}`: they extend it), each ordered by precedence then address, capped at 25, with
`total_affected_backlinks` / `total_affected_extensions`. Items in read-only slices carry `"read_only": true`.
It is a query of the index (plus staged changes for `stage=True`), recomputed from the state the write leaves,
so a retry reports the same; the engine never edits those cards. Updating them is the agent's job, in the same
session, and is easier when cards are named by durable slot (`team/lead`), not by value
(`team/lead-sarah-chen`): a link to a slot can stay, a link to a value-named card keeps stating the old value.

## Always-loaded cards

`load = "always"` works in the overlay and in every mounted slice. The overlay location is not required.
Folders under the workspace's `slices/` directory are not automatically mounted: register each with
`mindslice mount /path/to/slice`. The folder may live anywhere on disk. `boot()` and `manifest()` collect
the always-loaded cards from all registered mounts.

Some memory is not looked up but always in effect: who the agent is, which language the user wants,
rules for every reply. Mark such a card with `load = "always"`:

```markdown
+++
title = "Agent persona: Mira"
load = "always"
+++

You are Mira, a concise, friendly pair programmer.

- Answer in short paragraphs; prefer showing code over describing it.
```

MindSlice makes these cards available without a search query. The chat app must deliver them to the model:

- **MCP**: the cards are appended to the server's `initialize` instructions and listed in `manifest()`
  as `always_loaded`. Clients must include those instructions or the tool result in the model's context;
  handling of server instructions depends on the client. MCP registration applies to that client only,
  not to other apps using the same model server. When a harness lazy-loads or drops `initialize`
  instructions, wire `mindslice -w /path/to/workspace boot` into its session-start
  hook (see [`skills/mindslice-setup/SKILL.md`](../skills/mindslice-setup/SKILL.md)). If the set changes
  mid-session (a slice is mounted, the user approves a change), the next tool result carries an
  `always_loaded_update` with the new or changed cards.
- **Empty workspace onboarding**: when only `@overlay` is mounted, no cards are indexed, and nothing is
  staged (`boot()` sets `empty_workspace: true`), MCP `initialize` instructions and `mindslice boot`
  append an `# Empty memory workspace` cold-start hint, and `manifest()` includes `onboarding_hint`. Both disappear as soon as the first card is written, staged, or mounted.
- **Cards without tool instructions**: `mindslice boot --cards-only` prints only standing card content,
  ready for a system prompt (`claude --append-system-prompt "$(mindslice boot --cards-only)"`, or paste
  into any chat). `boot()` in Python continues to return the structured card snapshot.
- **`mount()`** lists the always-loaded cards the new slice brings.

The set is each always-loaded card resolved the way `read()` resolves it: a card superseded in
`@overlay` gives way to its replacement, and extensions are composed in. Otherwise these cards behave
like any other: searchable, readable, packable.

Because they shape every session, changes to them wait for the user. `write()` stages a change to the
always-loaded context by default (`stage=None`) and says why in `requires_approval`: creating or
marking a card always-loaded, editing or deleting one, or extending or superseding one (or a baseline
composed into one). The user reviews with `mindslice diff` and approves with `mindslice apply` (or
drops it with `mindslice discard`); `boot()` and `manifest()` list what is `awaiting_approval`. Over
MCP the agent cannot opt out (`stage=false` is ignored for these cards) and has no `apply` tool. At the
Python API or the CLI, `stage=False` / `--no-stage` writes directly: there the caller is the approver.

## MCP server

```bash
mindslice -w /path/to/workspace mcp                 # stdio, newline-delimited JSON-RPC
mindslice -w /path/to/workspace mcp --stage-writes  # force agent writes into staging/ for review
```

Claude Code:

```bash
claude mcp add mindslice -- python -m mindslice -w /path/to/workspace mcp
```

Generic MCP client config:

```json
{"mcpServers": {"mindslice": {"command": "python3", "args": ["-m", "mindslice", "-w", "/path/to/workspace", "mcp"]}}}
```

## Search, ranking & multilingual text

`search()` is lexical (SQLite FTS5, BM25 over `title, aliases, tags, summary, body` weighted
`10, 5, 3, 2, 1`). MindSlice analyzes text itself before it reaches FTS5, so behavior does not
depend on how SQLite was compiled:

- **Normalization.** Index and query text are NFKC-normalized, and variation selectors and
  zero-width characters are dropped. Full-width `ＪＷＴ` matches `JWT`, and half-width `ﾄｰｸﾝ`
  matches `トークン`. Tags and aliases compare NFKC + case-folded.
- **Latin and other spaced scripts** go through `porter unicode61` (case folding, stemming).
  `term*` is a prefix match.
- **Unspaced scripts (Chinese, Japanese, Korean, Thai, Khmer, Myanmar, Tibetan)** have no reliable
  word spaces, so each run is indexed as unigrams plus overlapping bigrams
  (`令牌过期` -> `令 牌 过 期 令牌 牌过 过期`). A unit is a letter plus its combining marks, so Thai
  vowels, the Khmer coeng and Tibetan stacks stay together.
  Any substring of two or more characters matches through its bigrams, and a single character
  matches through its unigram. Supplementary-plane ideographs (e.g. `𠮷`) and iteration marks
  (`々`) are handled.
- **Queries never fail silently on unspaced compounds.** An unspaced query run becomes its bigrams,
  OR-ed like ordinary words. `雾凇拼音` still finds a card that only says `雾凇词库`, usually ranked
  below cards that contain more of the query.

Results are ordered by `score = -bm25(...)`, then mount precedence, then address. Every preview
also reports `coverage`: the share of the query the card matches, with each word weighted by how rare
it is in the corpus (smoothed IDF). A CJK run earns the weighted share of its bigrams present, or full
credit if the card contains it verbatim. Coverage tells an agent how much of its question a card
covered; it does not order results.

Every response also lists `unmatched_terms`: query words (or whole CJK runs) that no card in scope
contains. An agent can then fix a typo or try another word instead of concluding the memory is empty.
It changes and reorders nothing.

Lexical search finds a card only by words it contains, so synonyms belong in each card's `aliases`
(indexed just below the title). The shared [card-format guide](../skills/slice-builder/references/card-format.md) says what
they should cover.

Why search works this way (aliases instead of spelling suggestions, BM25 order instead of coverage order) is in
[evaluations](evaluations.md#search-decisions-the-evaluations-settled).

The analysis uses only Python's `unicodedata` and `re`, with SQLite's built-in FTS5 tokenizer: no
jieba, no ICU, and no SQLite extension. The index records the analyzer and Unicode-database versions,
and re-indexes itself when either changes (for example after a Python upgrade). Read counts survive.

Lexical search is not morphological. Korean or Japanese inflections that change the stem
syllables (`이끌었다` vs `이끈다`) and Simplified/Traditional variants (`认证` vs `認證`) are
different strings, just as `ran`/`run` are in English.

## Change reasons and history

`write(..., reason="...")` (CLI `--reason`) explains why a card is created, replaced, appended to
or deleted. It is optional for compatibility; when supplied it must be a nonempty string. MCP
instructions ask agents to supply it. Only the engine writes `.history/changes.jsonl`: callers
provide the reason, never IDs, timestamps or log entries. Reasons are not card frontmatter or
`slice.toml` fields, are not searched, and are not included in baked directories or archives.

Each effective write returns a `change_id`. Its JSONL event records `schema_version`, `event_id`,
UTC `timestamp`, `change_id`, `address`, `op`, `reason`, and before/after SHA-256 hashes (null for
an absent file). No-op retries produce no new event. Writes without a reason still produce a
record, with `reason: null`. The lifecycle is:

| Operation | Event |
| :-- | :-- |
| Write directly to overlay | `applied` |
| Write to staging | `proposed`; manifest retains its `change_id` |
| Apply staging | `applied`, linked to the original proposal IDs |
| Discard staging, or delete a staged-only creation | `discarded`, linked to the proposal IDs |
| Bake | `baked`, with included change IDs, card hashes, alias, version, absolute `path`, `output` and `previous_path` |

Pending cards do not participate in live reads/search until applied. Their proposals still exist
in history, including after discard. Multiple edits preserve multiple reasons; applying does not
invent a new reason. `diff()` and `status()` attach `change_ids` and `changes` to relevant cards;
text status displays reasons and text diff sends them to stderr, keeping stdout a unified patch.
Reasons for applied overlay content are matched by hash; external edits break the recorded chain
instead of inheriting an unrelated reason. Editor writes and hand-authored staging files have no
agent-supplied reason; applying a legacy/manual staged entry records an applied change without one.
Engine reference rewrites during retirement also receive their own applied records and reasons.

History stays in the workspace after bake and cache rebuilds. Back up `.history/` with the workspace;
it cannot be reconstructed from current Markdown. There is no SQLite history database. The JSONL
file records metadata, not old card bodies, so it is not a content rollback store.

## Concurrency & durability

- Reads take `LOCK_SH` and writes take `LOCK_EX` (`fcntl.flock`) on `.cache/workspace.lock`.
- Before every operation, the engine re-indexes files whose `(mtime_ns, size)` changed. That covers
  editor saves, creations, renames and deletions. It also finishes any interrupted `apply()` it finds
  (`staging/.apply_journal.json`) or history transaction (`.history/.pending.json`), upgrading to
  `LOCK_EX` only when needed. An edit that keeps both
  mtime and size identical is invisible to this cheap check; `validate(rebuild_index=True)` catches it.
- File writes are atomic (temp file, `fsync`, `os.replace`). `apply()` removes the journal last, so a
  crash at any point is finished idempotently by the next reader or writer. Recovery never overwrites
  or deletes an `overlay/` file edited since the crash: that change stays staged, with its original
  base, and `diff()` shows the conflict.
- History writes share the workspace lock. Direct writes, staging edits, discard and bake's mount/
  overlay updates first save a recovery journal, then change files and append/fsync events. Apply
  carries its events in the existing apply journal. Recovery deduplicates by event ID, repairs an
  interrupted final JSONL line and removes the journal last. A history transaction with externally
  changed files (or missing/changed baked output) stops with `history_error`, preserving the files
  and journal for inspection. Complete malformed log records also stop writes. The temporary
  recovery journal can contain intended file contents; the permanent JSONL log contains metadata.

## Slice lifecycle

[`skills/mindslice-setup/SKILL.md`](../skills/mindslice-setup/SKILL.md) (with
[`uninstall.md`](../skills/mindslice-setup/uninstall.md)) covers initial installation, harness MCP +
session-start hook configuration, three-way conversational onboarding, and clean uninstallation.
[`skills/slice-builder/SKILL.md`](../skills/slice-builder/SKILL.md) builds one or more initial slices from
multiple source files or one large document. Source boundaries do not determine slice boundaries:
one document can feed several slices, and several documents can feed one. It plans slices by
independent mounting, reuse, sharing or versioning, then plans cards within each slice. Validation
covers source evidence, per-slice structure, cross-slice dependencies and representative retrieval.
Its [standalone prompt](../skills/slice-builder/prompt-template.md) provides the same workflow without
skill support. A shared build ledger maps source units to slice/card addresses, stays outside all generated
slices, and is separate from engine change history. Each slice has its own manifest, overview and
unique alias; mount individual slice directories, not their parent output directory.
[`skills/slice-maintainer/SKILL.md`](../skills/slice-maintainer/SKILL.md) covers existing memory updates,
lineage repair and consolidation through `bake()`. Routine agent writes also receive MCP instructions.

### Workspace bake review

Bare `mindslice bake` reviews all applied overlay cards. It proposes a destination when exactly one
mounted slice is related through extends, supersedes or a shared card path. Multiple candidates
remain unresolved; directory grouping helps review but never creates slice ownership by itself.
All overlay cards, including an overlay `overview.md`, are accounted for. A staged-only card is not
part of the input; an overlay card with a pending edit defaults to deferred. Explicitly assigning
such a card blocks execution until it is applied, discarded or deferred again.

In a terminal, unresolved cards are grouped by folder and candidate destinations. Enter an alias
(with or without `@`) to use an existing slice or create a new one. `inspect` shows summaries,
reasons and patches; `split` assigns cards individually; `defer` leaves them in overlay. The final
review supports inspecting all changes, editing selections and one `Bake all` confirmation. Cancel,
EOF or Ctrl-C during review preserve choices without creating versions. No lock is held at prompts.

```bash
mindslice bake
mindslice bake --fresh                               # ignore saved choices
mindslice bake --dry-run --json                      # full plan, no saved-plan/output writes
mindslice bake --assign 'research/=@research' --defer 'scratch/' --dry-run --json > plan.json
mindslice bake --plan plan.json --yes --json
```

`--assign SELECTOR=ALIAS` and `--defer SELECTOR` are repeatable. A selector is an exact overlay card
ID, a directory prefix ending in `/`, or quoted `'*'` for all cards. Explicit card assignments allow
new aliases without a redundant `--prefix`. Named-target options (`--output`, `--prefix`, `--tag`,
`--include-deps`, `--name`, `--description`, `--slice-version`) remain available with `bake @alias`;
workspace batches use default versioned directories under `slices/`, not archives.

Choices are saved in `<workspace>/.bake-plan.json` during ordinary review, including cancellation
or a noninteractive unresolved plan. Unchanged cards retain their choices across retries; a changed
card is reviewed again. `--fresh` ignores that draft. The draft contains review metadata and patches,
is excluded from bake exports, and is removed by a successful batch commit. `--dry-run` can read the
draft but does not save one or publish outputs (normal recovery/index maintenance may still run).

Noninteractive or `--json` execution never prompts. Unresolved destinations or validation blockers
return a structured `bake_conflict` with the plan. A resolved noninteractive plan still requires
`--yes`; this skips confirmation, never validation. Exported `--plan` inputs are bound to their
workspace, content revision and planned output paths. Stale inputs fail before execution; regenerate
a dry-run after edits. Plan files are review artifacts, not a way to override output paths.

Before publishing, the engine validates the combined future references, dependency declarations,
frontmatter and lineage graph. Cross-slice references between assigned cards are rewritten to their
new aliases. A selected card referring to an unassigned/deferred overlay card blocks execution;
assign its dependency too. Same-path extensions need content consolidation by the caller. The engine
moves and rewrites references; it performs no semantic synthesis.

All output trees are prepared first, then a single recoverable history transaction switches all
mounts, retires overlay cards, rebases remaining references and appends each slice's baked event.
Recoverable interruptions replay the transaction before another workspace operation. Preparation/
publication errors before the transaction leave active mounts and overlay intact; an abrupt process
exit before journaling can leave unmounted output directories. Previous slice directories stay
unchanged. External edits are checked by content hash before commit and during recovery.

Copies needed by staged drafts or unchanged read-only mounts stay in overlay and appear in
`retained_overlay_cards` with reasons. Deferral and retention are both reflected in
`remaining_overlay_cards`; baking successfully does not necessarily empty overlay. The receipt's
`baked` list contains `alias`, `version`, absolute `path`/`output`, `previous_path`, card IDs,
dependencies and `history_event_id`; `pending_review` reports the number of staged changes left.

Python callers explicitly execute their reviewed plan (no terminal interaction):

```python
plan = ws.plan_bake({"research/evaluation": "@research", "scratch/note": None})
# Inspect plan["slices"], plan["unassigned"], plan["blockers"], and plan["cards"].
if plan["ready"]:
    result = ws.bake(plan=plan)
```

`ws.bake(dry_run=True)` returns the current workspace plan. `ws.bake()` executes a fully resolved
plan or raises on unresolved cards/blockers; Python invocation itself authorizes execution.

### Bake one named slice

Use `bake(alias)` (`mindslice bake @alias`) to create or update a slice. The separate `pack` command and
Python method have been removed.

```bash
mindslice bake @python --prefix python/               # create and mount a slice from matching overlay cards
mindslice bake @python                               # update it from related overlay cards
mindslice bake @python --prefix python/ --output ./python-next.slice
mindslice bake @python --dry-run                      # inspect the plan without writing
```

For an alias that is not mounted, `prefix` (`--prefix`) is required, even when `tags` or `output_path`
is supplied. It filters overlay card paths; it does not specify the output directory. An explicit
empty prefix (`--prefix ''`, or `prefix=""` in Python) selects all overlay paths, with `tags` applied
as an additional filter. A new slice starts at version `0.1.0`, precedence `50`, role `baseline`, and
is mounted automatically. No separate `mount` step is needed.

For an existing alias, the new slice contains a copy of its folder (`.git` excluded) plus the selected
overlay cards. Without `prefix` / `tags`, it takes the overlay cards that extend or supersede one of
the slice's cards or share a path with one. `--output` chooses another destination; otherwise the
output is `<workspace>/slices/<name>.slice`, or `<name>-2.slice`, `-3` ... when taken (a new slice uses
the alias as its name). The new folder takes over the mount in one atomic mount-table update, keeping
the same alias, precedence and role. The old directory stays unchanged and is no longer mounted.
A `slice.toml` version of the form `1.2.3` becomes `1.2.4`. Optional `name`, `description` and `version`
keyword arguments (`--name`, `--description`, `--slice-version`) override the manifest metadata.

`include_deps` (`--include-deps`) pulls in overlay cards referenced by the selection; without it,
references to excluded overlay cards raise `unresolved_export_dependency`. References between baked
cards become slice-relative; references to other mounts stay qualified and are recorded in
`slice.toml` dependencies. When updating, references to the existing slice also become slice-relative.
A card that supersedes or shadows the slice card at its own path replaces that file; one that extends
it there would lose the baseline, so bake refuses it (`bake_conflict`) until the two are merged into
one card. Selected cards with staged changes are also refused before writing.

Baking retires the overlay copies and rewrites references to them in the overlay cards that stay
(`[[python/style]]` -> `[[@python/python/style]]`). The result reports `retired_overlay_cards` and
`rebased_references`; copies needed by staged cards are kept as `shadowing_overlay_cards`, and
references from read-only mounts that cannot be rewritten are reported as `broken_references`.
Mounting an imported slice also retires identical overlay copies, keeping edited or staged copies;
`retire_overlay=False` (`--keep-overlay`) disables this retirement for `mount()`.

For sharing, `--output python.zip`, `python.tar.gz` or `python.tgz` additionally writes a deterministic
archive of the complete baked slice. The mountable directory is created under `<workspace>/slices/`;
the result's `output` points to the archive and `path` to the mounted directory. Directory outputs use
the same value for both. Existing non-empty directories and existing archive files are never overwritten.
`dry_run` (`--dry-run`) reports the selected cards and destinations without creating either output,
changing mounts or retiring overlay cards. [`prompt-template.md`](../skills/slice-builder/prompt-template.md)
contains portable slice-authoring guidance.

## Notes on interpretation

The design leaves a few details open. These are the choices v1 makes:

- **Search query syntax.** Free-text words are OR-ed and ranked by BM25 (see
  [Search, ranking & multilingual text](#search-ranking--multilingual-text)). An empty query with
  `tags` lists that facet. `tags` filters are all-of. The card path is also indexed, alongside
  `aliases`.
- **Competing replacements.** Forwarding follows the unambiguous part of a chain and stops at the
  fork. For `A <- B <- {C, D}`, `read(A)` lands on `B` with `competing_replacements: [C, D]`.
- **`superseded_by`** lists the direct replacements. `status` is `"active"`,
  `"superseded_by: <addrs>"` or `"competing_replacements"`. `matched_via_superseded` is a list.
  `unrebased_extensions` items are `{"address", "extends"}` objects; `bypassed_replacements` items
  are `{"address", "supersedes"}` objects. For `A <- {B, C}` with only `B` trusted, `read(A)` lands
  on `B` (`status: "active"`) with `bypassed_replacements: [{"address": C, "supersedes": A}]`.
- **Search redirects respect filters.** A hit is redirected only if the replacement passes the same
  `source` and `tags` filters. Otherwise the original card is returned, stamped with its status.
- **`if_match` compares against the write target.** That is the overlay file, or the staged file
  when `stage=True` (`diff()` reports `staged_sha256`).
- **Deleting a missing card** succeeds with `changed: false` and a warning (an idempotent retry).
- **Orphan files in `staging/`** (no manifest entry, e.g. human drafts) count as creates that
  require the overlay path to still be absent.
- **Root `overview.md`** is readable and linkable, but is excluded from search results and card counts.
- **Windows.** The `msvcrt` adapter has no shared mode, so readers serialize.
  Open-file sharing errors leave interrupted apply batches journaled for recovery
  after the handle is closed. Directory flushes are best effort; process-exit
  recovery tests do not establish power-loss durability.

## Development

The public Python API is exported from `mindslice`; `workspace.py` is the facade used by
the CLI and MCP server. Implementation modules are grouped by responsibility:

| Package | Responsibility |
| --- | --- |
| `model` | Cards, addresses, lineage, text normalization and TOML formatting |
| `storage` | Workspace configuration, file I/O, locking and change history |
| `retrieval` | Indexing, lexical analysis and queries |
| `operations` | Writing, staging, boot payloads, status, impact and validation |
| `baking` | Single and batch baking, slice transfer and archives |
| `interfaces` | CLI, interactive bake review and MCP |

Shared card parsing and reconstruction belong in `model`; shared card-file reading belongs
in `storage`, so readers do not depend on the writer. Subpackage initializers stay lightweight.
Use `from mindslice import Workspace` for integrations; implementation imports use the
subpackage paths (for example, `mindslice.interfaces.mcp_server`). The `mindslice` command
and `python -m mindslice` use the same CLI entry point.

```bash
python3 -m unittest discover -s tests -t .
```

The suite covers every row of the design's behavior matrix (section 6) plus the format, CLI and MCP layers.

`tests/functional/` holds end-to-end **journeys**. Each starts from a workspace state (no slice, 3 slices,
or 24 slices), replays user sessions, and ends by consolidating, baking and exporting slices. In each
session a scripted agent drives MindSlice through the real MCP server; human steps between sessions
review staging, edit files and mount slices. After every session, base slices must be byte-identical
and `validate()` must report no errors. Every journey must also survive a cold-cache restart, and two
replays must produce identical normalized transcripts. Each `Session` keeps the user message, the
scripted tool calls and agent-agnostic outcome checks separate, so a real LLM agent can later replace
the script.

The evaluation suites under `evals/` are described in [evaluations](evaluations.md#the-evaluation-suites).
