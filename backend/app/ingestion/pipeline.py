from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.ingestion.activation import IngestionValidationError, ValidationMetrics
from app.ingestion.download import DownloadedSource
from app.ingestion.rules import ParsedGlossaryEntry, ParsedRule
from app.ingestion.scryfall import ParsedOracleCard, ParsedRuling

EMBEDDING_BATCH_SIZE = 128


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    source_type: str
    url: str
    parser_version: str
    schema_version: str
    minimum_record_count: int


@dataclass(frozen=True)
class CorpusDocument:
    canonical_key: str
    document_type: str
    text: str
    metadata: dict[str, Any]
    content_hash: str


@dataclass(frozen=True)
class ParsedCorpus:
    source_version_id: str
    documents: tuple[CorpusDocument, ...]
    rules: tuple[ParsedRule, ...]
    glossary: tuple[ParsedGlossaryEntry, ...]
    cards: tuple[ParsedOracleCard, ...]
    rulings: tuple[ParsedRuling, ...]


@dataclass(frozen=True)
class CachedDocumentEmbedding:
    content_hash: str
    embedding: list[float]


@dataclass(frozen=True)
class IngestionResult:
    status: str
    version_id: str
    new_embedding_count: int


class SnapshotStore(Protocol):
    async def put_immutable(
        self,
        *,
        source_name: str,
        fetched_at: datetime,
        sha256: str,
        payload: bytes,
        mime_type: str,
    ) -> str: ...


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class IngestionRepository(Protocol):
    async def find_version_by_sha(self, source_name: str, sha256: str) -> str | None: ...

    async def create_staged_version(
        self,
        *,
        source: SourceDefinition,
        source_url: str,
        fetched_at: datetime,
        sha256: str,
        raw_gcs_uri: str,
    ) -> str: ...

    async def active_document_embeddings(
        self, source_name: str
    ) -> dict[str, CachedDocumentEmbedding]: ...

    async def stage_corpus(
        self,
        *,
        version_id: str,
        corpus: ParsedCorpus,
        embeddings: dict[str, list[float]],
    ) -> None: ...

    async def validate_staged(
        self, version_id: str, minimum_record_count: int
    ) -> ValidationMetrics: ...

    async def activate(self, source_name: str, version_id: str) -> None: ...

    async def mark_failed(self, version_id: str, category: str) -> None: ...


Download = Callable[[SourceDefinition], Awaitable[DownloadedSource]]
Parser = Callable[[bytes, str], ParsedCorpus]


class IngestionPipeline:
    def __init__(
        self,
        *,
        repository: IngestionRepository,
        snapshot_store: SnapshotStore,
        embedding: EmbeddingProvider,
        download: Download,
    ) -> None:
        self._repository = repository
        self._snapshot_store = snapshot_store
        self._embedding = embedding
        self._download = download

    async def refresh(self, source: SourceDefinition, *, parse: Parser) -> IngestionResult:
        downloaded = await self._download(source)
        existing = await self._repository.find_version_by_sha(source.name, downloaded.sha256)
        if existing is not None:
            return IngestionResult(status="unchanged", version_id=existing, new_embedding_count=0)

        fetched_at = datetime.now(UTC)
        snapshot_uri = await self._snapshot_store.put_immutable(
            source_name=source.name,
            fetched_at=fetched_at,
            sha256=downloaded.sha256,
            payload=downloaded.payload,
            mime_type=downloaded.mime_type,
        )
        version_id = await self._repository.create_staged_version(
            source=source,
            source_url=downloaded.effective_url,
            fetched_at=fetched_at,
            sha256=downloaded.sha256,
            raw_gcs_uri=snapshot_uri,
        )

        try:
            corpus = parse(downloaded.payload, version_id)
        except Exception:
            await self._repository.mark_failed(version_id, "parse")
            raise

        try:
            cached = await self._repository.active_document_embeddings(source.name)
            embeddings: dict[str, list[float]] = {}
            changed_documents: list[CorpusDocument] = []
            for document in corpus.documents:
                previous = cached.get(document.canonical_key)
                if previous is not None and previous.content_hash == document.content_hash:
                    embeddings[document.canonical_key] = previous.embedding
                else:
                    changed_documents.append(document)
            for start in range(0, len(changed_documents), EMBEDDING_BATCH_SIZE):
                batch = changed_documents[start : start + EMBEDDING_BATCH_SIZE]
                batch_embeddings = await self._embedding.embed_many(
                    [document.text for document in batch]
                )
                if len(batch_embeddings) != len(batch):
                    raise ValueError("embedding batch response count does not match request")
                for document, embedding in zip(batch, batch_embeddings, strict=True):
                    embeddings[document.canonical_key] = embedding
            await self._repository.stage_corpus(
                version_id=version_id,
                corpus=corpus,
                embeddings=embeddings,
            )
        except Exception:
            await self._repository.mark_failed(version_id, "staging")
            raise

        metrics = await self._repository.validate_staged(
            version_id, source.minimum_record_count
        )
        failures = metrics.errors()
        if failures:
            await self._repository.mark_failed(version_id, "validation")
            raise IngestionValidationError("; ".join(failures))

        await self._repository.activate(source.name, version_id)
        return IngestionResult(
            status="activated",
            version_id=version_id,
            new_embedding_count=len(changed_documents),
        )
