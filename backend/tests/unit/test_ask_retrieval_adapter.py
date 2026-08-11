from dataclasses import dataclass, field

import pytest

from app.ask.retrieval import AskRetrievalAdapter
from app.generation.openai_adapter import RetrievedPassage


@dataclass
class FakeEmbedding:
    calls: list[str] = field(default_factory=list)

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2]


@dataclass
class FakeHybrid:
    calls: list[tuple[str, list[float]]] = field(default_factory=list)

    async def retrieve_with_embedding(
        self, question: str, embedding: list[float]
    ) -> list[RetrievedPassage]:
        self.calls.append((question, embedding))
        return [
            RetrievedPassage(
                passage_id="p1",
                document_type="rule",
                citation_label="Rule 100.1",
                canonical_url="https://example.test/100.1",
                text="Rule text",
            )
        ]


@pytest.mark.asyncio
async def test_ask_retrieval_adapter_reuses_one_normalized_question_embedding() -> None:
    embedding = FakeEmbedding()
    hybrid = FakeHybrid()
    adapter = AskRetrievalAdapter(embedding=embedding, hybrid=hybrid)  # type: ignore[arg-type]

    vector = await adapter.embed_question("  What IS Flying? ")
    bundle = await adapter.retrieve_with_embedding("  What IS Flying? ", vector)

    assert embedding.calls == ["what is flying?"]
    assert hybrid.calls == [("  What IS Flying? ", [0.1, 0.2])]
    assert bundle.embedding == vector
    assert bundle.passages[0].passage_id == "p1"

