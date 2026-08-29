from app.services.author_briefing import author_briefing_identity


def test_author_briefing_identity_is_deterministic_and_line_ending_canonical() -> None:
    assert author_briefing_identity("opinião\r\nlinha") == author_briefing_identity(
        "opinião\nlinha"
    )
    assert author_briefing_identity("opinião\nlinha ") != author_briefing_identity(
        "opinião\nlinha"
    )


def test_missing_and_explicit_empty_briefing_are_distinct() -> None:
    assert author_briefing_identity(None) != author_briefing_identity("")
