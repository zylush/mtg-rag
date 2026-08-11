from datetime import date

import pytest

from app.ingestion.rules import RulesParseError, parse_comprehensive_rules


RULES_FIXTURE = """Magic: The Gathering Comprehensive Rules
These rules are effective as of July 25, 2026.

100. General
100.1. These Magic rules apply to any Magic game with two or more players.
100.1a A two-player game is a game that begins with only two players.
100.2. To play, each player needs a deck of traditional Magic cards.

101. The Magic Golden Rules
101.1. Whenever a card's text directly contradicts these rules, the card takes precedence.

Glossary
Active Player, Nonactive Player Order
A system that determines the order in which players make choices.

Owner
The player who started the game with a card in their deck.
"""


def test_rules_are_split_on_canonical_rule_boundaries_with_context() -> None:
    parsed = parse_comprehensive_rules(RULES_FIXTURE, source_version_id="rules-v1")

    assert [rule.rule_number for rule in parsed.rules] == ["100.1", "100.1a", "100.2", "101.1"]
    assert parsed.rules[1].parent_rule == "100.1"
    assert parsed.rules[1].section_heading == "100. General"
    assert parsed.rules[1].previous_rule == "100.1"
    assert parsed.rules[1].next_rule == "100.2"
    assert parsed.effective_date == date(2026, 7, 25)
    assert parsed.rules[0].source_version_id == "rules-v1"


def test_glossary_entries_are_separate_retrievable_documents() -> None:
    parsed = parse_comprehensive_rules(RULES_FIXTURE, source_version_id="rules-v1")

    assert [entry.term for entry in parsed.glossary] == [
        "Active Player, Nonactive Player Order",
        "Owner",
    ]
    assert parsed.glossary[0].text.startswith("A system that determines")


def test_duplicate_rule_numbers_reject_the_source() -> None:
    duplicated = RULES_FIXTURE.replace(
        "100.2. To play, each player needs a deck of traditional Magic cards.",
        "100.1. This duplicate must fail validation.",
    )

    with pytest.raises(RulesParseError, match="duplicate rule number"):
        parse_comprehensive_rules(duplicated, source_version_id="rules-v1")

