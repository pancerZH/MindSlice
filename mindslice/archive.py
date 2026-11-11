"""Deterministic archives of a baked slice directory."""

from __future__ import annotations

import gzip
import io
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .fsutil import fsync_dir


def archive_format(output: Path) -> str:
    name = output.name.lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    return "directory"


def write_archive(tree: Path, output: Path, fmt: str) -> None:
    """Write all files, with fixed archive metadata, then atomically publish the archive."""
    name = output.name
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]
            break
    root = name if name.endswith(".slice") else name + ".slice"
    entries = [(root, None)]
    entries += [(root + "/" + p.relative_to(tree).as_posix(), None if p.is_dir() else p.read_bytes())
                for p in sorted(tree.rglob("*"))]
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    try:
        if fmt == "zip":
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, data in entries:
                    info = zipfile.ZipInfo(path + "/" if data is None else path, date_time=(1980, 1, 1, 0, 0, 0))
                    info.external_attr = ((0o40755 << 16) | 0x10) if data is None else 0o100644 << 16
                    if data is not None:
                        info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, b"" if data is None else data)
        else:
            with open(temporary, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for path, data in entries:
                        info = tarfile.TarInfo(path)
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mode = 0o755 if data is None else 0o644
                        if data is None:
                            info.type = tarfile.DIRTYPE
                            archive.addfile(info)
                        else:
                            info.size = len(data)
                            archive.addfile(info, io.BytesIO(data))
        os.replace(temporary, output)
        fsync_dir(output.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)
