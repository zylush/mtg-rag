from dataclasses import dataclass, field

import pytest

from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import analyze_question
from app.retrieval.service import HybridRetrievalService, RetrievalCandidate


def _passage(passage_id: str) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        document_type="rule",
        citation_label=f"Rule {passage_id}",
        canonical_url=f"https://magic.wizards.com/rules#{passage_id}",
        text=f"Text for {passage_id}",
    )


@dataclass
class FakeEmbedding:
    calls: list[str] = field(default_factory=list)

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * 1536


class FakeRepository:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def exact(self, analysis, *, limit: int):  # type: ignore[no-untyped-def]
        self.limits.append(limit)
        return [RetrievalCandidate(_passage("exact"), 1, "exact", exact=True)]

    async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
        self.limits.append(limit)
        return [
            RetrievalCandidate(_passage("shared"), 1, "lexical"),
            RetrievalCandidate(_passage("lexical"), 2, "lexical"),
        ]

    async def vector(self, embedding: list[float], *, limit: int):
        self.limits.append(limit)
        return [
            RetrievalCandidate(_passage("shared"), 1, "vector"),
            RetrievalCandidate(_passage("vector"), 2, "vector"),
        ]


def test_question_analysis_extracts_explicit_card_names_and_rule_references() -> None:
    analysis = analyze_question('Does "Lightning Bolt" use rule 608.2h?')

    assert analysis.normalized == 'does "lightning bolt" use rule 608.2h?'
    assert analysis.quoted_card_names == ("lightning bolt",)
    assert analysis.rule_references == ("608.2h",)


@pytest.mark.asyncio
async def test_hybrid_retrieval_runs_exact_lexical_vector_rrf_and_pins_exact_first() -> None:
    repository = FakeRepository()
    embedding = FakeEmbedding()
    service = HybridRetrievalService(repository=repository, embedding=embedding)

    passages = await service.retrieve('What does "Lightning Bolt" do?')

    assert [passage.passage_id for passage in passages] == [
        "exact",
        "shared",
        "lexical",
        "vector",
    ]
    assert repository.limits == [20, 20, 20]
    assert embedding.calls == ['what does "lightning bolt" do?']


@pytest.mark.asyncio
async def test_retrieval_context_is_capped_at_eight_passages() -> None:
    class ManyRepository(FakeRepository):
        async def lexical(self, question: str, *, limit: int):
            return [RetrievalCandidate(_passage(f"p-{index}"), index + 1, "lexical") for index in range(20)]

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    service = HybridRetrievalService(repository=ManyRepository(), embedding=FakeEmbedding())

    passages = await service.retrieve("What is priority?")

    assert len(passages) == 8

