from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class SourceDownloadError(RuntimeError):
    """Raised when a source download violates its security or integrity policy."""


@dataclass(frozen=True)
class DownloadPolicy:
    allowed_hosts: frozenset[str]
    allowed_mime_types: frozenset[str]
    max_bytes: int
    timeout_seconds: float


@dataclass(frozen=True)
class DownloadedSource:
    source_url: str
    effective_url: str
    mime_type: str
    payload: bytes
    sha256: str


def _validate_url(url: str, policy: DownloadPolicy) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in policy.allowed_hosts:
        raise SourceDownloadError("source URL must use an allowlisted HTTPS host")
    if parsed.username is not None or parsed.password is not None:
        raise SourceDownloadError("source URL must not contain credentials")


async def download_source(
    url: str, *, policy: DownloadPolicy, client: httpx.AsyncClient
) -> DownloadedSource:
    _validate_url(url, policy)
    try:
        async with client.stream(
            "GET", url, timeout=policy.timeout_seconds, follow_redirects=False
        ) as response:
            if response.is_redirect:
                raise SourceDownloadError("source redirects are not accepted")
            response.raise_for_status()
            _validate_url(str(response.url), policy)

            mime_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
            if mime_type not in policy.allowed_mime_types:
                raise SourceDownloadError(f"unexpected source MIME type: {mime_type or 'missing'}")

            content_length = response.headers.get("content-length")
            if content_length is not None and int(content_length) > policy.max_bytes:
                raise SourceDownloadError("source payload exceeds size limit")

            payload = bytearray()
            digest = hashlib.sha256()
            async for chunk in response.aiter_bytes():
                if len(payload) + len(chunk) > policy.max_bytes:
                    raise SourceDownloadError("source payload exceeds size limit")
                payload.extend(chunk)
                digest.update(chunk)
    except SourceDownloadError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceDownloadError("source download failed") from exc

    return DownloadedSource(
        source_url=url,
        effective_url=str(response.url),
        mime_type=mime_type,
        payload=bytes(payload),
        sha256=digest.hexdigest(),
    )

