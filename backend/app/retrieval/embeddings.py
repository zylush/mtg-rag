from __future__ import annotations

from openai import AsyncOpenAI


class OpenAIEmbeddingAdapter:
    def __init__(self, *, client: AsyncOpenAI, model: str, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self._client = client
        self._model = model
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
            encoding_format="float",
        )
        if not response.data:
            raise ValueError("embedding response contained no vectors")
        embedding = list(response.data[0].embedding)
        if len(embedding) != self._dimensions:
            raise ValueError(
                f"embedding dimension mismatch: expected {self._dimensions}, got {len(embedding)}"
            )
        return embedding

