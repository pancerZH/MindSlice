# MindSlice

A **lightweight, zero-dependency, human-readable** layered memory engine for LLM agents.
MindSlice is the *filesystem layer* for agent memory: plain Markdown cards in directories
("slices"), a writable overlay, a transactional staging buffer, and a disposable SQLite
index. It holds no LLM calls and no built-in trust heuristics; memory *policy* plugs in
through files, skills and caller-supplied trust rules.

See [`MindSlice_design.md`](MindSlice_design.md) for the full design.

- **Python 3.12+ standard library only** (`sqlite3` FTS5, `tomllib`, `fcntl`); POSIX (Linux/macOS).
- **Markdown + TOML is the source of truth.** Delete `.cache/` at any time; it is rebuilt from disk
  (only best-effort `read_count` / `last_read_at` telemetry is lost).
- **Read-only base slices + writable `overlay/`**, with explicit `extends` / `supersedes` lineage.
- **Three-stage retrieval funnel**: `manifest()` -> `search()` -> `read()`, with hard output bounds.
- **4-tool MCP server** (`manifest`, `search`, `read`, `write`) for agents.

## Install

```bash
pip install -e .          # provides the `mindslice` command
# or run in place without installing:
python -m mindslice --help
```

## Quick start

```bash
mindslice init my-workspace && cd my-workspace

# Mount a read-only slice (any directory of cards)
mindslice mount ./slices/project-kb.slice --alias @project --precedence 50 --role curated

# Agents record what they learn into @overlay
mindslice write api/jwt-ttl --title "JWT TTL" \
  --summary "Sessions moved to signed JWTs with a 30 minute TTL." \
  --content "- The JWT TTL is 30 minutes." --supersedes @project/api/auth-flow

mindslice manifest                       # boot context
mindslice search "token expiration"      # hits on the old card redirect to the replacement
mindslice read api/auth-flow --markdown  # composed view, with lineage notices
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
             if_match=card["sha256"])
```

## Workspace layout

```text
workspace/
├── mounts.toml        # mount table: path, @alias, precedence, role
├── slices/            # read-only base slices (*.slice/ directories)
├── overlay/           # the only runtime write target (@overlay, precedence 100, role "runtime")
├── staging/           # prospective final state for overlay/ (never indexed until apply())
│   ├── .manifest.json       # base_sha256 preconditions + delete tombstones
│   └── .apply_journal.json  # exists only while an apply() batch is in flight
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

Address forms: `@alias/path` targets one mount. A bare `path` passed **to the API** resolves to
the highest-precedence mount; written **inside a card**, it resolves only within that card's own slice.

## The 9 primitives

| Group | Primitive | Notes |
| :-- | :-- | :-- |
| A (MCP) | `manifest(limit=20, offset=0, max_folders_per_mount=10, include_overview=False)` | mounts, roles, counts, 160-char descriptions, bounded folder lists |
| A (MCP) | `search(query, source=None, tags=None, k=10, offset=0, max_neighbors=3, follow_supersedes=True)` | `score = -bm25(10,5,3,2,1) > 0`; supersession redirect; 240-char summaries |
| A (MCP) | `read(address, follow_supersedes=True, max_backlinks=10, backlinks_offset=0, max_extensions=5, extensions_offset=0)` | forwarding, extends composition, shadows, backlinks, `sha256` |
| A (MCP) | `write(id, op="create"\|"replace"\|"append"\|"delete", content, summary, title, tags, aliases, extends, supersedes, stage=False, if_match=None)` | overlay only; cycle checks; verified TOML round-trip |
| B | `mount(path, alias, precedence, role)` / `unmount(alias)` | updates `mounts.toml` and the index |
| B | `validate(slice_path=None, rebuild_index=False)` | lints from disk; rebuild re-hashes everything |
| B | `pack(output_path, prefix=None, tags=None, include_deps=False)` | deterministic dir / `.zip` / `.tar.gz` export |
| C | `diff(scope="staging"\|"overlay")` | structured summary + unified diffs |
| C | `apply()` / `discard()` | precondition-checked, journaled, crash-recoverable |

Every primitive is a `Workspace` method and a CLI subcommand (`mindslice <cmd> --help`).
Output is JSON (`--compact` for one line). Errors are JSON on stderr with a stable `code`.

### Lineage in one paragraph

`R supersedes B`: reads and search hits on `B` forward to `R` (transitively, to the terminal
replacement), annotated `redirected_from` / `matched_via_superseded`. Pass
`follow_supersedes=False` or an allowlist such as `["curated"]` (roles or `@aliases`) to stop
forwarding from untrusted mounts; untrusted replacements are still reported in
`superseded_by_untrusted`. Two rival replacements are never guessed between (`competing_replacements`).
`E extends B`: reading either returns the composed view (`baselines` / `extensions`). Extensions are
never silently rebased: if `B` is superseded, `read(B)` reports `unrebased_extensions` and
`read(E)` reports `baseline_superseded_by`.

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

Coverage-first ordering was tried and evaluated ([`evals/retrieval`](evals/retrieval/PLAN.md)). On a
harder, multi-candidate holdout it trailed BM25 order by 0.026 nDCG@5 overall (0.065 in English) and
gained only 0.002 on tiny corpora. In a small corpus, words that are rare but carry no topic ("do",
"when") earned too much coverage credit. The engine went back to BM25 order.

The analysis uses only Python's `unicodedata` and `re`, with SQLite's built-in FTS5 tokenizer: no
jieba, no ICU, and no SQLite extension. The index records the analyzer and Unicode-database versions,
and re-indexes itself when either changes (for example after a Python upgrade). Read counts survive.

Lexical search is not morphological. Korean or Japanese inflections that change the stem
syllables (`이끌었다` vs `이끈다`) and Simplified/Traditional variants (`认证` vs `認證`) are
different strings, just as `ran`/`run` are in English.

## Concurrency & durability

- Reads take `LOCK_SH` and writes take `LOCK_EX` (`fcntl.flock`) on `.cache/workspace.lock`.
- Before every operation, the engine re-indexes files whose `(mtime_ns, size)` changed. That covers
  editor saves, creations, renames and deletions. It also finishes any interrupted `apply()` it finds
  (`staging/.apply_journal.json`), upgrading to `LOCK_EX` only when needed. An edit that keeps both
  mtime and size identical is invisible to this cheap check; `validate(rebuild_index=True)` catches it.
- File writes are atomic (temp file, `fsync`, `os.replace`). `apply()` removes the journal last, so a
  crash at any point is finished idempotently by the next reader or writer.

## Slice lifecycle

[`skills/slice-builder/SKILL.md`](skills/slice-builder/SKILL.md) is an agent skill for the full
lifecycle. It covers cold start from project docs, daily refinement in `@overlay`, and consolidation
plus `pack()` for sharing. [`prompt-template.md`](skills/slice-builder/prompt-template.md) is the same
guidance as a portable prompt.

## Development

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

`evals/retrieval/` is a small English and Chinese retrieval-quality evaluation of `search()`. It reports
nDCG@5, Recall@10 and MRR@10 with bootstrap intervals, compares against alternative systems, and fixes its
pass lines in advance. See [its README](evals/retrieval/README.md) and [plan](evals/retrieval/PLAN.md).

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
  `unrebased_extensions` items are `{"address", "extends"}` objects.
- **Search redirects respect filters.** A hit is redirected only if the replacement passes the same
  `source` and `tags` filters. Otherwise the original card is returned, stamped with its status.
- **`if_match` compares against the write target.** That is the overlay file, or the staged file
  when `stage=True` (`diff()` reports `staged_sha256`).
- **Deleting a missing card** succeeds with `changed: false` and a warning (an idempotent retry).
- **Orphan files in `staging/`** (no manifest entry, e.g. human drafts) count as creates that
  require the overlay path to still be absent.
- **Root `overview.md`** is readable and linkable, but is excluded from search results and card counts.
- **Windows.** The `msvcrt` locking adapter has not been run yet (see the TODO in
  `tests/test_workspace.py`). It has no shared mode, so readers serialize on Windows.
