import pytest
from pydantic import ValidationError

from app.generation.citations import (
    CitationSupportError,
    CitationValidationError,
    GroundedAnswer,
    ModelCitation,
    validate_citations,
)


def test_known_model_citations_resolve_to_server_owned_canonical_links() -> None:
    answer = GroundedAnswer(
        answer="A token ceases to exist as a state-based action.",
        citations=[ModelCitation(passage_id="rule-704.5d", claim="Tokens cease to exist.")],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )

    resolved = validate_citations(
        answer,
        {
            "rule-704.5d": {
                "label": "Comprehensive Rules 704.5d",
                "url": "https://magic.wizards.com/rules#704.5d",
                "text": "Tokens cease to exist.",
            }
        },
    )

    assert resolved.citations[0].url.endswith("#704.5d")
    assert resolved.citations[0].label == "Comprehensive Rules 704.5d"


def test_duplicate_passage_claims_are_merged_before_persistence() -> None:
    answer = GroundedAnswer(
        answer="The same rule supports both parts of the answer.",
        citations=[
            ModelCitation(passage_id="rule-608.2h", claim="The effect gets information."),
            ModelCitation(passage_id="rule-608.2h", claim="Last known information applies."),
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )

    resolved = validate_citations(
        answer,
        {
            "rule-608.2h": {
                "label": "Comprehensive Rules 608.2h",
                "url": "https://magic.wizards.com/rules#608.2h",
                "text": (
                    "The effect gets information. Last known information applies."
                ),
            }
        },
    )

    assert [citation.passage_id for citation in resolved.citations] == ["rule-608.2h"]
    assert resolved.citations[0].claim == (
        "The effect gets information. Last known information applies."
    )


def test_unknown_citation_ids_raise_a_repairable_validation_error() -> None:
    answer = GroundedAnswer(
        answer="Unsupported answer.",
        citations=[ModelCitation(passage_id="invented", claim="Invented claim")],
        assumptions=[],
        confidence="low",
        needs_clarification=False,
        behavior="answer",
    )

    with pytest.raises(CitationValidationError) as error:
        validate_citations(answer, {})

    assert error.value.unknown_ids == ("invented",)


def test_explicit_abstention_survives_citation_resolution() -> None:
    answer = GroundedAnswer(
        answer="The supplied passages do not contain current market prices.",
        citations=[ModelCitation(passage_id="card", claim="The passage is card data only.")],
        assumptions=[],
        confidence="low",
        needs_clarification=False,
        behavior="abstain",
    )

    resolved = validate_citations(
        answer,
        {
            "card": {
                "label": "Card data",
                "url": "https://example.test/card",
                "text": "The passage is card data only.",
            }
        },
    )

    assert resolved.behavior == "abstain"


def test_normalized_exact_excerpt_matches_unicode_and_whitespace_variants() -> None:
    answer = GroundedAnswer(
        answer="The ability costs one mana.",
        citations=[
            ModelCitation(
                passage_id="rule-1",
                claim="Pay 1 mana to activate this ability.",
            )
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )

    resolved = validate_citations(
        answer,
        {
            "rule-1": {
                "label": "Rule 1",
                "url": "https://example.test/rule-1",
                "text": "Pay \uff11 mana\n\tto activate this ability.",
            }
        },
    )

    assert resolved.citations[0].claim == "Pay 1 mana to activate this ability."


def test_paraphrased_claim_raises_repairable_support_error() -> None:
    answer = GroundedAnswer(
        answer="A token ceases to exist.",
        citations=[
            ModelCitation(
                passage_id="rule-704.5d",
                claim="Tokens disappear after leaving the battlefield.",
            )
        ],
        assumptions=[],
        confidence="high",
        needs_clarification=False,
        behavior="answer",
    )

    with pytest.raises(CitationSupportError) as error:
        validate_citations(
            answer,
            {
                "rule-704.5d": {
                    "label": "Comprehensive Rules 704.5d",
                    "url": "https://magic.wizards.com/rules#704.5d",
                    "text": (
                        "A token in a zone other than the battlefield ceases to exist."
                    ),
                }
            },
        )

    assert error.value.unsupported_ids == ("rule-704.5d",)


def test_model_citation_excerpt_is_limited_to_320_characters() -> None:
    citation = ModelCitation(passage_id="rule-1", claim="x" * 320)

    assert len(citation.claim) == 320
    with pytest.raises(ValidationError, match="at most 320 characters"):
        ModelCitation(passage_id="rule-1", claim="x" * 321)
