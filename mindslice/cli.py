"""``mindslice`` command-line interface (all 9 primitives + ``boot``, ``bake``, ``init`` and ``mcp``)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .boot import render_markdown as render_boot
from .errors import ApplyConflictError, MindSliceError
from .workspace import Workspace


def _follow(value: str | None) -> bool | list[str]:
    if value is None:
        return True
    low = value.strip().lower()
    if low in ("", "all", "true", "yes", "1"):
        return True
    if low in ("none", "false", "no", "0"):
        return False
    return [v.strip() for v in value.split(",") if v.strip()]


def _emit(data: Any, compact: bool) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=None if compact else 2)
    sys.stdout.write(text + "\n")


def _content(args: argparse.Namespace) -> str | None:
    if args.content is not None and args.content_file is not None:
        raise SystemExit("use either --content or --content-file, not both")
    if args.content_file is None:
        return args.content
    if args.content_file == "-":
        return sys.stdin.read()
    return Path(args.content_file).read_text(encoding="utf-8")


def _cwd_path(value: str) -> str:
    return str(Path(value).expanduser().absolute())


def render_markdown(result: dict[str, Any]) -> str:
    """Human-readable rendering of a ``read()`` result (composed view)."""
    out: list[str] = []

    def card(c: dict[str, Any], heading: str) -> None:
        out.append(f"{heading} {c['title']}  ({c['address']}, role={c['role']}, precedence={c['precedence']})")
        if c.get("summary"):
            out.append("")
            out.append(c["summary"])
        if c.get("body", "").strip():
            out.append("")
            out.append(c["body"].rstrip())
        out.append("")

    notes = []
    if result.get("redirected_from"):
        notes.append("redirected from " + result["redirected_from"] + " via " + " -> ".join(result.get("lineage_path", [])))
    for key in ("shadows", "superseded_by_untrusted", "baseline_superseded_by"):
        if result.get(key):
            notes.append(f"{key}: {', '.join(result[key])}")
    if result.get("unrebased_extensions"):
        notes.append("unrebased_extensions: " + ", ".join(
            f"{u['address']} (extends {u['extends']})" for u in result["unrebased_extensions"]))
    if result.get("bypassed_replacements"):
        notes.append("bypassed_replacements: " + ", ".join(
            f"{b['address']} (supersedes {b['supersedes']})" for b in result["bypassed_replacements"]))
    if result.get("competing_replacements"):
        notes.append("competing_replacements: " + ", ".join(c["address"] for c in result["competing_replacements"]))
    for base in result.get("baselines", []):
        card(base, "## Baseline:")
    card(result, "#")
    for ext in result.get("extensions", []):
        card(ext, "## Extension:")
    if notes:
        out.append("---")
        out.extend(f"> {n}" for n in notes)
    out.append(f"<!-- status: {result.get('status')} sha256: {result.get('sha256')} -->")
    return "\n".join(out).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    # Global options are accepted before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-w", "--workspace", default=argparse.SUPPRESS,
                        help="workspace root (default: $MINDSLICE_WORKSPACE or nearest dir with mounts.toml)")
    common.add_argument("--compact", action="store_true", default=argparse.SUPPRESS, help="single-line JSON output")
    p = argparse.ArgumentParser(prog="mindslice", parents=[common],
                                description="Layered, human-readable long-term memory for LLM agents.")
    p.add_argument("--version", action="version", version=f"mindslice {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    _add_parser = sub.add_parser
    sub.add_parser = lambda *a, **kw: _add_parser(*a, parents=[common], **kw)  # type: ignore[method-assign]

    s = sub.add_parser("init", help="create a workspace (mounts.toml, overlay/, staging/, slices/, .cache/)")
    s.add_argument("path", nargs="?", default=".")

    s = sub.add_parser("manifest", help="boot context: paginated mount & folder map")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--max-folders", type=int, default=10, dest="max_folders_per_mount")
    s.add_argument("--include-overview", action="store_true")
    s.add_argument("--no-always", action="store_false", dest="include_always", help="omit the always-loaded cards")

    s = sub.add_parser("boot", help="print the always-loaded cards (load = \"always\") as Markdown for a system prompt")
    s.add_argument("--json", action="store_true", help="JSON instead of Markdown")
    s.add_argument("--mcp-instructions", action="store_true",
                   help="include MCP server instructions and empty-workspace hint (for session-start hooks)")

    s = sub.add_parser("search", help="associative BM25 search returning card previews")
    s.add_argument("query")
    s.add_argument("--source", action="append", help="restrict to mount alias (repeatable)")
    s.add_argument("--tag", action="append", dest="tags", help="require tag (repeatable, all must match)")
    s.add_argument("-k", type=int, default=10)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--max-neighbors", type=int, default=3)
    s.add_argument("--follow", help="follow_supersedes: all (default) | none | comma-separated roles/@aliases")

    s = sub.add_parser("read", help="exact resolution of an address (with lineage composition)")
    s.add_argument("address")
    s.add_argument("--follow", help="follow_supersedes: all (default) | none | comma-separated roles/@aliases")
    s.add_argument("--max-backlinks", type=int, default=10)
    s.add_argument("--backlinks-offset", type=int, default=0)
    s.add_argument("--max-extensions", type=int, default=5)
    s.add_argument("--extensions-offset", type=int, default=0)
    s.add_argument("--markdown", action="store_true", help="render the composed card as Markdown instead of JSON")

    s = sub.add_parser("write", help="create/replace/append/delete a card in overlay/ (or staging/)")
    s.add_argument("id", help="overlay-relative card id, e.g. api/auth-edge-cases")
    s.add_argument("--op", choices=("create", "replace", "append", "delete"), default="create")
    s.add_argument("--content", help="body text (append: bullet statements)")
    s.add_argument("--content-file", help="read content from file ('-' = stdin)")
    s.add_argument("--summary")
    s.add_argument("--title")
    s.add_argument("--tag", action="append", dest="tags")
    s.add_argument("--alias", action="append", dest="aliases")
    s.add_argument("--extends", action="append")
    s.add_argument("--supersedes", action="append")
    s.add_argument("--load", choices=("always", "as-needed"),
                   help="always = loaded into every session without a query (persona, language, standing instructions)")
    s.add_argument("--stage", action="store_true", default=None,
                   help="write to staging/ instead of overlay/ (default: only changes to always-loaded cards are staged)")
    s.add_argument("--no-stage", action="store_false", dest="stage", help="write to overlay/ even if always-loaded")
    s.add_argument("--if-match", help="sha256 the target must currently have")

    s = sub.add_parser("mount", help="mount a read-only slice directory")
    s.add_argument("path")
    s.add_argument("--alias")
    s.add_argument("--precedence", type=int, default=50)
    s.add_argument("--role", default="baseline")
    s.add_argument("--keep-overlay", action="store_true",
                   help="keep @overlay copies of this slice's cards (by default, unchanged packed copies are retired)")

    s = sub.add_parser("unmount", help="remove a mount")
    s.add_argument("alias")

    s = sub.add_parser("validate", help="lint the workspace or a slice directory")
    s.add_argument("slice_path", nargs="?")
    s.add_argument("--rebuild-index", action="store_true", help="rebuild .cache/index.sqlite with full sha256 verification")

    s = sub.add_parser("pack", help="export overlay cards into a standalone .slice (dir, .zip, .tar.gz)")
    s.add_argument("output")
    s.add_argument("--prefix")
    s.add_argument("--tag", action="append", dest="tags")
    s.add_argument("--include-deps", action="store_true")
    s.add_argument("--name")
    s.add_argument("--description")
    s.add_argument("--slice-version", default="0.1.0")
    s.add_argument("--alias")

    s = sub.add_parser("bake", help="bake overlay cards into a new version of a mounted slice and mount it instead")
    s.add_argument("alias", help="the mounted slice to bake into, e.g. @persona")
    s.add_argument("--output", help="where the new slice goes (default: slices/<name>.slice, or <name>-2.slice ...); "
                   "the old folder is left as it was")
    s.add_argument("--prefix", help="bake the overlay cards under this path (default: the ones that extend, "
                   "supersede or share a path with the slice's cards)")
    s.add_argument("--tag", action="append", dest="tags", help="bake the overlay cards with this tag (repeatable)")
    s.add_argument("--include-deps", action="store_true", help="also bake overlay cards the selection references")
    s.add_argument("--dry-run", action="store_true", help="show what would move, write nothing")

    s = sub.add_parser("diff", help="show staged changes (or overlay overrides)")
    s.add_argument("--scope", choices=("staging", "overlay"), default="staging")
    s.add_argument("--patch", action="store_true", help="print a unified diff instead of JSON")

    sub.add_parser("apply", help="promote staging/ into overlay/ (journaled, all-or-nothing)")
    sub.add_parser("discard", help="drop everything in staging/")

    s = sub.add_parser("mcp", help="serve the 4-tool MCP server (manifest/search/read/write) over stdio")
    s.add_argument("--stage-writes", action="store_true", help="force every agent write into staging/")
    return p


def _open(args: argparse.Namespace) -> Workspace:
    root = args.workspace or os.environ.get("MINDSLICE_WORKSPACE")
    return Workspace(root) if root else Workspace.discover()


def main(argv: Sequence[str] | None = None) -> int:
    from .mcp_server import ensure_utf8_stdio

    ensure_utf8_stdio()  # JSON output is UTF-8 (CJK-safe) regardless of the console locale
    args = build_parser().parse_args(argv)
    args.workspace = getattr(args, "workspace", None)
    args.compact = compact = getattr(args, "compact", False)
    try:
        if args.command == "init":
            target = Path(args.workspace or args.path)
            with Workspace.init(target) as ws:
                _emit({"workspace": str(ws.root), "mounts": str(ws.root / "mounts.toml")}, compact)
            return 0
        if args.command == "mcp":
            from .mcp_server import serve

            with _open(args) as ws:
                serve(ws, stage_writes=args.stage_writes)
            return 0
        with _open(args) as ws:
            return _dispatch(ws, args, compact)
    except ApplyConflictError as exc:
        _emit(exc.to_dict(), compact)
        return 2
    except MindSliceError as exc:
        sys.stderr.write(json.dumps(exc.to_dict(), ensure_ascii=False) + "\n")
        return 1
    except (ValueError, TypeError, OSError) as exc:
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False) + "\n")
        return 1


def _dispatch(ws: Workspace, args: argparse.Namespace, compact: bool) -> int:
    cmd = args.command
    if cmd == "manifest":
        _emit(ws.manifest(args.limit, args.offset, args.max_folders_per_mount, args.include_overview,
                          args.include_always), compact)
    elif cmd == "boot":
        result = ws.boot()
        if args.json:
            if args.mcp_instructions:
                from .mcp_server import format_instructions

                result = dict(result, instructions=format_instructions(result))
            _emit(result, compact)
        else:
            if args.mcp_instructions:
                from .mcp_server import format_instructions

                text = format_instructions(result)
                sys.stdout.write(text if text.endswith("\n") else text + "\n")
            else:
                sys.stdout.write(render_boot(result["cards"]))
            for item in result.get("pending_approval", []):
                sys.stderr.write(f"awaiting approval: @overlay/{item['id']} ({item['reason']}); "
                                 "review with `mindslice diff`, approve with `mindslice apply`\n")
    elif cmd == "search":
        _emit(ws.search(args.query, args.source, args.tags, args.k, args.offset, args.max_neighbors, _follow(args.follow)), compact)
    elif cmd == "read":
        result = ws.read(args.address, _follow(args.follow), args.max_backlinks, args.backlinks_offset,
                         args.max_extensions, args.extensions_offset)
        if args.markdown:
            sys.stdout.write(render_markdown(result))
        else:
            _emit(result, compact)
    elif cmd == "write":
        _emit(ws.write(args.id, args.op, _content(args), args.summary, args.title, args.tags, args.aliases,
                       args.extends, args.supersedes, args.stage, args.if_match, args.load), compact)
    elif cmd == "mount":
        _emit(ws.mount(_cwd_path(args.path), args.alias, args.precedence, args.role,
                       retire_overlay=not args.keep_overlay), compact)
    elif cmd == "unmount":
        _emit(ws.unmount(args.alias), compact)
    elif cmd == "validate":
        result = ws.validate(_cwd_path(args.slice_path) if args.slice_path else None, args.rebuild_index)
        _emit(result, compact)
        return 0 if result["ok"] else 1
    elif cmd == "pack":
        _emit(ws.pack(_cwd_path(args.output), args.prefix, args.tags, args.include_deps, name=args.name,
                      description=args.description, version=args.slice_version, alias=args.alias), compact)
    elif cmd == "bake":
        _emit(ws.bake(args.alias, _cwd_path(args.output) if args.output else None, args.prefix, args.tags,
                      args.include_deps, args.dry_run), compact)
    elif cmd == "diff":
        result = ws.diff(args.scope)
        if args.patch:
            sys.stdout.write("".join(item["diff"] for item in result["items"]))
        else:
            _emit(result, compact)
    elif cmd == "apply":
        _emit(ws.apply(), compact)
    elif cmd == "discard":
        _emit(ws.discard(), compact)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
