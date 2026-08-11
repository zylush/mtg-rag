from types import SimpleNamespace

import pytest

from app.retrieval.embeddings import OpenAIEmbeddingAdapter


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class FakeClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddings()


@pytest.mark.asyncio
async def test_embedding_adapter_pins_model_dimensions_and_float_encoding() -> None:
    client = FakeClient()
    adapter = OpenAIEmbeddingAdapter(
        client=client,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=1536,
    )

    embedding = await adapter.embed("What is flying?")

    assert embedding == [0.1, 0.2, 0.3]
    assert client.embeddings.calls == [
        {
            "model": "text-embedding-3-small",
            "input": "What is flying?",
            "dimensions": 1536,
            "encoding_format": "float",
        }
    ]


@pytest.mark.asyncio
async def test_embedding_adapter_rejects_wrong_vector_length() -> None:
    client = FakeClient()
    adapter = OpenAIEmbeddingAdapter(
        client=client,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=2,
    )

    with pytest.raises(ValueError, match="dimension"):
        await adapter.embed("What is flying?")

