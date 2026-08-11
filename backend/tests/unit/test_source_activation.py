from dataclasses import dataclass, field

import pytest

from app.ingestion.activation import (
    ActivationCandidate,
    ActivationService,
    IngestionValidationError,
    ValidationMetrics,
)


@dataclass
class FakeVersionRepository:
    active: dict[str, str] = field(default_factory=lambda: {"rules": "rules-old"})
    previous: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    async def activate_atomically(self, candidate: ActivationCandidate) -> None:
        self.events.append(f"activate:{candidate.version_id}")
        old = self.active.get(candidate.source_name)
        if old is not None:
            self.previous[candidate.source_name] = old
        self.active[candidate.source_name] = candidate.version_id

    async def rollback_atomically(self, source_name: str) -> str:
        target = self.previous[source_name]
        self.active[source_name] = target
        self.events.append(f"rollback:{target}")
        return target


@pytest.mark.asyncio
async def test_valid_candidate_activates_only_after_all_validation_gates() -> None:
    repository = FakeVersionRepository()
    service = ActivationService(repository)
    candidate = ActivationCandidate(
        source_name="rules",
        version_id="rules-new",
        metrics=ValidationMetrics(
            record_count=100,
            minimum_record_count=90,
            duplicate_count=0,
            missing_identity_count=0,
            broken_relationship_count=0,
        ),
    )

    await service.activate(candidate)

    assert repository.active["rules"] == "rules-new"
    assert repository.previous["rules"] == "rules-old"
    assert repository.events == ["activate:rules-new"]


@pytest.mark.asyncio
async def test_failed_refresh_leaves_previous_version_active() -> None:
    repository = FakeVersionRepository()
    service = ActivationService(repository)
    candidate = ActivationCandidate(
        source_name="rules",
        version_id="rules-bad",
        metrics=ValidationMetrics(
            record_count=12,
            minimum_record_count=90,
            duplicate_count=1,
            missing_identity_count=0,
            broken_relationship_count=0,
        ),
    )

    with pytest.raises(IngestionValidationError):
        await service.activate(candidate)

    assert repository.active["rules"] == "rules-old"
    assert repository.events == []


@pytest.mark.asyncio
async def test_previous_version_can_be_rolled_back_immediately() -> None:
    repository = FakeVersionRepository(
        active={"rules": "rules-new"}, previous={"rules": "rules-old"}
    )
    service = ActivationService(repository)

    target = await service.rollback("rules")

    assert target == "rules-old"
    assert repository.active["rules"] == "rules-old"

