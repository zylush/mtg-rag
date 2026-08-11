from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class IngestionValidationError(ValueError):
    """Raised before activation when staged source invariants fail."""


@dataclass(frozen=True)
class ValidationMetrics:
    record_count: int
    minimum_record_count: int
    duplicate_count: int
    missing_identity_count: int
    broken_relationship_count: int

    def errors(self) -> tuple[str, ...]:
        failures: list[str] = []
        if self.record_count < self.minimum_record_count:
            failures.append("record count below minimum")
        if self.duplicate_count:
            failures.append("duplicate records detected")
        if self.missing_identity_count:
            failures.append("missing identities detected")
        if self.broken_relationship_count:
            failures.append("broken relationships detected")
        return tuple(failures)


@dataclass(frozen=True)
class ActivationCandidate:
    source_name: str
    version_id: str
    metrics: ValidationMetrics


class VersionRepository(Protocol):
    async def activate_atomically(self, candidate: ActivationCandidate) -> None: ...

    async def rollback_atomically(self, source_name: str) -> str: ...


class ActivationService:
    def __init__(self, repository: VersionRepository) -> None:
        self._repository = repository

    async def activate(self, candidate: ActivationCandidate) -> None:
        failures = candidate.metrics.errors()
        if failures:
            raise IngestionValidationError("; ".join(failures))
        await self._repository.activate_atomically(candidate)

    async def rollback(self, source_name: str) -> str:
        return await self._repository.rollback_atomically(source_name)

