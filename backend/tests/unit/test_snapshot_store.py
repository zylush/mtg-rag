from datetime import UTC, datetime

import pytest

from app.ingestion.storage import GCSSnapshotStore


class FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cache_control: str | None = None
        self.metadata: dict[str, str] | None = None
        self.calls: list[dict[str, object]] = []

    def upload_from_string(self, payload: bytes, **kwargs: object) -> None:
        self.calls.append({"payload": payload, **kwargs})


class FakeBucket:
    def __init__(self) -> None:
        self.created: list[FakeBlob] = []
        self.name = "mtg-snapshots"

    def blob(self, name: str) -> FakeBlob:
        blob = FakeBlob(name)
        self.created.append(blob)
        return blob


@pytest.mark.asyncio
async def test_gcs_snapshot_path_and_generation_precondition_are_immutable() -> None:
    bucket = FakeBucket()
    store = GCSSnapshotStore(bucket)  # type: ignore[arg-type]

    uri = await store.put_immutable(
        source_name="rules",
        fetched_at=datetime(2026, 8, 12, 18, 0, tzinfo=UTC),
        sha256="abc123",
        payload=b"rules",
        mime_type="text/plain",
    )

    blob = bucket.created[0]
    assert blob.name == "rules/2026/08/12/abc123.raw"
    assert blob.calls == [
        {
            "payload": b"rules",
            "content_type": "text/plain",
            "if_generation_match": 0,
        }
    ]
    assert blob.cache_control == "no-store"
    assert blob.metadata == {"sha256": "abc123", "source": "rules"}
    assert uri == "gs://mtg-snapshots/rules/2026/08/12/abc123.raw"

