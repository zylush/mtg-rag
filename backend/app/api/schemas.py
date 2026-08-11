from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AskRequest(StrictModel):
    conversation_id: UUID | None = None
    question: str = Field(min_length=1, max_length=2000)


class CitationResponse(StrictModel):
    passage_id: str
    claim: str
    label: str
    url: str


class AskResponse(StrictModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[CitationResponse]
    assumptions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool
    quota_remaining: int = Field(ge=0)
    cache_status: Literal["exact", "semantic", "miss", "ineligible"]


class ConversationSummary(StrictModel):
    id: UUID
    title: str
    updated_at: datetime


class ConversationMessage(StrictModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    citations: list[CitationResponse]


class ConversationDetail(StrictModel):
    id: UUID
    title: str
    messages: list[ConversationMessage]


class FeedbackRequest(StrictModel):
    answer_message_id: UUID
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=2000)

