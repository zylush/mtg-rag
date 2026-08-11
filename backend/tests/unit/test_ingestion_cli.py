from __future__ import annotations

import json

import httpx
import pytest

from app.ingestion.cli import (
    SourceDiscoveryError,
    build_source_jobs,
    discover_source_urls,
    refresh_all,
)


@pytest.mark.asyncio
async def test_discovers_current_allowlisted_wotc_and_scryfall_sources() -> None:
    rules_url = "https://media.wizards.com/2026/downloads/MagicCompRules%2020260807.txt"
    cards_url = "https://data.scryfall.io/oracle-cards/oracle.jsonl.gz"
    rulings_url = "https://data.scryfall.io/rulings/rulings.jsonl.gz"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "magic.wizards.com":
            body = f'<a href="{rules_url}">TXT</a>'.encode()
            return httpx.Response(
                200, headers={"content-type": "text/html"}, content=body, request=request
            )
        body = json.dumps(
            {
                "data": [
                    {"type": "oracle_cards", "jsonl_download_uri": cards_url},
                    {"type": "rulings", "jsonl_download_uri": rulings_url},
                ]
            }
        ).encode()
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=body, request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sources = await discover_source_urls(client)

    assert sources.rules == rules_url
    assert sources.cards == cards_url
    assert sources.rulings == rulings_url


@pytest.mark.asyncio
async def test_discovery_rejects_non_allowlisted_bulk_download_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "magic.wizards.com":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=(
                    b'<a href="https://media.wizards.com/rules/MagicCompRules.txt">TXT</a>'
                ),
                request=request,
            )
        body = json.dumps(
            {
                "data": [
                    {
                        "type": "oracle_cards",
                        "jsonl_download_uri": "https://evil.example/cards.jsonl.gz",
                    },
                    {
                        "type": "rulings",
                        "jsonl_download_uri": "https://data.scryfall.io/rulings.jsonl.gz",
                    },
                ]
            }
        ).encode()
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=body, request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceDiscoveryError, match="allowlisted"):
            await discover_source_urls(client)


def test_builds_source_jobs_in_dependency_order() -> None:
    from app.ingestion.cli import SourceURLs

    jobs = build_source_jobs(
        SourceURLs(
            rules="https://media.wizards.com/rules.txt",
            cards="https://data.scryfall.io/cards.jsonl.gz",
            rulings="https://data.scryfall.io/rulings.jsonl.gz",
        )
    )

    assert [source.name for source, _parse in jobs] == ["rules", "cards", "rulings"]
    assert [source.minimum_record_count for source, _parse in jobs] == [1000, 25000, 50000]


@pytest.mark.asyncio
async def test_refreshes_sources_sequentially_in_dependency_order() -> None:
    class RecordingPipeline:
        def __init__(self) -> None:
            self.names: list[str] = []

        async def refresh(self, source: object, *, parse: object) -> str:
            self.names.append(source.name)  # type: ignore[attr-defined]
            return source.name  # type: ignore[no-any-return, attr-defined]

    from app.ingestion.cli import SourceURLs

    pipeline = RecordingPipeline()
    results = await refresh_all(
        pipeline,  # type: ignore[arg-type]
        SourceURLs(
            rules="https://media.wizards.com/rules.txt",
            cards="https://data.scryfall.io/cards.jsonl.gz",
            rulings="https://data.scryfall.io/rulings.jsonl.gz",
        ),
    )

    assert pipeline.names == ["rules", "cards", "rulings"]
    assert results == ("rules", "cards", "rulings")
