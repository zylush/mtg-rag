from types import SimpleNamespace

import pytest

from app.retrieval.embeddings import OpenAIEmbeddingAdapter


class FakeEmbeddings:
    def __init__(
        self,
        forced_embedding: list[float] | None = None,
        *,
        reverse_batch_response: bool = False,
        distinct_embeddings: bool = False,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.forced_embedding = forced_embedding
        self.reverse_batch_response = reverse_batch_response
        self.distinct_embeddings = distinct_embeddings

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        dimensions = int(kwargs["dimensions"])  # type: ignore[arg-type]
        raw_input = kwargs["input"]
        inputs = raw_input if isinstance(raw_input, list) else [raw_input]
        data = [
            SimpleNamespace(
                index=index,
                embedding=self.forced_embedding
                or (
                    [float(index + 1)] * dimensions
                    if self.distinct_embeddings
                    else [0.1] * dimensions
                ),
            )
            for index, _ in enumerate(inputs)
        ]
        if self.reverse_batch_response:
            data.reverse()
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(
        self,
        forced_embedding: list[float] | None = None,
        *,
        reverse_batch_response: bool = False,
        distinct_embeddings: bool = False,
    ) -> None:
        self.embeddings = FakeEmbeddings(
            forced_embedding,
            reverse_batch_response=reverse_batch_response,
            distinct_embeddings=distinct_embeddings,
        )


@pytest.mark.asyncio
async def test_embedding_adapter_pins_model_dimensions_and_float_encoding() -> None:
    client = FakeClient()
    adapter = OpenAIEmbeddingAdapter(
        client=client,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=1536,
    )

    embedding = await adapter.embed("What is flying?")

    assert len(embedding) == 1536
    assert embedding[:3] == [0.1, 0.1, 0.1]
    assert client.embeddings.calls == [
        {
            "model": "text-embedding-3-small",
            "input": ["What is flying?"],
            "dimensions": 1536,
            "encoding_format": "float",
        }
    ]


@pytest.mark.asyncio
async def test_embedding_adapter_rejects_wrong_vector_length() -> None:
    client = FakeClient(forced_embedding=[0.1, 0.2, 0.3])
    adapter = OpenAIEmbeddingAdapter(
        client=client,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=2,
    )

    with pytest.raises(ValueError, match="dimension"):
        await adapter.embed("What is flying?")


@pytest.mark.asyncio
async def test_embedding_adapter_batches_inputs_and_restores_response_index_order() -> None:
    client = FakeClient(reverse_batch_response=True, distinct_embeddings=True)
    adapter = OpenAIEmbeddingAdapter(
        client=client,  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=2,
    )

    embeddings = await adapter.embed_many(["First document", "Second document"])

    assert embeddings == [[1.0, 1.0], [2.0, 2.0]]
    assert client.embeddings.calls == [
        {
            "model": "text-embedding-3-small",
            "input": ["First document", "Second document"],
            "dimensions": 2,
            "encoding_format": "float",
        }
    ]


@pytest.mark.asyncio
async def test_embedding_adapter_rejects_an_empty_batch() -> None:
    adapter = OpenAIEmbeddingAdapter(
        client=FakeClient(),  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=2,
    )

    with pytest.raises(ValueError, match="at least one"):
        await adapter.embed_many([])
