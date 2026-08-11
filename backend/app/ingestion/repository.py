from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Passage, SourceVersion
from app.ingestion.activation import ActivationCandidate


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

