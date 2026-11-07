"""``write()``: create / replace / append / delete cards in ``overlay/`` or ``staging/``."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from .addressing import MountCatalog, format_address, normalize_alias, normalize_path, resolve_ref
from .card import (
    LIST_FIELDS,
    ParsedCard,
    append_statements,
    compose_after,
    dump_frontmatter,
    normalize_newlines,
    parse_card,
    render_card,
    sha256_bytes,
    split_summary,
    statement_blocks,
)
from .errors import (
    AlreadyExistsError,
    FrontmatterError,
    InvalidAddressError,
    LineageCycleError,
    NotFoundError,
    PreconditionFailedError,
    ReadOnlyMountError,
)
from .fsutil import atomic_write_text, prune_empty_dirs, unlink_if_exists
from .lineage import cycle_through

if TYPE_CHECKING:  # pragma: no cover
    from .workspace import Workspace

OPS = ("create", "replace", "append", "delete")


def overlay_card_path(ws: "Workspace", card_id: str) -> str:
    """Normalize a write target to an overlay-relative path (``@overlay/`` prefix allowed)."""
    if not isinstance(card_id, str) or not card_id.strip():
        raise InvalidAddressError("write() needs a non-empty card id")
    card_id = card_id.strip()
    overlay_alias = ws.table().overlay.alias
    if card_id.startswith("@"):
        alias, _, rest = card_id.partition("/")
        if normalize_alias(alias) != overlay_alias:
            raise ReadOnlyMountError(
                f"{alias} is a read-only base slice; runtime writes go to {overlay_alias}",
                alias=alias,
            )
        card_id = rest
    return normalize_path(card_id)


def read_card_file(file) -> tuple[str | None, str | None]:
    """Return ``(text, sha256_of_raw_bytes)`` or ``(None, None)`` when the file is absent."""
    try:
        data = file.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None, None
    return data.decode("utf-8", errors="replace"), sha256_bytes(data)


def _as_list(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise FrontmatterError(f"{name} must be a list of strings")
    return [v.strip() for v in value if v.strip()]


def _body_text(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return normalize_newlines(content)
    if isinstance(content, (list, tuple)):
        return "\n".join(statement_blocks(content))
    raise TypeError("content must be a string or a list of statements")


def humanize(path: str) -> str:
    leaf = path.rsplit("/", 1)[-1]
    words = leaf.replace("_", " ").replace("-", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words) or path


def _union(existing: Iterable[str], extra: Iterable[str]) -> list[str]:
    out = list(dict.fromkeys(existing))
    for item in extra:
        if item not in out:
            out.append(item)
    return out


def build_text(
    op: str,
    path: str,
    current: str | None,
    *,
    content: Any,
    summary: str | None,
    title: str | None,
    tags: list[str] | None,
    aliases: list[str] | None,
    extends: list[str] | None,
    supersedes: list[str] | None,
) -> tuple[str | None, dict[str, Any]]:
    """Compute the new card text for ``op`` (None for delete); returns ``(text, info)``."""
    info: dict[str, Any] = {}
    lists = {"tags": tags, "aliases": aliases, "extends": extends, "supersedes": supersedes}
    if summary is not None:
        summary = " ".join(normalize_newlines(summary).split())
    if op == "create":
        fields: dict[str, Any] = {"title": title.strip() if title else humanize(path)}
        fields.update({k: v or [] for k, v in lists.items()})
        return render_card(fields, summary, _body_text(content)), info
    if op == "delete":
        return None, info
    assert current is not None
    parsed = parse_card(current)
    if op == "replace":
        given = {k: v for k, v in lists.items() if v is not None}
        new_fields: dict[str, Any] | None = None
        if title is not None or given:
            new_fields = dict(parsed.frontmatter) if not parsed.errors else {}
            if title is not None:
                new_fields["title"] = title.strip()
            elif not parsed.title:
                new_fields["title"] = parsed.display_title(path)
            new_fields.update(given)
        after = None
        body = _body_text(content)
        if summary is not None or body is not None:
            after = compose_after(parsed.summary if summary is None else summary, parsed.body if body is None else body)
        return reassemble(parsed, current, new_fields, after), info
    if op == "append":
        if content is None and not any(v for v in lists.values()) and title is None and summary is None:
            raise ValueError("append needs content (bullet statements) or list fields to merge")
        blocks = statement_blocks(content) if content is not None else []
        new_after, added = append_statements(parsed.after, blocks)
        info["added_statements"] = len(added)
        info["duplicate_statements"] = len(blocks) - len(added)
        if summary is not None:
            _, body = split_summary(new_after)
            new_after = compose_after(summary, body)
        new_fields = None
        if title is not None or any(v for v in lists.values()):
            new_fields = dict(parsed.frontmatter) if not parsed.errors else {}
            if title is not None:
                new_fields["title"] = title.strip()
            elif not parsed.title:
                new_fields["title"] = parsed.display_title(path)
            for name, extra in lists.items():
                if extra:
                    new_fields[name] = _union(parsed.list_field(name), extra)
            if new_fields == parsed.frontmatter:
                new_fields = None
        changed_after = new_after if new_after != parsed.after else None
        return reassemble(parsed, current, new_fields, changed_after), info
    raise ValueError(f"unknown op {op!r} (expected one of {', '.join(OPS)})")


def reassemble(parsed: ParsedCard, original: str, fields: dict[str, Any] | None, after: str | None) -> str:
    """Rebuild a card, keeping untouched regions (frontmatter text, body) verbatim."""
    original = normalize_newlines(original)
    if fields is None and after is None:
        return original if original.endswith("\n") or not original else original + "\n"
    new_after = (parsed.after if after is None else after).lstrip("\n")
    if fields is None and parsed.raw_frontmatter is None:
        text = new_after
    else:
        fm = parsed.raw_frontmatter if fields is None else dump_frontmatter(fields)
        text = f"+++\n{fm}+++\n" + ("\n" + new_after if new_after else "")
    return text if text.endswith("\n") or not text else text + "\n"


# ---------------------------------------------------------------------------
# Cycle checks over the prospective lineage graph
# ---------------------------------------------------------------------------


def prospective_successors(
    index, overlay_alias: str, overrides: dict[str, ParsedCard | None]
) -> tuple[dict[str, list[str]], dict[str, MountCatalog]]:
    """Lineage successor map (``extends`` + ``supersedes``) with overlay overrides applied."""
    cats = index.catalogs()
    ocat = cats.setdefault(overlay_alias, MountCatalog())
    for path, parsed in overrides.items():
        ocat.remove(path)
    for path, parsed in overrides.items():
        if parsed is not None:
            ocat.add(path, parsed.aliases)
    refs: list[tuple[str, str, str]] = []
    for row in index.lineage_edges():
        if row["src_mount"] == overlay_alias and row["src_path"] in overrides:
            continue
        refs.append((row["src_mount"], row["src_path"], row["raw"]))
    for path, parsed in overrides.items():
        if parsed is not None:
            refs += [(overlay_alias, path, raw) for raw in parsed.extends + parsed.supersedes]
    succ: dict[str, list[str]] = defaultdict(list)
    for src_mount, src_path, raw in refs:
        res = resolve_ref(raw, src_mount, cats)
        if res.resolved and res.address:
            succ[format_address(src_mount, src_path)].append(res.address)
    return succ, cats


def check_cycles(index, overlay_alias: str, overrides: dict[str, ParsedCard | None], nodes: Sequence[str]) -> None:
    succ, _ = prospective_successors(index, overlay_alias, overrides)
    for path in nodes:
        if overrides.get(path) is None:
            continue
        start = format_address(overlay_alias, path)
        cycle = cycle_through(start, lambda n: succ.get(n, ()))
        if cycle:
            raise LineageCycleError(
                f"lineage cycle via {start}: {' -> '.join(cycle)}", cycle=cycle, address=start
            )


def unresolved_lineage(parsed: ParsedCard, overlay_alias: str, cats: dict[str, MountCatalog]) -> list[str]:
    out = []
    for kind, refs in (("extends", parsed.extends), ("supersedes", parsed.supersedes)):
        for raw in refs:
            if not resolve_ref(raw, overlay_alias, cats).resolved:
                out.append(f"{kind} target {raw!r} does not resolve (yet)")
    return out


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


def write(
    ws: "Workspace",
    id: str,
    op: str = "create",
    content: Any = None,
    summary: str | None = None,
    title: str | None = None,
    tags: Sequence[str] | None = None,
    aliases: Sequence[str] | None = None,
    extends: Sequence[str] | None = None,
    supersedes: Sequence[str] | None = None,
    stage: bool = False,
    if_match: str | None = None,
) -> dict[str, Any]:
    if op not in OPS:
        raise ValueError(f"unknown op {op!r} (expected one of {', '.join(OPS)})")
    path = overlay_card_path(ws, id)
    tags_l = _as_list("tags", tags)
    aliases_l = _as_list("aliases", aliases)
    extends_l = _as_list("extends", extends)
    supersedes_l = _as_list("supersedes", supersedes)
    with ws._writing() as table:
        overlay = table.overlay
        address = format_address(overlay.alias, path)
        staging = ws.staging
        if stage:
            current, current_sha = staging.prospective_state(path, overlay.root)
        else:
            current, current_sha = read_card_file(overlay.root / f"{path}.md")
        result: dict[str, Any] = {
            "address": address,
            "id": path,
            "op": op,
            "staged": bool(stage),
            "changed": False,
            "previous_sha256": current_sha,
            "warnings": [],
        }
        if if_match is not None and if_match != current_sha:
            raise PreconditionFailedError(
                f"{address} changed since it was read (if_match={if_match[:12]}…, current="
                f"{current_sha[:12] + '…' if current_sha else 'absent'})",
                address=address,
                expected=if_match,
                current=current_sha,
            )
        if op == "create" and current is not None:
            new_text, _ = build_text(
                op, path, None, content=content, summary=summary, title=title, tags=tags_l,
                aliases=aliases_l, extends=extends_l, supersedes=supersedes_l,
            )
            if new_text == normalize_newlines(current):
                result["sha256"] = current_sha
                return result  # idempotent retry
            raise AlreadyExistsError(f"{address} already exists with different content", address=address, sha256=current_sha)
        if op in ("replace", "append") and current is None:
            raise NotFoundError(f"{address} does not exist{' in staging or overlay' if stage else ''}", address=address)
        if op == "delete" and current is None:
            result["sha256"] = None
            result["warnings"].append(f"{address} does not exist; nothing to delete")
            if stage:
                staging.stage_delete(path, overlay.root)  # clears stale entries, if any
            return result

        new_text, info = build_text(
            op, path, current, content=content, summary=summary, title=title, tags=tags_l,
            aliases=aliases_l, extends=extends_l, supersedes=supersedes_l,
        )
        result.update(info)
        parsed_new: ParsedCard | None = None
        if new_text is not None:
            parsed_new = parse_card(new_text)
            if parsed_new.errors:
                raise FrontmatterError("; ".join(parsed_new.errors), address=address)
            overrides: dict[str, ParsedCard | None] = {}
            if stage:
                overrides.update(staging.prospective_overrides(overlay.root))
            overrides[path] = parsed_new
            check_cycles(ws.index, overlay.alias, overrides, [path])
            _, cats = prospective_successors(ws.index, overlay.alias, overrides)
            result["warnings"] += unresolved_lineage(parsed_new, overlay.alias, cats)

        if new_text is not None and current is not None and new_text == normalize_newlines(current):
            result["sha256"] = current_sha
            return result

        if stage:
            if new_text is None:
                staging.stage_delete(path, overlay.root)
            else:
                staging.stage_write(path, new_text, overlay.root, op)
        else:
            file = overlay.root / f"{path}.md"
            if new_text is None:
                unlink_if_exists(file)
                prune_empty_dirs(overlay.root, file.parent)
            else:
                atomic_write_text(file, new_text)
            ws._sync(table)
        result["changed"] = True
        result["sha256"] = sha256_bytes(new_text.encode("utf-8")) if new_text is not None else None
        return result


__all__ = ["write", "build_text", "reassemble", "check_cycles", "prospective_successors", "OPS", "LIST_FIELDS"]
