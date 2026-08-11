import httpx
import pytest

from app.ingestion.download import DownloadPolicy, SourceDownloadError, download_source


@pytest.fixture
def policy() -> DownloadPolicy:
    return DownloadPolicy(
        allowed_hosts=frozenset({"data.scryfall.io", "media.wizards.com"}),
        allowed_mime_types=frozenset({"application/json", "text/plain"}),
        max_bytes=32,
        timeout_seconds=2.0,
    )


@pytest.mark.asyncio
async def test_downloader_rejects_non_https_and_unlisted_hosts_before_request(
    policy: DownloadPolicy,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"should not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceDownloadError, match="allowlisted HTTPS"):
            await download_source("http://evil.example/payload", policy=policy, client=client)

    assert called is False


@pytest.mark.asyncio
async def test_downloader_validates_mime_size_and_returns_sha256(policy: DownloadPolicy) -> None:
    payload = b'{"ok":true}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            content=payload,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await download_source(
            "https://data.scryfall.io/oracle.json", policy=policy, client=client
        )

    assert result.payload == payload
    assert result.mime_type == "application/json"
    assert result.sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef04513da31"


@pytest.mark.asyncio
async def test_downloader_rejects_payload_that_exceeds_streaming_limit(
    policy: DownloadPolicy,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"x" * 33,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceDownloadError, match="size limit"):
            await download_source(
                "https://data.scryfall.io/oracle.json", policy=policy, client=client
            )


@pytest.mark.asyncio
async def test_downloader_rejects_unexpected_mime_type(policy: DownloadPolicy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"not bulk data",
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceDownloadError, match="MIME"):
            await download_source(
                "https://data.scryfall.io/oracle.json", policy=policy, client=client
            )

