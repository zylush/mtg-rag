from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.ingestion.activation import IngestionValidationError, ValidationMetrics
from app.ingestion.download import DownloadedSource
from app.ingestion.pipeline import (
    CachedDocumentEmbedding,
    CorpusDocument,
    IngestionPipeline,
    ParsedCorpus,
    SourceDefinition,
)


@dataclass
class FakeSnapshotStore:
    fail: bool = False
    events: list[str] = field(default_factory=list)

    async def put_immutable(self, **kwargs: object) -> str:
        self.events.append("snapshot")
        if self.fail:
            raise RuntimeError("GCS unavailable")
        return "gs://snapshots/rules/sha.txt"


@dataclass
class FakeEmbedding:
    calls: list[str] = field(default_factory=list)

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2]


class FakeRepository:
    def __init__(self, *, existing_version: str | None = None) -> None:
        self.existing_version = existing_version
        self.events: list[str] = []
        self.staged_documents: list[CorpusDocument] = []
        self.staged_embeddings: dict[str, list[float]] = {}
        self.cached = {
            "100.1": CachedDocumentEmbedding(content_hash="same-hash", embedding=[0.9, 0.8])
        }

    async def find_version_by_sha(self, source_name: str, sha256: str) -> str | None:
        self.events.append("dedupe")
        return self.existing_version

    async def create_staged_version(self, **kwargs: object) -> str:
        self.events.append("create-staged")
        return "rules-new"

    async def active_document_embeddings(
        self, source_name: str
    ) -> dict[str, CachedDocumentEmbedding]:
        self.events.append("load-active-embeddings")
        return self.cached

    async def stage_corpus(
        self,
        *,
        version_id: str,
        corpus: ParsedCorpus,
        embeddings: dict[str, list[float]],
    ) -> None:
        self.events.append("stage-corpus")
        self.staged_documents = list(corpus.documents)
        self.staged_embeddings = embeddings

    async def validate_staged(
        self, version_id: str, minimum_record_count: int
    ) -> ValidationMetrics:
        self.events.append("validate")
        return ValidationMetrics(100, minimum_record_count, 0, 0, 0)

    async def activate(self, source_name: str, version_id: str) -> None:
        self.events.append("activate")

    async def mark_failed(self, version_id: str, category: str) -> None:
        self.events.append(f"failed:{category}")


async def fake_download(*args: object, **kwargs: object) -> DownloadedSource:
    return DownloadedSource(
        source_url="https://media.wizards.com/rules.txt",
        effective_url="https://media.wizards.com/rules.txt",
        mime_type="text/plain",
        payload=b"rules",
        sha256="abc123",
    )


def fake_parse(payload: bytes, version_id: str) -> ParsedCorpus:
    return ParsedCorpus(
        source_version_id=version_id,
        documents=(
            CorpusDocument(
                canonical_key="100.1",
                document_type="rule",
                text="Unchanged rule",
                metadata={},
                content_hash="same-hash",
            ),
            CorpusDocument(
                canonical_key="100.2",
                document_type="rule",
                text="New rule",
                metadata={},
                content_hash="new-hash",
            ),
        ),
        rules=(),
        glossary=(),
        cards=(),
        rulings=(),
    )


def source() -> SourceDefinition:
    return SourceDefinition(
        name="rules",
        source_type="rules",
        url="https://media.wizards.com/rules.txt",
        parser_version="1",
        schema_version="1",
        minimum_record_count=90,
    )


@pytest.mark.asyncio
async def test_pipeline_snapshots_stages_validates_then_activates_and_embeds_only_changes() -> None:
    snapshots = FakeSnapshotStore()
    repository = FakeRepository()
    embedding = FakeEmbedding()
    pipeline = IngestionPipeline(
        repository=repository,
        snapshot_store=snapshots,
        embedding=embedding,
        download=fake_download,
    )

    result = await pipeline.refresh(source(), parse=fake_parse)

    assert result.status == "activated"
    assert result.new_embedding_count == 1
    assert snapshots.events == ["snapshot"]
    assert repository.events == [
        "dedupe",
        "create-staged",
        "load-active-embeddings",
        "stage-corpus",
        "validate",
        "activate",
    ]
    assert embedding.calls == ["New rule"]
    assert repository.staged_embeddings == {
        "100.1": [0.9, 0.8],
        "100.2": [0.1, 0.2],
    }


@pytest.mark.asyncio
async def test_unchanged_sha_is_idempotent_and_skips_snapshot_parse_and_embedding() -> None:
    snapshots = FakeSnapshotStore()
    repository = FakeRepository(existing_version="rules-existing")
    embedding = FakeEmbedding()
    parsed = False

    def parser(payload: bytes, version_id: str) -> ParsedCorpus:
        nonlocal parsed
        parsed = True
        return fake_parse(payload, version_id)

    pipeline = IngestionPipeline(
        repository=repository,
        snapshot_store=snapshots,
        embedding=embedding,
        download=fake_download,
    )

    result = await pipeline.refresh(source(), parse=parser)

    assert result.status == "unchanged"
    assert result.version_id == "rules-existing"
    assert snapshots.events == []
    assert embedding.calls == []
    assert parsed is False


@pytest.mark.asyncio
async def test_snapshot_failure_prevents_staging_or_activation() -> None:
    repository = FakeRepository()
    pipeline = IngestionPipeline(
        repository=repository,
        snapshot_store=FakeSnapshotStore(fail=True),
        embedding=FakeEmbedding(),
        download=fake_download,
    )

    with pytest.raises(RuntimeError, match="GCS unavailable"):
        await pipeline.refresh(source(), parse=fake_parse)

    assert repository.events == ["dedupe"]


@pytest.mark.asyncio
async def test_validation_failure_marks_candidate_failed_and_never_activates() -> None:
    repository = FakeRepository()

    async def invalid(version_id: str, minimum_record_count: int) -> ValidationMetrics:
        repository.events.append("validate")
        return ValidationMetrics(2, minimum_record_count, 0, 1, 0)

    repository.validate_staged = invalid  # type: ignore[method-assign]
    pipeline = IngestionPipeline(
        repository=repository,
        snapshot_store=FakeSnapshotStore(),
        embedding=FakeEmbedding(),
        download=fake_download,
    )

    with pytest.raises(IngestionValidationError):
        await pipeline.refresh(source(), parse=fake_parse)

    assert "activate" not in repository.events
    assert repository.events[-1] == "failed:validation"

