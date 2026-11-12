"""Source fingerprints for the complete engine package, independent of its install path."""

from __future__ import annotations

import hashlib
from pathlib import Path


def engine_digest(package: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(package.rglob("*.py")):
        digest.update(file.relative_to(package).as_posix().encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()
