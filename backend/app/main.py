from __future__ import annotations

import firebase_admin  # type: ignore[import-untyped]
from openai import AsyncOpenAI

from app.api.app import create_app
from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.runtime import build_services

settings = get_settings()
engine = create_engine(settings.database_url)
session_factory = create_session_factory(engine)

try:
    firebase_admin.get_app()
except ValueError:
    options = {"projectId": settings.gcp_project_id} if settings.gcp_project_id else None
    firebase_admin.initialize_app(options=options)

api_key = (
    settings.openai_api_key.get_secret_value()
    if settings.openai_api_key is not None
    else "not-configured"
)
openai_client = AsyncOpenAI(
    api_key=api_key,
    timeout=30.0,
    max_retries=2,
)
services = build_services(
    settings=settings,
    session_factory=session_factory,
    openai_client=openai_client,
)
app = create_app(settings=settings, services=services)


@app.on_event("shutdown")
async def shutdown() -> None:
    await openai_client.close()
    await engine.dispose()
