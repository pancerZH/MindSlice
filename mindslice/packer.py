"""``pack()``: deterministic export of overlay cards into a standalone ``.slice``.

Every reference (``extends``, ``supersedes``, ``[[wikilinks]]``) is first
resolved against ``@overlay`` (source-first), then classified:

* included ``@overlay`` target -> written slice-relative (``<path>``)
* external slice target        -> kept qualified (``@alias/<path>``) and listed
                                   under ``dependencies`` in ``slice.toml``
* excluded ``@overlay`` target -> ``UnresolvedExportDependencyError`` unless
                                   ``include_deps=True`` pulls it in transitively
"""

from __future__ import annotations

import gzip
import io
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .addressing import format_address, normalize_alias, resolve_ref, rewrite_wikilinks
from .card import ParsedCard, parse_card, truncate
from .config import DESCRIPTION_CHARS, OVERVIEW_PATH, SLICE_FILE, SliceManifest, dump_slice_manifest
from .errors import AlreadyExistsError, InvalidAddressError, NotFoundError, UnresolvedExportDependencyError
from .fsutil import fsync_dir, iter_markdown
from .lexical import fold
from .validation import validate_slice_dir
from .writer import read_card_file, reassemble

if TYPE_CHECKING:  # pragma: no cover
    from .workspace import Workspace

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _format_of(output: Path) -> str:
    name = output.name.lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return "tar.gz"
    return "directory"


def _slice_dir_name(output: Path, fmt: str) -> str:
    name = output.name
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if fmt != "directory" and name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name if name.endswith(".slice") else name + ".slice"


def _safe_alias(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-.") or "slice"
    if not cleaned[0].isalnum():
        cleaned = "s" + cleaned
    return normalize_alias(cleaned)


def pack(
    ws: "Workspace",
    output_path: str | Path,
    prefix: str | None = None,
    tags: str | Sequence[str] | None = None,
    include_deps: bool = False,
    *,
    name: str | None = None,
    description: str | None = None,
    version: str = "0.1.0",
    alias: str | None = None,
) -> dict[str, Any]:
    output = Path(output_path).expanduser().absolute()
    fmt = _format_of(output)
    dir_name = _slice_dir_name(output, fmt)
    tag_set = {fold(t) for t in ([tags] if isinstance(tags, str) else (tags or [])) if fold(t)}
    if prefix is not None:
        prefix = prefix.strip().lstrip("./").lstrip("/")

    with ws._reading() as table:
        overlay = table.overlay
        cats = ws.index.catalogs()
        nested = tuple(o.root for o in table.all() if o.alias != overlay.alias and overlay.root in o.root.parents)
        cards: dict[str, tuple[str, ParsedCard]] = {}
        for rel, _ in iter_markdown(overlay.root, exclude=tuple(ws._exclude()) + nested):
            text, _ = read_card_file(overlay.root / f"{rel}.md")
            if text is not None:
                cards[rel] = (text, parse_card(text))

    def selected_by_filter(path: str, parsed: ParsedCard) -> bool:
        if path == OVERVIEW_PATH and (prefix or tag_set):
            return False
        if prefix and not path.startswith(prefix):
            return False
        return tag_set <= {fold(t) for t in parsed.tags}

    selected = sorted(p for p, (_, parsed) in cards.items() if selected_by_filter(p, parsed))
    if not selected:
        raise NotFoundError(f"no {overlay.alias} cards match prefix={prefix!r} tags={sorted(tag_set)}")

    included = set(selected)
    pulled: list[str] = []
    missing: list[dict[str, str]] = []
    warnings: list[str] = []
    external: set[str] = set()
    queue = list(selected)
    while queue:
        path = queue.pop(0)
        parsed = cards[path][1]
        refs = [(k, r) for k in ("extends", "supersedes") for r in parsed.list_field(k)]
        refs += [("wikilink", r) for r in parsed.wikilink_targets()]
        for kind, raw in refs:
            res = resolve_ref(raw, overlay.alias, cats)
            if res.mount is None:
                warnings.append(f"{path}: {kind} reference {raw!r} is not a valid address; copied verbatim")
                continue
            if res.mount != overlay.alias:
                external.add(res.mount)
                if not res.resolved:
                    warnings.append(f"{path}: {kind} reference {raw!r} does not resolve in {res.mount}")
                continue
            if not res.resolved or res.path not in cards:
                warnings.append(f"{path}: {kind} reference {raw!r} does not resolve in {overlay.alias}; copied verbatim")
                continue
            if res.path in included:
                continue
            if include_deps:
                included.add(res.path)
                pulled.append(res.path)
                queue.append(res.path)
            else:
                missing.append({"source": format_address(overlay.alias, path), "field": kind, "ref": raw,
                                "target": format_address(overlay.alias, res.path)})
    if missing:
        targets = sorted({m["target"] for m in missing})
        raise UnresolvedExportDependencyError(
            f"export references {len(targets)} excluded {overlay.alias} card(s): {', '.join(targets)} "
            "(pass include_deps=True to pull them in)",
            missing=missing,
        )

    def rewrite(raw: str) -> str:
        res = resolve_ref(raw, overlay.alias, cats)
        if res.mount == overlay.alias:
            if raw.strip().startswith("@") and res.path:
                return res.path  # @overlay/x -> slice-relative x
            return raw  # slice-relative refs keep resolving inside the exported slice
        if res.mount and res.resolved and res.path:
            return format_address(res.mount, res.path)  # canonical qualified external ref
        return raw

    files: dict[str, str] = {}
    for path in sorted(included):
        text, parsed = cards[path]
        new_ext = [rewrite(r) for r in parsed.extends]
        new_sup = [rewrite(r) for r in parsed.supersedes]
        fields = None
        if new_ext != parsed.extends or new_sup != parsed.supersedes:
            fields = dict(parsed.frontmatter)
            fields["extends"], fields["supersedes"] = new_ext, new_sup
        link_map = {t: rewrite(t) for t in parsed.wikilink_targets()}
        link_map = {k: v for k, v in link_map.items() if k != v}
        new_after = rewrite_wikilinks(parsed.after, link_map) if link_map else None
        files[f"{path}.md"] = reassemble(parsed, text, fields, new_after)

    slice_name = name or dir_name.removesuffix(".slice")
    try:
        slice_alias = normalize_alias(alias) if alias else _safe_alias(slice_name)
    except InvalidAddressError:
        slice_alias = _safe_alias(slice_name)
    if description is None:
        scope = []
        if prefix:
            scope.append(f"prefix={prefix}")
        if tag_set:
            scope.append("tags=" + ",".join(sorted(tag_set)))
        description = f"Exported from {overlay.alias}" + (f" ({'; '.join(scope)})" if scope else "")
    description, _ = truncate(" ".join(description.split()), DESCRIPTION_CHARS)
    sm = SliceManifest(name=slice_name, version=version, description=description, alias=slice_alias,
                       dependencies=sorted(external))
    files[SLICE_FILE] = dump_slice_manifest(sm)

    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "directory":
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise AlreadyExistsError(f"{output} already exists and is not empty", path=str(output))
    elif output.exists():
        raise AlreadyExistsError(f"{output} already exists", path=str(output))

    tmp_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        tree = tmp_root / dir_name
        for rel, text in files.items():
            dest = tree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text.encode("utf-8"))
        validation = validate_slice_dir(tree, ws)
        if fmt == "directory":
            if output.exists():
                output.rmdir()
            os.replace(tree, output)
            fsync_dir(output.parent)
        else:
            archive = tmp_root / "archive.tmp"
            if fmt == "zip":
                _write_zip(archive, dir_name, files)
            else:
                _write_tar_gz(archive, dir_name, files)
            os.replace(archive, output)
            fsync_dir(output.parent)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "output": str(output),
        "format": fmt,
        "name": slice_name,
        "alias": slice_alias,
        "cards": sorted(p[:-3] for p in files if p.endswith(".md")),
        "included_dependencies": pulled,
        "dependencies": sorted(external),
        "warnings": warnings,
        "validation": {
            "ok": validation["ok"],
            "errors": validation["errors"],
            "warnings": len(validation["warnings"]),
        },
    }


def _entries(root_name: str, files: dict[str, str]) -> list[tuple[str, bytes | None]]:
    dirs = {root_name}
    for rel in files:
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add(root_name + "/" + "/".join(parts[:i]))
    entries: list[tuple[str, bytes | None]] = [(d, None) for d in dirs]
    entries += [(f"{root_name}/{rel}", text.encode("utf-8")) for rel, text in files.items()]
    return sorted(entries, key=lambda e: e[0])


def _write_zip(dest: Path, root_name: str, files: dict[str, str]) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in _entries(root_name, files):
            if data is None:
                info = zipfile.ZipInfo(name + "/", date_time=_ZIP_EPOCH)
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zf.writestr(info, data)


def _write_tar_gz(dest: Path, root_name: str, files: dict[str, str]) -> None:
    with open(dest, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, data in _entries(root_name, files):
                info = tarfile.TarInfo(name)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                if data is None:
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    tar.addfile(info)
                else:
                    info.size = len(data)
                    info.mode = 0o644
                    tar.addfile(info, io.BytesIO(data))
