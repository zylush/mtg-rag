from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.api.app import create_app
from app.api.auth import AuthenticatedUser
from app.api.schemas import (
    AskResponse,
    CitationResponse,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
)
from app.api.services import AppServices
from app.config import Settings


class FakeAuth:
    async def verify(self, token: str) -> AuthenticatedUser:
        if token != "valid-token":
            raise ValueError("invalid token")
        return AuthenticatedUser(firebase_uid="firebase-user-1", email="user@example.com")


class FakeAsk:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, UUID | None]] = []

    async def ask(
        self, *, user: AuthenticatedUser, question: str, conversation_id: UUID | None
    ) -> AskResponse:
        self.calls.append((user.firebase_uid, question, conversation_id))
        return AskResponse(
            conversation_id=UUID("00000000-0000-0000-0000-000000000010"),
            message_id=UUID("00000000-0000-0000-0000-000000000011"),
            answer="Flying changes how a creature can be blocked.",
            citations=[
                CitationResponse(
                    passage_id="rule-702.9",
                    claim="Flying restricts blockers.",
                    label="Comprehensive Rules 702.9",
                    url="https://magic.wizards.com/rules#702.9",
                )
            ],
            assumptions=[],
            confidence="high",
            needs_clarification=False,
            quota_remaining=19,
            cache_status="miss",
        )


class FakeConversations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID | None]] = []

    async def list(self, *, user: AuthenticatedUser) -> list[ConversationSummary]:
        self.calls.append((user.firebase_uid, None))
        return [
            ConversationSummary(
                id=UUID("00000000-0000-0000-0000-000000000010"),
                title="Flying",
                updated_at=datetime(2026, 8, 12, tzinfo=UTC),
            )
        ]

    async def get(self, *, user: AuthenticatedUser, conversation_id: UUID) -> ConversationDetail:
        self.calls.append((user.firebase_uid, conversation_id))
        return ConversationDetail(
            id=conversation_id,
            title="Flying",
            messages=[
                ConversationMessage(
                    id=UUID("00000000-0000-0000-0000-000000000020"),
                    role="user",
                    content="What is flying?",
                    created_at=datetime(2026, 8, 12, tzinfo=UTC),
                    citations=[],
                )
            ],
        )

    async def delete(self, *, user: AuthenticatedUser, conversation_id: UUID) -> None:
        self.calls.append((user.firebase_uid, conversation_id))


class FakeFeedback:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, int, str | None]] = []

    async def submit(
        self,
        *,
        user: AuthenticatedUser,
        answer_message_id: UUID,
        rating: int,
        comment: str | None,
    ) -> None:
        self.calls.append((user.firebase_uid, answer_message_id, rating, comment))


class FakeAccounts:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, *, user: AuthenticatedUser) -> None:
        self.deleted.append(user.firebase_uid)


@pytest.fixture
def services() -> AppServices:
    return AppServices(
        auth=FakeAuth(),
        ask=FakeAsk(),
        conversations=FakeConversations(),
        feedback=FakeFeedback(),
        accounts=FakeAccounts(),
    )


@pytest.fixture
def app(services: AppServices):  # type: ignore[no-untyped-def]
    settings = Settings(
        database_url="postgresql+asyncpg://mtg:mtg@localhost:5432/mtg",
        frontend_origin="https://rules.example.com",
    )
    return create_app(settings=settings, services=services)


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example.com"
    ) as test_client:
        yield test_client


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


@pytest.mark.asyncio
async def test_health_is_minimal_and_unauthenticated(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/ask"),
        ("GET", "/v1/conversations"),
        ("GET", "/v1/conversations/00000000-0000-0000-0000-000000000010"),
        ("DELETE", "/v1/conversations/00000000-0000-0000-0000-000000000010"),
        ("POST", "/v1/feedback"),
        ("DELETE", "/v1/account"),
    ],
)
async def test_every_protected_endpoint_requires_bearer_authentication(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, json={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ask_validates_question_length_before_calling_service(
    client: httpx.AsyncClient, services: AppServices
) -> None:
    response = await client.post(
        "/v1/ask", headers=auth_headers(), json={"question": "x" * 2001}
    )

    assert response.status_code == 422
    assert services.ask.calls == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_authenticated_user_can_ask_and_receives_resolved_citations_and_quota(
    client: httpx.AsyncClient, services: AppServices
) -> None:
    response = await client.post(
        "/v1/ask", headers=auth_headers(), json={"question": "What is flying?"}
    )

    assert response.status_code == 200
    assert response.json()["quota_remaining"] == 19
    assert response.json()["citations"][0]["url"].endswith("#702.9")
    assert services.ask.calls == [("firebase-user-1", "What is flying?", None)]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_history_operations_are_scoped_with_authenticated_identity(
    client: httpx.AsyncClient, services: AppServices
) -> None:
    conversation_id = "00000000-0000-0000-0000-000000000010"

    listed = await client.get("/v1/conversations", headers=auth_headers())
    detail = await client.get(f"/v1/conversations/{conversation_id}", headers=auth_headers())
    deleted = await client.delete(f"/v1/conversations/{conversation_id}", headers=auth_headers())

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert deleted.status_code == 204
    assert services.conversations.calls == [  # type: ignore[attr-defined]
        ("firebase-user-1", None),
        ("firebase-user-1", UUID(conversation_id)),
        ("firebase-user-1", UUID(conversation_id)),
    ]


@pytest.mark.asyncio
async def test_feedback_and_account_deletion_use_authenticated_identity(
    client: httpx.AsyncClient, services: AppServices
) -> None:
    message_id = "00000000-0000-0000-0000-000000000011"
    feedback = await client.post(
        "/v1/feedback",
        headers=auth_headers(),
        json={"answer_message_id": message_id, "rating": 1, "comment": "Helpful"},
    )
    account = await client.delete("/v1/account", headers=auth_headers())

    assert feedback.status_code == 204
    assert account.status_code == 204
    assert services.feedback.calls == [  # type: ignore[attr-defined]
        ("firebase-user-1", UUID(message_id), 1, "Helpful")
    ]
    assert services.accounts.deleted == ["firebase-user-1"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_cors_allows_only_configured_frontend_origin(client: httpx.AsyncClient) -> None:
    allowed = await client.options(
        "/v1/ask",
        headers={
            "Origin": "https://rules.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    denied = await client.options(
        "/v1/ask",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "https://rules.example.com"
    assert "access-control-allow-origin" not in denied.headers

