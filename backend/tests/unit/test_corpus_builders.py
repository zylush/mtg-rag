import json

from app.ingestion.corpus import parse_cards_corpus, parse_rules_corpus, parse_rulings_corpus


RULES = """Magic: The Gathering Comprehensive Rules
These rules are effective as of July 25, 2026.

100. General
100.1. These rules apply to any Magic game.

Glossary
Owner
The player who started the game with a card in their deck.
"""


def test_rules_corpus_builds_independent_rule_and_glossary_passages() -> None:
    corpus = parse_rules_corpus(RULES.encode(), "rules-version")

    assert [(doc.document_type, doc.canonical_key) for doc in corpus.documents] == [
        ("rule", "100.1"),
        ("glossary", "owner"),
    ]
    assert corpus.documents[0].metadata["citation_label"] == "Comprehensive Rules 100.1"
    assert corpus.documents[0].metadata["canonical_url"].endswith("#100.1")
    assert len(corpus.documents[0].content_hash) == 64


def test_card_corpus_normalizes_one_document_per_oracle_identity() -> None:
    payload = json.dumps(
        [
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "oracle_id": "00000000-0000-0000-0000-000000000011",
                "lang": "en",
                "digital": False,
                "name": "Fire // Ice",
                "layout": "split",
                "card_faces": [
                    {"name": "Fire", "oracle_text": "Fire deals 2 damage."},
                    {"name": "Ice", "oracle_text": "Tap target permanent. Draw a card."},
                ],
            }
        ]
    ).encode()

    corpus = parse_cards_corpus(payload, "cards-version")

    assert len(corpus.cards) == len(corpus.documents) == 1
    assert corpus.documents[0].canonical_key == "00000000-0000-0000-0000-000000000011"
    assert corpus.documents[0].metadata["card_name"] == "Fire // Ice"
    assert corpus.cards[0].aliases == ("Fire // Ice", "Fire", "Ice")


def test_ruling_corpus_preserves_attribution_in_each_passage() -> None:
    payload = json.dumps(
        [
            {
                "oracle_id": "00000000-0000-0000-0000-000000000011",
                "published_at": "2026-01-01",
                "source": "wotc",
                "comment": "Official ruling.",
            }
        ]
    ).encode()

    corpus = parse_rulings_corpus(payload, "rulings-version")

    assert corpus.documents[0].metadata["source"] == "wotc"
    assert corpus.documents[0].metadata["attribution"] == "Wizards of the Coast"
    assert corpus.documents[0].canonical_key.startswith("00000000-0000-0000-0000-000000000011:")

