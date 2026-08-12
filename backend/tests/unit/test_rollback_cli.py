from __future__ import annotations

import pytest

from app.ingestion.activation import ActivationCandidate
from app.ingestion.rollback import execute_rollback


class Repository:
    def __init__(self) -> None:
        self.source_names: list[str] = []

    async def activate_atomically(self, candidate: ActivationCandidate) -> None:
        raise AssertionError("rollback CLI must not activate an arbitrary candidate")

    async def rollback_atomically(self, source_name: str) -> str:
        self.source_names.append(source_name)
        return "previous-version"


@pytest.mark.asyncio
async def test_operator_rollback_command_uses_atomic_repository_path() -> None:
    repository = Repository()

    target = await execute_rollback(repository, "rules")

    assert target == "previous-version"
    assert repository.source_names == ["rules"]


@pytest.mark.asyncio
async def test_operator_rollback_command_rejects_unknown_sources() -> None:
    with pytest.raises(ValueError, match="source must be"):
        await execute_rollback(Repository(), "arbitrary")
