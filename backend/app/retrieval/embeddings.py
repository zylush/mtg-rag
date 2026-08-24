from __future__ import annotations

from openai import AsyncOpenAI

MAX_EMBEDDING_INPUTS_PER_REQUEST = 128


class OpenAIEmbeddingAdapter:
    def __init__(self, *, client: AsyncOpenAI, model: str, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self._client = client
        self._model = model
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_many([text]))[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("embedding batch must contain at least one input")
        if len(texts) > MAX_EMBEDDING_INPUTS_PER_REQUEST:
            raise ValueError(
                f"embedding batch exceeds {MAX_EMBEDDING_INPUTS_PER_REQUEST} inputs"
            )
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        if len(response.data) != len(texts):
            raise ValueError("embedding response contained no vectors")
        embeddings_by_index: dict[int, list[float]] = {}
        for item in response.data:
            index = item.index
            if index < 0 or index >= len(texts) or index in embeddings_by_index:
                raise ValueError("embedding response indices are invalid")
            embedding = list(item.embedding)
            if len(embedding) != self._dimensions:
                raise ValueError(
                    "embedding dimension mismatch: "
                    f"expected {self._dimensions}, got {len(embedding)}"
                )
            embeddings_by_index[index] = embedding
        if len(embeddings_by_index) != len(texts):
            raise ValueError("embedding response indices are incomplete")
        return [embeddings_by_index[index] for index in range(len(texts))]
