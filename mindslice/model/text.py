"""Shared Unicode normalization for card text and exact-match keys."""

from __future__ import annotations

import re
import unicodedata

# Default-ignorable characters that must not change what text matches.
_IGNORABLE = re.compile("[­​-‍⁠﻿︀-️\U000e0100-\U000e01ef]")


def normalize(text: str) -> str:
    """Search-side normalization: drop ignorable characters, then NFKC."""
    return unicodedata.normalize("NFKC", _IGNORABLE.sub("", text or ""))


def fold(text: str) -> str:
    """Normalization for exact-match keys (aliases, tags): NFKC + case folding + whitespace."""
    return " ".join(normalize(text).casefold().split())
