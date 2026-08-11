import pytest

from app.generation.citations import (
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
    )

    resolved = validate_citations(
        answer,
        {
            "rule-704.5d": {
                "label": "Comprehensive Rules 704.5d",
                "url": "https://magic.wizards.com/rules#704.5d",
            }
        },
    )

    assert resolved.citations[0].url.endswith("#704.5d")
    assert resolved.citations[0].label == "Comprehensive Rules 704.5d"


def test_unknown_citation_ids_raise_a_repairable_validation_error() -> None:
    answer = GroundedAnswer(
        answer="Unsupported answer.",
        citations=[ModelCitation(passage_id="invented", claim="Invented claim")],
        assumptions=[],
        confidence="low",
        needs_clarification=False,
    )

    with pytest.raises(CitationValidationError) as error:
        validate_citations(answer, {})

    assert error.value.unknown_ids == ("invented",)

