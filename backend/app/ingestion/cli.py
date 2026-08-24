from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from google.cloud import storage  # type: ignore[import-untyped]
from openai import AsyncOpenAI
from pythonjsonlogger.json import JsonFormatter
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.ingestion.corpus import (
    parse_cards_corpus,
    parse_rules_corpus,
    parse_rulings_corpus,
)
from app.ingestion.download import (
    DownloadedSource,
    DownloadPolicy,
    SourceDownloadError,
    download_source,
)
from app.ingestion.pipeline import (
    IngestionPipeline,
    IngestionResult,
    Parser,
    SourceDefinition,
)
from app.ingestion.repository import PostgresIngestionRepository
from app.ingestion.storage import GCSSnapshotStore
from app.retrieval.embeddings import OpenAIEmbeddingAdapter

RULES_PAGE_URL = "https://magic.wizards.com/en/rules"
SCRYFALL_BULK_CATALOG_URL = "https://api.scryfall.com/bulk-data"
SOURCE_USER_AGENT = "MTG-RAG/0.1 (scheduled corpus refresh)"
SOURCE_ORDER = ("rules", "cards", "rulings")


class SourceDiscoveryError(RuntimeError):
    """Raised when an upstream catalog does not identify an approved source."""


@dataclass(frozen=True)
class SourceURLs:
    rules: str
    cards: str
    rulings: str


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attrs:
            if name.casefold() == "href" and value:
                self.hrefs.append(value)


def _approved_url(url: str, *, hosts: frozenset[str]) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SourceDiscoveryError("discovered source URL is not allowlisted HTTPS")
    return url


def _rules_url(payload: bytes) -> str:
    try:
        html = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceDiscoveryError("WotC rules page is not valid UTF-8") from exc
    collector = _LinkCollector()
    collector.feed(html)
    candidates: list[str] = []
    for href in collector.hrefs:
        candidate = urljoin(RULES_PAGE_URL, href)
        parsed = urlparse(candidate)
        if (
            parsed.hostname == "media.wizards.com"
            and parsed.path.casefold().endswith(".txt")
            and "magiccomprules" in parsed.path.casefold()
        ):
            candidates.append(candidate)
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise SourceDiscoveryError("WotC rules page must contain one Comprehensive Rules TXT")
    return _approved_url(unique[0], hosts=frozenset({"media.wizards.com"}))


def _scryfall_urls(payload: bytes) -> tuple[str, str]:
    try:
        catalog = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceDiscoveryError("Scryfall bulk catalog is invalid JSON") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise SourceDiscoveryError("Scryfall bulk catalog has an invalid schema")

    discovered: dict[str, str] = {}
    for entry in catalog["data"]:
        if not isinstance(entry, dict) or entry.get("type") not in {
            "default_cards",
            "rulings",
        }:
            continue
        download_uri = entry.get("jsonl_download_uri") or entry.get("download_uri")
        if not isinstance(download_uri, str):
            raise SourceDiscoveryError("Scryfall bulk entry has no download URL")
        discovered[str(entry["type"])] = _approved_url(
            download_uri,
            hosts=frozenset({"data.scryfall.io"}),
        )
    if set(discovered) != {"default_cards", "rulings"}:
        raise SourceDiscoveryError("Scryfall catalog is missing required bulk types")
    return discovered["default_cards"], discovered["rulings"]


async def _download_with_retry(
    url: str,
    *,
    policy: DownloadPolicy,
    client: httpx.AsyncClient,
) -> DownloadedSource:
    retrying = AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, SourceDownloadError)),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            return await download_source(url, policy=policy, client=client)
    raise RuntimeError("bounded source retry loop completed without a result")


async def discover_source_urls(client: httpx.AsyncClient) -> SourceURLs:
    rules_page = await _download_with_retry(
        RULES_PAGE_URL,
        policy=DownloadPolicy(
            allowed_hosts=frozenset({"magic.wizards.com"}),
            allowed_mime_types=frozenset({"text/html"}),
            max_bytes=5 * 1024 * 1024,
            timeout_seconds=20.0,
        ),
        client=client,
    )
    catalog = await _download_with_retry(
        SCRYFALL_BULK_CATALOG_URL,
        policy=DownloadPolicy(
            allowed_hosts=frozenset({"api.scryfall.com"}),
            allowed_mime_types=frozenset({"application/json"}),
            max_bytes=2 * 1024 * 1024,
            timeout_seconds=20.0,
        ),
        client=client,
    )
    cards, rulings = _scryfall_urls(catalog.payload)
    return SourceURLs(rules=_rules_url(rules_page.payload), cards=cards, rulings=rulings)


def build_source_jobs(urls: SourceURLs) -> tuple[tuple[SourceDefinition, Parser], ...]:
    return (
        (
            SourceDefinition(
                name="rules",
                source_type="wotc_comprehensive_rules",
                url=urls.rules,
                parser_version="rules-v1",
                schema_version="corpus-v1",
                minimum_record_count=1_000,
            ),
            parse_rules_corpus,
        ),
        (
            SourceDefinition(
                name="cards",
                source_type="scryfall_default_cards",
                url=urls.cards,
                parser_version="scryfall-cards-v2",
                schema_version="corpus-v1",
                minimum_record_count=25_000,
            ),
            parse_cards_corpus,
        ),
        (
            SourceDefinition(
                name="rulings",
                source_type="scryfall_rulings",
                url=urls.rulings,
                parser_version="scryfall-rulings-v1",
                schema_version="corpus-v1",
                minimum_record_count=50_000,
            ),
            parse_rulings_corpus,
        ),
    )


async def refresh_all(
    pipeline: IngestionPipeline,
    urls: SourceURLs,
    *,
    source_names: tuple[str, ...] = SOURCE_ORDER,
) -> tuple[IngestionResult, ...]:
    if len(source_names) != len(set(source_names)):
        raise ValueError("ingestion sources must not contain duplicates")
    unknown = set(source_names).difference(SOURCE_ORDER)
    if unknown:
        raise ValueError("unknown ingestion source")
    jobs = {source.name: (source, parser) for source, parser in build_source_jobs(urls)}
    results: list[IngestionResult] = []
    for source_name in source_names:
        source, parser = jobs[source_name]
        results.append(await pipeline.refresh(source, parse=parser))
    return tuple(results)


def _parse_sources(argv: Sequence[str] | None = None) -> tuple[str, ...]:
    parser = argparse.ArgumentParser(description="Refresh versioned MTG source corpora")
    parser.add_argument("sources", nargs="*", choices=SOURCE_ORDER)
    sources = tuple(parser.parse_args(argv).sources) or SOURCE_ORDER
    if len(sources) != len(set(sources)):
        raise ValueError("ingestion sources must not contain duplicates")
    return sources


def _source_policy(source_name: str) -> DownloadPolicy:
    policies = {
        "rules": DownloadPolicy(
            allowed_hosts=frozenset({"media.wizards.com"}),
            allowed_mime_types=frozenset({"text/plain", "application/octet-stream"}),
            max_bytes=10 * 1024 * 1024,
            timeout_seconds=60.0,
        ),
        "cards": DownloadPolicy(
            allowed_hosts=frozenset({"data.scryfall.io"}),
            allowed_mime_types=frozenset({"application/gzip", "application/json"}),
            max_bytes=128 * 1024 * 1024,
            timeout_seconds=180.0,
        ),
        "rulings": DownloadPolicy(
            allowed_hosts=frozenset({"data.scryfall.io"}),
            allowed_mime_types=frozenset({"application/gzip", "application/json"}),
            max_bytes=32 * 1024 * 1024,
            timeout_seconds=120.0,
        ),
    }
    try:
        return policies[source_name]
    except KeyError as exc:
        raise ValueError("unknown ingestion source") from exc


def _configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(source)s %(status)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


async def run_ingestion_job(
    settings: Settings | None = None,
    *,
    source_names: tuple[str, ...] = SOURCE_ORDER,
) -> tuple[IngestionResult, ...]:
    resolved_settings = settings or get_settings()
    if resolved_settings.openai_api_key is None:
        raise RuntimeError("MTG_RAG_OPENAI_API_KEY is required for ingestion")
    if not resolved_settings.gcs_snapshot_bucket:
        raise RuntimeError("MTG_RAG_GCS_SNAPSHOT_BUCKET is required for ingestion")

    _configure_logging(resolved_settings.log_level)
    logger = logging.getLogger("mtg_rag.ingestion")
    engine = create_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    openai_client = AsyncOpenAI(
        api_key=resolved_settings.openai_api_key.get_secret_value(),
        timeout=30.0,
        max_retries=2,
    )
    storage_client = storage.Client(project=resolved_settings.gcp_project_id)
    bucket = storage_client.bucket(resolved_settings.gcs_snapshot_bucket)
    headers = {
        "User-Agent": SOURCE_USER_AGENT,
        "Accept": "application/json,text/html,text/plain,application/gzip;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=False) as http_client:
            urls = await discover_source_urls(http_client)

            async def download(source: SourceDefinition) -> DownloadedSource:
                return await _download_with_retry(
                    source.url,
                    policy=_source_policy(source.name),
                    client=http_client,
                )

            pipeline = IngestionPipeline(
                repository=PostgresIngestionRepository(session_factory),
                snapshot_store=GCSSnapshotStore(bucket),
                embedding=OpenAIEmbeddingAdapter(
                    client=openai_client,
                    model=resolved_settings.openai_embedding_model,
                    dimensions=resolved_settings.embedding_dimensions,
                ),
                download=download,
            )
            results = await refresh_all(pipeline, urls, source_names=source_names)
            for source, result in zip(source_names, results, strict=True):
                logger.info(
                    "source refresh completed",
                    extra={
                        "source": source,
                        "status": result.status,
                        "version_id": result.version_id,
                        "new_embedding_count": result.new_embedding_count,
                    },
                )
            return results
    finally:
        storage_client.close()
        await openai_client.close()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run_ingestion_job(source_names=_parse_sources(sys.argv[1:])))
    except Exception:
        logging.getLogger("mtg_rag.ingestion").exception("ingestion job failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
