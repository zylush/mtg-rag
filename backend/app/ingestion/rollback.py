from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.ingestion.activation import ActivationService, VersionRepository
from app.ingestion.repository import PostgresVersionRepository


async def execute_rollback(repository: VersionRepository, source_name: str) -> str:
    if source_name not in {"rules", "cards", "rulings"}:
        raise ValueError("source must be rules, cards, or rulings")
    return await ActivationService(repository).rollback(source_name)


async def run(source_name: str) -> str:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        repository = PostgresVersionRepository(create_session_factory(engine))
        return await execute_rollback(repository, source_name)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atomically reactivate the preceding healthy corpus version."
    )
    parser.add_argument("source", choices=("rules", "cards", "rulings"))
    args = parser.parse_args()
    version_id = asyncio.run(run(args.source))
    print(json.dumps({"source": args.source, "active_version_id": version_id}))


if __name__ == "__main__":
    main()
