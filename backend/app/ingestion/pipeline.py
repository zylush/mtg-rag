from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
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
        self, source_name: str, canonical_keys: tuple[str, ...] | None = None
    ) -> dict[str, CachedDocumentEmbedding]: ...

    async def active_document_hashes(self, source_name: str) -> dict[str, str]: ...

    async def active_card_oracle_ids(
        self, oracle_ids: tuple[str, ...]
    ) -> frozenset[str]: ...

    async def stage_metadata(self, *, version_id: str, corpus: ParsedCorpus) -> None: ...

    async def stage_passages(
        self,
        *,
        version_id: str,
        documents: tuple[CorpusDocument, ...],
        embeddings: dict[str, list[float]],
    ) -> None: ...

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

        if corpus.rulings:
            supported_oracle_ids = await self._repository.active_card_oracle_ids(
                tuple(sorted({ruling.oracle_id for ruling in corpus.rulings}))
            )
            corpus = replace(
                corpus,
                documents=tuple(
                    document
                    for document in corpus.documents
                    if document.document_type != "ruling"
                    or document.metadata.get("oracle_id") in supported_oracle_ids
                ),
                rulings=tuple(
                    ruling
                    for ruling in corpus.rulings
                    if ruling.oracle_id in supported_oracle_ids
                ),
            )

        try:
            await self._repository.stage_metadata(version_id=version_id, corpus=corpus)
            active_hashes = await self._repository.active_document_hashes(source.name)
            changed_documents = tuple(
                document
                for document in corpus.documents
                if active_hashes.get(document.canonical_key) != document.content_hash
            )
            changed_embeddings: dict[str, list[float]] = {}
            for start in range(0, len(changed_documents), EMBEDDING_BATCH_SIZE):
                batch = changed_documents[start : start + EMBEDDING_BATCH_SIZE]
                batch_embeddings = await self._embedding.embed_many(
                    [document.text for document in batch]
                )
                if len(batch_embeddings) != len(batch):
                    raise ValueError("embedding batch response count does not match request")
                changed_embeddings.update(
                    {
                        document.canonical_key: embedding
                        for document, embedding in zip(batch, batch_embeddings, strict=True)
                    }
                )

            for start in range(0, len(corpus.documents), EMBEDDING_BATCH_SIZE):
                batch = corpus.documents[start : start + EMBEDDING_BATCH_SIZE]
                reusable_keys = tuple(
                    document.canonical_key
                    for document in batch
                    if document.canonical_key not in changed_embeddings
                )
                cached = (
                    await self._repository.active_document_embeddings(
                        source.name,
                        reusable_keys,
                    )
                    if reusable_keys
                    else {}
                )
                embeddings: dict[str, list[float]] = {}
                for document in batch:
                    changed_embedding = changed_embeddings.get(document.canonical_key)
                    if changed_embedding is not None:
                        embeddings[document.canonical_key] = changed_embedding
                        continue
                    previous = cached.get(document.canonical_key)
                    if previous is None or previous.content_hash != document.content_hash:
                        raise RuntimeError("active document changed while staging corpus")
                    embeddings[document.canonical_key] = previous.embedding
                await self._repository.stage_passages(
                    version_id=version_id,
                    documents=batch,
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
