from __future__ import annotations

import re
from dataclasses import dataclass

from app.retrieval.query import normalize_question


_RULE_REFERENCE = re.compile(r"\b\d{3}\.\d+[a-z]?\b", re.IGNORECASE)
_QUOTED_NAME = re.compile(r"[\"“]([^\"”]{2,255})[\"”]")


@dataclass(frozen=True)
class QuestionAnalysis:
    original: str
    normalized: str
    quoted_card_names: tuple[str, ...]
    rule_references: tuple[str, ...]


def analyze_question(question: str) -> QuestionAnalysis:
    normalized = normalize_question(question)
    quoted_names = tuple(
        dict.fromkeys(normalize_question(match) for match in _QUOTED_NAME.findall(question))
    )
    rule_references = tuple(
        dict.fromkeys(match.casefold() for match in _RULE_REFERENCE.findall(question))
    )
    return QuestionAnalysis(
        original=question,
        normalized=normalized,
        quoted_card_names=quoted_names,
        rule_references=rule_references,
    )

