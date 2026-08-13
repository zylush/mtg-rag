from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Card,
    CardAlias,
    CardFace,
    GlossaryEntry,
    Passage,
    RuleSection,
    Ruling,
    SourceVersion,
)
from app.ingestion.activation import ActivationCandidate, ValidationMetrics
from app.ingestion.pipeline import (
    CachedDocumentEmbedding,
    ParsedCorpus,
    SourceDefinition,
)


class VersionStateError(RuntimeError):
    pass


class PostgresVersionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def activate_atomically(self, candidate: ActivationCandidate) -> None:
        try:
            candidate_id = uuid.UUID(candidate.version_id)
        except ValueError as exc:
            raise VersionStateError("candidate version ID is invalid") from exc

        async with self._session_factory.begin() as session:
            versions = (
                await session.execute(
                    select(SourceVersion)
                    .where(SourceVersion.source_name == candidate.source_name)
                    .with_for_update()
                )
            ).scalars().all()
            staged = next((version for version in versions if version.id == candidate_id), None)
            if staged is None or staged.status != "staged" or staged.is_active:
                raise VersionStateError("candidate is not a staged version for this source")

            now = datetime.now(UTC)
            old_ids = [version.id for version in versions if version.is_active]
            if old_ids:
                await session.execute(
                    update(SourceVersion)
                    .where(SourceVersion.id.in_(old_ids))
                    .values(is_active=False, status="inactive", deactivated_at=now)
                )
                await session.execute(
                    update(Passage)
                    .where(Passage.source_version_id.in_(old_ids))
                    .values(is_active=False)
                )

            await session.execute(
                update(SourceVersion)
                .where(SourceVersion.id == candidate_id)
                .values(
                    is_active=True,
                    status="active",
                    activated_at=now,
                    deactivated_at=None,
                )
            )
            await session.execute(
                update(Passage)
                .where(Passage.source_version_id == candidate_id)
                .values(is_active=True)
            )

    async def rollback_atomically(self, source_name: str) -> str:
        async with self._session_factory.begin() as session:
            versions = (
                await session.execute(
                    select(SourceVersion)
                    .where(SourceVersion.source_name == source_name)
                    .with_for_update()
                )
            ).scalars().all()
            current = next((version for version in versions if version.is_active), None)
            inactive = [version for version in versions if not version.is_active]
            inactive.sort(
                key=lambda version: (
                    version.deactivated_at or datetime.min.replace(tzinfo=UTC),
                    version.activated_at or datetime.min.replace(tzinfo=UTC),
                ),
                reverse=True,
            )
            if current is None or not inactive:
                raise VersionStateError("no previous active version is available")

            target = inactive[0]
            now = datetime.now(UTC)
            await session.execute(
                update(SourceVersion)
                .where(SourceVersion.id == current.id)
                .values(is_active=False, status="inactive", deactivated_at=now)
            )
            await session.execute(
                update(Passage)
                .where(Passage.source_version_id == current.id)
                .values(is_active=False)
            )
            await session.execute(
                update(SourceVersion)
                .where(SourceVersion.id == target.id)
                .values(
                    is_active=True,
                    status="active",
                    activated_at=now,
                    deactivated_at=None,
                )
            )
            await session.execute(
                update(Passage)
                .where(Passage.source_version_id == target.id)
                .values(is_active=True)
            )
            return str(target.id)


def _uuid(value: str, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"invalid UUID for {field}") from exc


class PostgresIngestionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._versions = PostgresVersionRepository(session_factory)

    async def find_version_by_sha(self, source_name: str, sha256: str) -> str | None:
        async with self._session_factory() as session:
            version_id = await session.scalar(
                select(SourceVersion.id).where(
                    SourceVersion.source_name == source_name,
                    SourceVersion.sha256 == sha256,
                    SourceVersion.status != "failed",
                )
            )
        return str(version_id) if version_id is not None else None

    async def create_staged_version(
        self,
        *,
        source: SourceDefinition,
        source_url: str,
        fetched_at: datetime,
        sha256: str,
        raw_gcs_uri: str,
    ) -> str:
        async with self._session_factory.begin() as session:
            existing = await session.scalar(
                select(SourceVersion)
                .where(
                    SourceVersion.source_name == source.name,
                    SourceVersion.sha256 == sha256,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.status != "failed" or existing.is_active:
                    raise VersionStateError("source version already exists and is not retryable")
                await session.execute(
                    delete(RuleSection).where(RuleSection.source_version_id == existing.id)
                )
                await session.execute(
                    delete(GlossaryEntry).where(GlossaryEntry.source_version_id == existing.id)
                )
                await session.execute(delete(Card).where(Card.source_version_id == existing.id))
                await session.execute(delete(Ruling).where(Ruling.source_version_id == existing.id))
                await session.execute(
                    delete(Passage).where(Passage.source_version_id == existing.id)
                )
                existing.source_type = source.source_type
                existing.source_url = source_url
                existing.effective_date = None
                existing.fetched_at = fetched_at
                existing.parser_version = source.parser_version
                existing.schema_version = source.schema_version
                existing.raw_gcs_uri = raw_gcs_uri
                existing.status = "staged"
                existing.is_active = False
                existing.activated_at = None
                existing.deactivated_at = None
                await session.flush()
                return str(existing.id)

            version = SourceVersion(
                source_name=source.name,
                source_type=source.source_type,
                source_url=source_url,
                effective_date=None,
                fetched_at=fetched_at,
                sha256=sha256,
                parser_version=source.parser_version,
                schema_version=source.schema_version,
                raw_gcs_uri=raw_gcs_uri,
                status="staged",
                is_active=False,
            )
            session.add(version)
            await session.flush()
        return str(version.id)

    async def active_document_embeddings(
        self, source_name: str
    ) -> dict[str, CachedDocumentEmbedding]:
        async with self._session_factory() as session:
            passages = (
                await session.execute(
                    select(Passage)
                    .join(SourceVersion, SourceVersion.id == Passage.source_version_id)
                    .where(
                        SourceVersion.source_name == source_name,
                        SourceVersion.is_active.is_(True),
                        Passage.is_active.is_(True),
                    )
                )
            ).scalars().all()
        return {
            passage.canonical_key: CachedDocumentEmbedding(
                content_hash=str(passage.passage_metadata.get("content_hash", "")),
                embedding=list(passage.embedding),
            )
            for passage in passages
        }

    async def stage_corpus(
        self,
        *,
        version_id: str,
        corpus: ParsedCorpus,
        embeddings: dict[str, list[float]],
    ) -> None:
        version_uuid = _uuid(version_id, field="source version")
        if corpus.source_version_id != version_id:
            raise ValueError("corpus source version does not match staged version")

        async with self._session_factory.begin() as session:
            version = await session.scalar(
                select(SourceVersion)
                .where(SourceVersion.id == version_uuid)
                .with_for_update()
            )
            if version is None or version.status != "staged" or version.is_active:
                raise VersionStateError("source version is not staged")

            for rule in corpus.rules:
                session.add(
                    RuleSection(
                        source_version_id=version_uuid,
                        rule_number=rule.rule_number,
                        section_heading=rule.section_heading,
                        parent_rule=rule.parent_rule,
                        previous_rule=rule.previous_rule,
                        next_rule=rule.next_rule,
                        effective_date=rule.effective_date,
                        text=rule.text,
                    )
                )
            for entry in corpus.glossary:
                session.add(
                    GlossaryEntry(
                        source_version_id=version_uuid,
                        term=entry.term,
                        effective_date=entry.effective_date,
                        text=entry.text,
                    )
                )
            for parsed_card in corpus.cards:
                card = Card(
                    oracle_id=_uuid(parsed_card.oracle_id, field="oracle ID"),
                    source_version_id=version_uuid,
                    representative_printing_id=_uuid(
                        parsed_card.representative_printing_id,
                        field="representative printing ID",
                    ),
                    name=parsed_card.name,
                    normalized_name=parsed_card.name.casefold(),
                    layout=parsed_card.layout,
                    document_text=parsed_card.document_text,
                )
                card.faces = [
                    CardFace(
                        position=face.position,
                        name=face.name,
                        oracle_text=face.oracle_text,
                    )
                    for face in parsed_card.faces
                ]
                card.aliases = [
                    CardAlias(alias=alias, normalized_alias=alias.casefold())
                    for alias in parsed_card.aliases
                ]
                session.add(card)
            for parsed_ruling in corpus.rulings:
                session.add(
                    Ruling(
                        source_version_id=version_uuid,
                        oracle_id=_uuid(parsed_ruling.oracle_id, field="ruling oracle ID"),
                        published_at=parsed_ruling.published_at,
                        source=parsed_ruling.source,
                        attribution=parsed_ruling.attribution,
                        comment=parsed_ruling.comment,
                    )
                )
            for document in corpus.documents:
                embedding = embeddings.get(document.canonical_key)
                if embedding is None:
                    raise ValueError(f"missing embedding for {document.canonical_key}")
                metadata = {**document.metadata, "content_hash": document.content_hash}
                session.add(
                    Passage(
                        source_version_id=version_uuid,
                        document_type=document.document_type,
                        canonical_key=document.canonical_key,
                        text=document.text,
                        passage_metadata=metadata,
                        search_vector=func.to_tsvector("english", document.text),
                        embedding=embedding,
                        is_active=False,
                    )
                )

            effective_dates = [
                *(rule.effective_date for rule in corpus.rules),
                *(entry.effective_date for entry in corpus.glossary),
            ]
            if effective_dates:
                version.effective_date = max(effective_dates)

    async def validate_staged(
        self, version_id: str, minimum_record_count: int
    ) -> ValidationMetrics:
        version_uuid = _uuid(version_id, field="source version")
        active_card = (
            select(Card.id)
            .join(SourceVersion, SourceVersion.id == Card.source_version_id)
            .where(
                Card.oracle_id == Ruling.oracle_id,
                SourceVersion.is_active.is_(True),
            )
        )
        async with self._session_factory() as session:
            record_count = int(
                await session.scalar(
                    select(func.count(Passage.id)).where(
                        Passage.source_version_id == version_uuid
                    )
                )
                or 0
            )
            broken_relationships = int(
                await session.scalar(
                    select(func.count(Ruling.id)).where(
                        Ruling.source_version_id == version_uuid,
                        ~exists(active_card),
                    )
                )
                or 0
            )
        return ValidationMetrics(
            record_count=record_count,
            minimum_record_count=minimum_record_count,
            duplicate_count=0,
            missing_identity_count=0,
            broken_relationship_count=broken_relationships,
        )

    async def activate(self, source_name: str, version_id: str) -> None:
        await self._versions.activate_atomically(
            ActivationCandidate(
                source_name=source_name,
                version_id=version_id,
                metrics=ValidationMetrics(1, 0, 0, 0, 0),
            )
        )

    async def mark_failed(self, version_id: str, category: str) -> None:
        version_uuid = _uuid(version_id, field="source version")
        async with self._session_factory.begin() as session:
            await session.execute(
                update(SourceVersion)
                .where(SourceVersion.id == version_uuid, SourceVersion.is_active.is_(False))
                .values(status="failed")
            )
