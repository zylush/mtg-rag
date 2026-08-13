from app.ingestion.scryfall import parse_oracle_cards, parse_rulings


def test_oracle_parser_filters_language_and_digital_cards_and_preserves_face_order() -> None:
    cards = [
        {
            "id": "printing-1",
            "oracle_id": "oracle-1",
            "lang": "en",
            "digital": False,
            "name": "Fire // Ice",
            "layout": "split",
            "card_faces": [
                {"name": "Fire", "oracle_text": "Fire deals 2 damage divided as you choose."},
                {"name": "Ice", "oracle_text": "Tap target permanent. Draw a card."},
            ],
        },
        {"id": "jp", "oracle_id": "oracle-jp", "lang": "ja", "digital": False, "name": "島"},
        {
            "id": "digital",
            "oracle_id": "oracle-digital",
            "lang": "en",
            "digital": True,
            "name": "Digital Only",
        },
    ]

    parsed = parse_oracle_cards(cards)

    assert len(parsed) == 1
    assert parsed[0].oracle_id == "oracle-1"
    assert [face.name for face in parsed[0].faces] == ["Fire", "Ice"]
    assert parsed[0].document_text.index("Fire") < parsed[0].document_text.index("Ice")


def test_oracle_parser_deduplicates_printings_by_oracle_identity() -> None:
    cards = [
        {
            "id": "old",
            "oracle_id": "oracle-1",
            "lang": "en",
            "digital": False,
            "name": "Lightning Bolt",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "released_at": "2010-01-01",
        },
        {
            "id": "new",
            "oracle_id": "oracle-1",
            "lang": "en",
            "digital": False,
            "name": "Lightning Bolt",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "released_at": "2026-01-01",
        },
    ]

    parsed = parse_oracle_cards(cards)

    assert len(parsed) == 1
    assert parsed[0].representative_printing_id == "new"


def test_rulings_keep_attribution_and_rank_wotc_first() -> None:
    rulings = [
        {
            "oracle_id": "oracle-1",
            "published_at": "2026-02-01",
            "source": "scryfall",
            "comment": "Editorial explanation.",
        },
        {
            "oracle_id": "oracle-1",
            "published_at": "2025-02-01",
            "source": "wotc",
            "comment": "Official ruling.",
        },
    ]

    parsed = parse_rulings(rulings)

    assert [r.source for r in parsed] == ["wotc", "scryfall"]
    assert parsed[0].attribution == "Wizards of the Coast"
    assert parsed[1].attribution == "Scryfall"


def test_rulings_skip_records_without_substantive_comment_text() -> None:
    rulings = [
        {
            "oracle_id": "oracle-empty",
            "published_at": "2026-02-02",
            "source": "wotc",
        },
        {
            "oracle_id": "oracle-whitespace",
            "published_at": "2026-02-02",
            "source": "scryfall",
            "comment": "   ",
        },
        {
            "oracle_id": "oracle-usable",
            "published_at": "2026-02-02",
            "source": "wotc",
            "comment": "Usable official ruling.",
        },
    ]

    parsed = parse_rulings(rulings)

    assert [(ruling.oracle_id, ruling.comment) for ruling in parsed] == [
        ("oracle-usable", "Usable official ruling."),
    ]


def test_rulings_deduplicate_canonical_identity_and_prefer_wotc() -> None:
    rulings = [
        {
            "oracle_id": "oracle-1",
            "published_at": "2026-02-01",
            "source": "scryfall",
            "comment": "Shared explanation.",
        },
        {
            "oracle_id": "oracle-1",
            "published_at": "2026-02-01",
            "source": "wotc",
            "comment": "Shared explanation.",
        },
        {
            "oracle_id": "oracle-1",
            "published_at": "2026-02-01",
            "source": "wotc",
            "comment": "Shared explanation.",
        },
    ]

    parsed = parse_rulings(rulings)

    assert len(parsed) == 1
    assert parsed[0].source == "wotc"
    assert parsed[0].attribution == "Wizards of the Coast"
