"""``mindslice`` command-line interface (memory primitives plus ``status``, ``boot``, ``init`` and ``mcp``)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .. import __version__
from ..model.addressing import normalize_alias
from ..operations.boot import render_markdown as render_boot
from .cli_addressing import reference as cli_reference
from ..errors import ApplyConflictError, MindSliceError
from ..operations.status import render_status
from ..workspace import Workspace
from . import render


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


def _output(args: argparse.Namespace, data: Any, renderer: render.Renderer) -> None:
    """Human-readable by default; the result dict as JSON with ``--json`` (or ``--compact``)."""
    if args.json:
        _emit(data, args.compact)
        return
    text = renderer(data)
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _error(args: argparse.Namespace, error: dict[str, Any]) -> None:
    """Errors go to stderr in both modes, with the same stable ``code``."""
    if args.json:
        sys.stderr.write(json.dumps(error, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(render.render_error(error))


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


def build_parser() -> argparse.ArgumentParser:
    # Global options are accepted before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-w", "--workspace", default=argparse.SUPPRESS,
                        help="workspace root (default: $MINDSLICE_WORKSPACE or nearest dir with mounts.toml)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="structured JSON output instead of human-readable text (errors too, on stderr)")
    common.add_argument("--compact", action="store_true", default=argparse.SUPPRESS,
                        help="single-line JSON output (implies --json)")
    p = argparse.ArgumentParser(prog="mindslice", parents=[common],
                                description="Layered, human-readable long-term memory for LLM agents.")
    p.add_argument("--version", action="version", version=f"mindslice {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    _add_parser = sub.add_parser
    sub.add_parser = lambda *a, **kw: _add_parser(*a, parents=[common], **kw)  # type: ignore[method-assign]

    s = sub.add_parser("init", help="create a workspace (mounts.toml, overlay/, staging/, slices/, .cache/)")
    s.add_argument("path", nargs="?", default=".")

    s = sub.add_parser("doctor", help="check local workspace, startup payload and MCP; guide client verification")

    s = sub.add_parser("status", help="show mounts, pending review and unbaked overlay changes")

    s = sub.add_parser("history", help="inspect recorded reasons and lifecycle events (not old content snapshots)")
    s.add_argument("address", nargs="?", help="card address; omit for workspace history, including version switches")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)

    s = sub.add_parser("explain", help="explain the sources, precedence and lineage of a read result")
    s.add_argument("address")
    s.add_argument("--follow", help="all | none | comma-separated roles/@aliases")
    s.add_argument("--max-extensions", type=int, default=5)
    s.add_argument("--extensions-offset", type=int, default=0)

    s = sub.add_parser("rollback", help="preview and switch a mounted slice to an earlier directory; overlay stays")
    s.add_argument("alias", type=normalize_alias)
    s.add_argument("--to", dest="target", help="physical slice directory (default: recorded predecessor)")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--yes", action="store_true", help="execute after reviewing the preview")

    s = sub.add_parser("backup", help="create a verified portable directory snapshot, including external mounts")
    s.add_argument("output", help="new backup directory outside the workspace and mounted sources")

    s = sub.add_parser("restore", help="verify a backup and restore into a new workspace directory")
    s.add_argument("source", help="backup directory")
    s.add_argument("--output", required=True, help="new workspace directory; never overwrites an existing directory")

    s = sub.add_parser("manifest", help="paginated mount and folder map for memory navigation")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--max-folders", type=int, default=10, dest="max_folders_per_mount")
    s.add_argument("--include-overview", action="store_true")
    s.add_argument("--no-always", action="store_false", dest="include_always", help="omit the always-loaded cards")

    s = sub.add_parser("boot", help="emit the session startup payload (instructions, standing cards and onboarding)")
    s.add_argument("--cards-only", action="store_true", help="only standing card content, without startup instructions")

    s = sub.add_parser("search", help="associative BM25 search returning card previews")
    s.add_argument("query")
    s.add_argument("--source", action="append", type=normalize_alias, help="restrict to mount alias; @ optional (repeatable)")
    s.add_argument("--tag", action="append", dest="tags", help="require tag (repeatable, all must match)")
    s.add_argument("-k", type=int, default=10)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--max-neighbors", type=int, default=3)
    s.add_argument("--follow", help="follow_supersedes: all (default) | none | comma-separated roles/@aliases")

    s = sub.add_parser("read", help="exact resolution of an address (with lineage composition)")
    s.add_argument("address", help="@alias/path, unambiguous alias/path, or relative card path (./path forces relative)")
    s.add_argument("--follow", help="follow_supersedes: all (default) | none | comma-separated roles/@aliases")
    s.add_argument("--max-backlinks", type=int, default=10)
    s.add_argument("--backlinks-offset", type=int, default=0)
    s.add_argument("--max-extensions", type=int, default=5)
    s.add_argument("--extensions-offset", type=int, default=0)
    s.add_argument("--markdown", action="store_true", help=argparse.SUPPRESS)  # deprecated: now the default

    s = sub.add_parser("write", help="create/replace/append/delete a card in overlay/ (or staging/)")
    s.add_argument("id", help="overlay-relative card id, e.g. api/auth-edge-cases")
    s.add_argument("--op", choices=("create", "replace", "append", "delete"), default="create")
    s.add_argument("--content", help="body text (append: bullet statements)")
    s.add_argument("--content-file", help="read content from file ('-' = stdin)")
    s.add_argument("--summary")
    s.add_argument("--reason", help="why this change is needed; stored in engine history, not in the card")
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
    s.add_argument("--alias", type=normalize_alias, help="mount alias, with or without @")
    s.add_argument("--precedence", type=int, default=50)
    s.add_argument("--role", default="baseline")
    s.add_argument("--keep-overlay", action="store_true",
                   help="keep @overlay copies of this slice's cards (by default, unchanged exported copies are retired)")

    s = sub.add_parser("unmount", help="remove a mount")
    s.add_argument("alias", type=normalize_alias, help="mount alias, with or without @")

    s = sub.add_parser("validate", help="lint the workspace or a slice directory")
    s.add_argument("slice_path", nargs="?")
    s.add_argument("--rebuild-index", action="store_true", help="rebuild .cache/index.sqlite with full sha256 verification")

    s = sub.add_parser("bake", help="review and bake the workspace, or create/update one named slice")
    s.add_argument("alias", nargs="?", type=normalize_alias, help="optional target alias; omit for workspace review")
    s.add_argument("--assign", action="append", help="batch destination: CARD_OR_FOLDER=ALIAS (repeatable)")
    s.add_argument("--defer", action="append", help="batch cards to leave in overlay: ID, folder/ or *")
    s.add_argument("--plan", help="reviewed JSON plan from bake --dry-run --json")
    s.add_argument("--fresh", action="store_true", help="ignore saved batch destination choices")
    s.add_argument("--yes", action="store_true", help="execute a resolved batch plan without interactive confirmation")
    s.add_argument("--output", help="slice directory or .zip/.tar.gz archive (default directory: "
                   "slices/<name>.slice, or <name>-2.slice ...); the old folder is left as it was")
    s.add_argument("--prefix", help="select overlay cards under this path; required for a new named target "
                   "(default for an existing alias: cards that extend, supersede or share a path with its cards)")
    s.add_argument("--tag", action="append", dest="tags", help="bake the overlay cards with this tag (repeatable)")
    s.add_argument("--include-deps", action="store_true", help="also bake overlay cards the selection references")
    s.add_argument("--dry-run", action="store_true", help="show what would move, write nothing")
    s.add_argument("--name", help="slice name")
    s.add_argument("--description", help="slice description")
    s.add_argument("--slice-version", help="version (default: 0.1.0 for a new slice, patch bump for an update)")

    s = sub.add_parser("diff", help="show staged changes (or overlay overrides)")
    s.add_argument("--scope", choices=("staging", "overlay"), default="staging")

    for command, description in (
        ("apply", "accept selected staging cards (default: all), saved and active immediately"),
        ("discard", "reject selected staging cards (default: all), keeping live memory unchanged"),
        ("review", "interactively accept, reject or leave staged cards pending"),
    ):
        s = sub.add_parser(command, help=description)
        s.add_argument("ids", nargs="*", help="exact pending card IDs or @overlay/path; omit for all")

    s = sub.add_parser("mcp", help="serve the 4-tool MCP server (manifest/search/read/write) over stdio")
    s.add_argument("--stage-writes", action="store_true", help="force every agent write into staging/")
    return p


def _open(args: argparse.Namespace) -> Workspace:
    root = args.workspace or os.environ.get("MINDSLICE_WORKSPACE")
    return Workspace(root) if root else Workspace.discover()


def main(argv: Sequence[str] | None = None) -> int:
    from .mcp_server import ensure_utf8_stdio

    ensure_utf8_stdio()  # output is UTF-8 (CJK-safe) regardless of the console locale
    args = build_parser().parse_args(argv)
    args.workspace = getattr(args, "workspace", None)
    args.compact = getattr(args, "compact", False)
    args.json = getattr(args, "json", False) or args.compact
    try:
        if args.command == "init":
            target = Path(args.workspace or args.path)
            with Workspace.init(target) as ws:
                _output(args, {"workspace": str(ws.root), "mounts": str(ws.root / "mounts.toml")}, render.render_init)
            return 0
        if args.command == "restore":
            _output(args, Workspace.restore(args.source, args.output), _render_restore)
            return 0
        if args.command == "doctor":
            from .doctor import diagnose, render as render_doctor

            result = diagnose(args.workspace or os.environ.get("MINDSLICE_WORKSPACE"))
            _output(args, result, render_doctor)
            return 0 if result["ok"] else 1
        if args.command == "mcp":
            from .mcp_server import serve

            with _open(args) as ws:
                serve(ws, stage_writes=args.stage_writes)
            return 0
        with _open(args) as ws:
            return _dispatch(ws, args)
    except ApplyConflictError as exc:
        _error(args, exc.to_dict())
        return 2
    except MindSliceError as exc:
        _error(args, exc.to_dict())
        return 1
    except (ValueError, TypeError, OSError) as exc:
        _error(args, {"error": type(exc).__name__, "message": str(exc)})
        return 1


def _render_restore(result: dict[str, Any]) -> str:
    lines = [f"Restored workspace: {result['workspace']}", result["note"]]
    lines += [f"Historical version unavailable in backup: {path}" for path in result["unavailable_versions"]]
    return "\n".join(lines) + "\n"


def _render_backup(result: dict[str, Any]) -> str:
    lines = [f"Backup: {result['path']} ({result['files']} files)", result["note"]]
    lines += [f"Historical version already missing: {path}" for path in result["unavailable_versions"]]
    return "\n".join(lines) + "\n"


def _dispatch(ws: Workspace, args: argparse.Namespace) -> int:
    cmd = args.command

    def out(data: Any, renderer: render.Renderer) -> None:
        _output(args, data, renderer)

    if cmd == "status":
        out(ws.status(), render_status)
    elif cmd in ("history", "explain"):
        from ..operations.audit import render_history, render_explain
        with ws._reading():
            address = cli_reference(ws, args.address) if args.address else None
            result = (ws.card_history(address, args.limit, args.offset) if cmd == "history" else
                      ws.explain(address, _follow(args.follow), args.max_extensions, args.extensions_offset))
        out(result, render_history if cmd == "history" else render_explain)
    elif cmd == "backup":
        out(ws.backup(args.output), _render_backup)
    elif cmd == "rollback":
        from ..operations.recovery import render_rollback
        from ..errors import RecoveryError
        plan = ws.rollback(args.alias, args.target, dry_run=True)
        if args.dry_run:
            out(plan, render_rollback)
            return 0 if plan["ready"] else 1
        if not plan["ready"]:
            raise RecoveryError("rollback is blocked; inspect rollback --dry-run", plan=plan)
        if not args.yes:
            if args.json or not sys.stdin.isatty():
                raise RecoveryError("review rollback --dry-run, then use --yes to execute", plan=plan)
            sys.stderr.write(render_rollback(plan) + "Switch this slice pointer? [yes/No]: ")
            sys.stderr.flush()
            try:
                answer = sys.stdin.readline().strip().lower()
            except KeyboardInterrupt:
                answer = ""
            if answer not in ("yes", "y"):
                out({"cancelled": True}, render.render_cancelled)
                return 0
        result = ws.rollback(args.alias, plan["path"], revision=plan["revision"])
        out(result, lambda r: "Slice pointer switched.\n" + render_rollback(r))
    elif cmd == "manifest":
        out(ws.manifest(args.limit, args.offset, args.max_folders_per_mount, args.include_overview,
                        args.include_always), render.render_manifest)
    elif cmd == "boot":
        from .mcp_server import format_instructions

        result = ws.boot()
        if args.json:
            if args.cards_only:
                _emit({"cards": result["cards"], "total": result["total"]}, args.compact)
            else:
                _emit(dict(result, instructions=format_instructions(result)), args.compact)
        else:
            text = render_boot(result["cards"], header="") if args.cards_only else format_instructions(result)
            if text:
                sys.stdout.write(text if text.endswith("\n") else text + "\n")
        for item in result.get("pending_approval", []):
            sys.stderr.write(f"awaiting approval: {ws.table().overlay.alias}/{item['id']} ({item['reason']}); "
                             "review with `mindslice diff`, approve with `mindslice apply`\n")
    elif cmd == "search":
        out(ws.search(args.query, args.source, args.tags, args.k, args.offset, args.max_neighbors, _follow(args.follow)),
            render.render_search)
    elif cmd == "read":
        with ws._reading():
            address = cli_reference(ws, args.address)
            result = ws.read(address, _follow(args.follow), args.max_backlinks, args.backlinks_offset,
                             args.max_extensions, args.extensions_offset)
        out(result, render.render_read)
    elif cmd == "write":
        content = _content(args)
        with ws._writing() as table:
            extends = [cli_reference(ws, ref, source=table.overlay.alias) for ref in args.extends] if args.extends else None
            supersedes = [cli_reference(ws, ref, source=table.overlay.alias) for ref in args.supersedes] if args.supersedes else None
            result = ws.write(args.id, args.op, content, args.summary, args.title, args.tags, args.aliases,
                              extends, supersedes, args.stage, args.if_match, args.load, args.reason)
        out(result, render.render_write)
    elif cmd == "mount":
        out(ws.mount(_cwd_path(args.path), args.alias, args.precedence, args.role,
                     retire_overlay=not args.keep_overlay), render.render_mount)
    elif cmd == "unmount":
        out(ws.unmount(args.alias), render.render_unmount)
    elif cmd == "validate":
        result = ws.validate(_cwd_path(args.slice_path) if args.slice_path else None, args.rebuild_index)
        out(result, render.render_validate)
        return 0 if result["ok"] else 1
    elif cmd == "bake":
        if args.alias is None:
            from .bake_review import run
            return run(ws, args, out)
        if args.assign or args.defer or args.plan or args.fresh:
            from ..errors import InvalidArgumentsError
            raise InvalidArgumentsError("batch review options cannot be combined with a target alias")
        out(ws.bake(args.alias, _cwd_path(args.output) if args.output else None, args.prefix, args.tags,
                    args.include_deps, args.dry_run, name=args.name, description=args.description,
                    version=args.slice_version), render.render_bake)
    elif cmd == "diff":
        result = ws.diff(args.scope)
        if args.json:
            _emit(result, args.compact)
        else:
            sys.stdout.write("".join(item["diff"] for item in result["items"]))
            for item in result["items"]:
                for change in item.get("changes", []):
                    if change.get("reason"):
                        sys.stderr.write(f"reason: {item['address']} ({change['op']}): {change['reason']}\n")
                if item.get("conflict"):
                    sys.stderr.write(f"conflict: {item['address']}: {item['conflict']}\n")
    elif cmd == "apply":
        out(ws.apply(args.ids or None), render.render_apply)
    elif cmd == "discard":
        out(ws.discard(args.ids or None), render.render_discard)
    elif cmd == "review":
        from .staging_review import run
        out(run(ws, args.ids or None), render.render_review)
    else:  # pragma: no cover - argparse guards this
        raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
