from __future__ import annotations

import asyncio
from datetime import datetime

from google.api_core.exceptions import PreconditionFailed
from google.cloud.storage import Bucket


class GCSSnapshotStore:
    def __init__(self, bucket: Bucket) -> None:
        self._bucket = bucket

    async def put_immutable(
        self,
        *,
        source_name: str,
        fetched_at: datetime,
        sha256: str,
        payload: bytes,
        mime_type: str,
    ) -> str:
        safe_source = source_name.replace("/", "-").replace("\\", "-")
        object_name = (
            f"{safe_source}/{fetched_at:%Y/%m/%d}/{sha256}.raw"
        )
        blob = self._bucket.blob(object_name)
        blob.cache_control = "no-store"
        blob.metadata = {"sha256": sha256, "source": source_name}
        try:
            await asyncio.to_thread(
                blob.upload_from_string,
                payload,
                content_type=mime_type,
                if_generation_match=0,
            )
        except PreconditionFailed:
            # A concurrent run stored the same content-addressed object first.
            pass
        return f"gs://{self._bucket.name}/{object_name}"

