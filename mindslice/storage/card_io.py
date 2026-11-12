"""Read card text and raw-byte revisions from disk."""

from __future__ import annotations

from ..model.card import sha256_bytes


def read_card_file(file) -> tuple[str | None, str | None]:
    """Return ``(text, sha256_of_raw_bytes)`` or ``(None, None)`` when the file is absent."""
    try:
        data = file.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None, None
    return data.decode("utf-8", errors="replace"), sha256_bytes(data)
