"""``validate()``: lint slices straight from disk (the index is never trusted here)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .addressing import MountCatalog, format_address, normalize_alias, resolve_ref
from .card import MAX_CARD_LINES, SUMMARY_PREVIEW_CHARS, ParsedCard, parse_card
from .config import DESCRIPTION_CHARS, OVERVIEW_PATH, SliceManifest, load_slice_manifest
from .errors import InvalidAddressError
from .fsutil import iter_markdown
from .lineage import strongly_connected_cycles
from .writer import read_card_file

if TYPE_CHECKING:  # pragma: no cover
    from .workspace import Workspace


@dataclass
class SliceSource:
    alias: str
    root: Path
    manifest: SliceManifest
    kind: str  # overlay | slice | standalone
    exclude: tuple[Path, ...] = ()


class Report:
    def __init__(self, target: str) -> None:
        self.target = target
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.cards = 0
        self.slices = 0

    def add(self, severity: str, code: str, message: str, address: str | None = None, file: str | None = None) -> None:
        issue: dict[str, Any] = {"severity": severity, "code": code, "message": message}
        if address:
            issue["address"] = address
        if file:
            issue["file"] = file
        (self.errors if severity == "error" else self.warnings).append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": not self.errors,
            "target": self.target,
            "errors": self.errors,
            "warnings": self.warnings,
            "stats": {"slices": self.slices, "cards": self.cards, "errors": len(self.errors), "warnings": len(self.warnings)},
        }


def _deps(manifest: SliceManifest) -> set[str]:
    out = set()
    for dep in manifest.dependencies:
        try:
            out.add(normalize_alias(dep))
        except InvalidAddressError:
            pass
    return out


def lint(
    sources: list[SliceSource],
    report: Report,
    external: dict[str, MountCatalog] | None = None,
    standalone: bool = False,
) -> None:
    cats: dict[str, MountCatalog] = dict(external or {})
    cards: dict[tuple[str, str], tuple[ParsedCard, int, Path]] = {}
    for src in sources:
        report.slices += 1
        cat = cats[src.alias] = MountCatalog()
        for rel, _ in sorted(iter_markdown(src.root, exclude=src.exclude)):
            file = src.root / f"{rel}.md"
            text, _ = read_card_file(file)
            if text is None:
                continue
            parsed = parse_card(text)
            lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
            cards[(src.alias, rel)] = (parsed, lines, file)
            cat.add(rel, parsed.aliases)
    by_alias = {s.alias: s for s in sources}
    succ: dict[str, list[str]] = defaultdict(list)

    for src in sources:
        sm = src.manifest
        if sm.errors:
            for err in sm.errors:
                report.add("error", "invalid_slice_manifest", err, file=str(src.root / "slice.toml"))
        if len(sm.description) > DESCRIPTION_CHARS:
            report.add("warning", "long_description", f"slice.toml description exceeds {DESCRIPTION_CHARS} chars",
                       file=str(src.root / "slice.toml"))
        if not standalone:
            for dep in sm.dependencies:
                try:
                    dep_alias = normalize_alias(dep)
                except InvalidAddressError:
                    report.add("error", "invalid_dependency", f"invalid dependency alias {dep!r}", address=src.alias)
                    continue
                if dep_alias not in cats:
                    report.add("warning", "missing_dependency", f"{src.alias} depends on {dep_alias}, which is not mounted",
                               address=src.alias)

    aliases_seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (mount, path), (parsed, lines, file) in sorted(cards.items()):
        report.cards += 1
        address = format_address(mount, path)
        fname = str(file)
        is_overview = path == OVERVIEW_PATH
        for err in parsed.errors:
            report.add("error", "invalid_frontmatter", err, address, fname)
        for warn in parsed.warnings:
            report.add("warning", "frontmatter_schema", warn, address, fname)
        if not is_overview:
            if not parsed.has_frontmatter:
                report.add("warning", "missing_frontmatter", "card has no +++ TOML frontmatter", address, fname)
            elif not parsed.title.strip():
                report.add("warning", "missing_title", "frontmatter has no title", address, fname)
            if not parsed.summary:
                report.add("warning", "missing_summary", "no summary paragraph directly below the frontmatter", address, fname)
            elif len(" ".join(parsed.summary.split())) > SUMMARY_PREVIEW_CHARS:
                report.add("warning", "long_summary", f"summary exceeds {SUMMARY_PREVIEW_CHARS} chars", address, fname)
        if lines > MAX_CARD_LINES:
            report.add("warning", "card_too_long", f"card has {lines} lines (> {MAX_CARD_LINES}); consider splitting", address, fname)
        for a in parsed.aliases:
            aliases_seen[(mount, a.strip().lower())].append(path)

        src = by_alias[mount]
        refs = [(k, r) for k in ("extends", "supersedes") for r in parsed.list_field(k)]
        refs += [("wikilink", r) for r in parsed.wikilink_targets()]
        for kind, raw in refs:
            res = resolve_ref(raw, mount, cats)
            if res.resolved:
                if standalone and res.mount != mount and res.mount not in _deps(src.manifest):
                    report.add("warning", "undeclared_dependency",
                               f"{kind} reference {raw!r} targets {res.mount}, which is not declared in slice.toml dependencies",
                               address, fname)
                if res.address == address:
                    if kind != "wikilink":
                        report.add("error", "self_reference", f"{kind} points at the card itself", address, fname)
                elif kind != "wikilink":
                    succ[address].append(res.address)
                continue
            lineage = kind != "wikilink"
            if res.mount is None:
                report.add("error", "invalid_reference", f"{kind} reference {raw!r} is not a valid address", address, fname)
            elif raw.strip().startswith("@") and res.mount not in cats:
                if standalone and res.mount in _deps(src.manifest):
                    continue  # declared external dependency; target cannot be checked here
                code = "undeclared_dependency" if standalone else "unmounted_dependency"
                report.add("warning", code, f"{kind} reference {raw!r} targets {res.mount}, which is "
                           + ("not declared in slice.toml dependencies" if standalone else "not mounted"), address, fname)
            elif lineage:
                report.add("error", "broken_lineage", f"{kind} target {raw!r} does not exist", address, fname)
            else:
                report.add("warning", "broken_wikilink", f"[[{raw}]] does not resolve", address, fname)

    for (mount, alias), paths in sorted(aliases_seen.items()):
        if len(set(paths)) > 1:
            report.add("warning", "duplicate_alias", f"alias {alias!r} is used by {', '.join(sorted(set(paths)))}",
                       address=mount)
    nodes = sorted(set(succ) | {t for ts in succ.values() for t in ts})
    for comp in strongly_connected_cycles(nodes, lambda n: succ.get(n, ())):
        report.add("error", "lineage_cycle", "circular extends/supersedes chain: " + " -> ".join(comp + comp[:1]),
                   address=comp[0])


def validate(ws: "Workspace | None", slice_path: str | Path | None = None, rebuild_index: bool = False) -> dict[str, Any]:
    rebuilt = None
    if rebuild_index:
        if ws is None:
            raise ValueError("rebuild_index requires a workspace")
        with ws._writing(sync=False) as table:
            rebuilt = ws.index.rebuild(table, ws._exclude()).to_dict()
    if slice_path is None:
        if ws is None:
            raise ValueError("validate() needs a workspace or a slice_path")
        out = _validate_workspace(ws)
    else:
        out = validate_slice_dir(Path(slice_path), ws)
    out["rebuilt_index"] = rebuilt
    return out


def _validate_workspace(ws: "Workspace") -> dict[str, Any]:
    with ws._reading() as table:
        report = Report(str(ws.root))
        sources = []
        exclude = tuple(ws._exclude())
        for m in table.all():
            nested = tuple(o.root for o in table.all() if o.alias != m.alias and m.root in o.root.parents)
            if not m.root.is_dir():
                report.add("error", "missing_mount", f"mount path {m.path} does not exist", address=m.alias)
                continue
            sources.append(SliceSource(m.alias, m.root, load_slice_manifest(m.root), m.kind, exclude + nested))
        lint(sources, report)
        # Staged files must be valid cards; conflicts are reported (apply would abort on them).
        from .staging import precondition_conflict  # local import: staging imports writer

        overlay = table.overlay
        for path, entry in ws.staging.entries().items():
            address = format_address(overlay.alias, path)
            _, current = read_card_file(overlay.root / f"{path}.md")
            conflict = precondition_conflict(entry.get("base_sha256"), current)
            if conflict:
                report.add("warning", "staging_conflict", f"staged change would not apply: {conflict}", address)
            if entry.get("op") != "delete":
                text, _ = read_card_file(ws.staging.file(path))
                if text is None:
                    report.add("error", "staged_file_missing", "manifest entry has no staged file", address)
                    continue
                for err in parse_card(text).errors:
                    report.add("error", "invalid_staged_card", err, address, str(ws.staging.file(path)))
        return report.to_dict()


def validate_slice_dir(root: Path, ws: "Workspace | None" = None) -> dict[str, Any]:
    """Validate a standalone ``.slice`` directory (mounted or not)."""
    root = Path(root).resolve()
    report = Report(str(root))
    if not root.is_dir():
        report.add("error", "missing_slice", f"{root} is not a directory")
        return report.to_dict()
    sm = load_slice_manifest(root)
    alias_name = sm.alias or root.name.removesuffix(".slice")
    try:
        alias = normalize_alias(alias_name)
    except InvalidAddressError:
        alias = "@self"
    external: dict[str, MountCatalog] = {}
    if ws is not None:
        with ws._reading():
            external = {a: c for a, c in ws.index.catalogs().items() if a != alias}
            for row in ws.index.mount_rows():
                if Path(row["root"]) == root:
                    external.pop(row["alias"], None)
    lint([SliceSource(alias, root, sm, "standalone")], report, external=external, standalone=True)
    return report.to_dict()
