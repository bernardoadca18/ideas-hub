"""Small, deterministic guard against numbered-work/entity substitution."""

from __future__ import annotations

import re

_NUMBERED_ENTITY = re.compile(
    r"\b(?P<base>[A-Z][A-Za-z0-9._-]{1,})\s+"
    r"(?P<marker>[IVXLCDM]{1,7}|[1-9]\d{0,3})\b"
)


def numbered_entities(text: str) -> set[tuple[str, str]]:
    """Return conservative (entity stem, installment) pairs such as GTA IV."""

    return {
        (match.group("base").casefold(), match.group("marker").casefold())
        for match in _NUMBERED_ENTITY.finditer(text)
    }


def validate_visual_query_entity_scope(*, query: str, authorized_context: str) -> None:
    """Reject a sibling installment when that stem is anchored to another one.

    This intentionally is not general-purpose entity resolution. The prompt owns the
    broad semantic rule; this boundary catches the reliable numbered-work drift case.
    Explicit comparisons pass because both installments occur in authorized context.
    """

    authorized = numbered_entities(authorized_context)
    query_entities = numbered_entities(query)
    allowed_by_stem: dict[str, set[str]] = {}
    for stem, marker in authorized:
        allowed_by_stem.setdefault(stem, set()).add(marker)
    for stem, marker in query_entities:
        allowed = allowed_by_stem.get(stem)
        if allowed and marker not in allowed:
            rendered = ", ".join(sorted(value.upper() for value in allowed))
            raise ValueError(
                f"VisualQuery entity drift: {stem.upper()} {marker.upper()} is not "
                f"authorized; allowed installment(s): {rendered}"
            )
