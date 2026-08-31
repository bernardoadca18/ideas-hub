"""Deterministic identity contract for author-provided editorial context."""

from __future__ import annotations

import hashlib
import unicodedata

AUTHOR_BRIEFING_IDENTITY_VERSION = "author-briefing-v1"


def canonicalize_author_briefing(value: str | None) -> bytes:
    """Return the canonical bytes used by the author-briefing identity.

    The stored briefing is never changed.  Identity v1 normalizes only Unicode
    composition and line-ending representation; all other whitespace remains
    meaningful.  ``None`` is deliberately distinct from an explicitly supplied
    empty string.
    """

    if value is None:
        return b"null"
    normalized = (
        unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    )
    return b"text\x00" + normalized.encode("utf-8")


def author_briefing_identity(value: str | None) -> str:
    digest = hashlib.sha256(canonicalize_author_briefing(value)).hexdigest()
    return f"{AUTHOR_BRIEFING_IDENTITY_VERSION}:{digest}"
