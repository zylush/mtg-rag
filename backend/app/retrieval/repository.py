from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Float,
    Integer,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from app.db.models import Card, CardAlias, CardFace, Passage, SourceVersion
from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import QuestionAnalysis
from app.retrieval.service import RetrievalCandidate

_LEXICAL_TERM = re.compile(r"[0-9a-z]+(?:[.'/-][0-9a-z]+)*", re.IGNORECASE)
_RULE_REFERENCE = re.compile(r"\b\d{3}\.\d+[a-z]?\b", re.IGNORECASE)
_RULE_SECTION_REFERENCE = re.compile(r"\brules?\s+(\d{3})(?!\.)\b", re.IGNORECASE)
_SUBRULE_KEY = re.compile(r"^(\d{3}\.\d+)[a-z]$", re.IGNORECASE)
_MAX_LEXICAL_FALLBACK_TERMS = 12
_MAX_CURRENT_LEXICAL_TERMS = 8
_MAX_PRIOR_USER_LEXICAL_TERMS = 4
_MAX_LEXICAL_ANCHOR_CLAUSES = 4
_LEXICAL_COVERAGE_CANDIDATE_LIMIT = 32
_MAX_PARENT_CONTEXT_COVERAGE_TERMS = 2
_MAX_CARD_ALIAS_CANDIDATES = 96
_MAX_CARD_ALIAS_TERMS = 8
_MAX_CARD_ALIAS_SEGMENT_TERMS = 12
_MAX_GLOSSARY_KEY_CANDIDATES = 128
_MAX_GLOSSARY_KEY_TERMS = 5
_MAX_GLOSSARY_SEGMENT_TERMS = 24
_MAX_RULE_PARENT_SUPPLEMENTS = 4
_VECTOR_CANDIDATE_MULTIPLIER = 5
_MAX_LINKED_RULE_SECTIONS = 4
_MAX_RULES_PER_LINKED_SECTION = 4
_MAX_PROTECTED_LINKED_RULES = 2
_CONTEXTUAL_SECTION_LEXICAL_WEIGHT = 0.01
_GLOSSARY_QUERY_ALIASES = {
    "dfc": "double-faced cards",
    "mdfc": "modal double-faced cards",
    "sba": "state-based actions",
}
_LEXICAL_QUERY_ALIASES = {
    "copy": "copiable",
    "zero": "0",
}
_NONBATTLEFIELD_ZONE_TERMS = frozenset({"command", "exile", "graveyard", "hand", "library"})
_ORACLE_ABILITY_SUFFIX = re.compile(r"\s*(?:\(|\u2013|\u2014|--).*")
_DOMAIN_LANGUAGE_REWRITES = (
    (
        re.compile(
            r"\blayer\b.{0,40}\badds?\b.{0,40}\bremoves?\b.{0,20}\babilities\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "layer 6 ability-adding keyword counters ability-removing",
    ),
    (
        re.compile(
            r"\bcreature\b.{0,30}\blethal\b.{0,20}\bmarked\s+damage\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "toughness damage marked greater equal lethal destroyed",
    ),
    (
        re.compile(
            r"\bdouble-faced\s+cards?\b.{0,60}\bhidden\s+zones?\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "double-faced cards hidden zones indistinguishable",
    ),
    (
        re.compile(
            r"\bcreature\s+with\s+reach\b.{0,30}\bblock\s+it\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "flying blocked except creatures reach",
    ),
    (
        re.compile(
            r"\bwhich\s+face\b.{0,40}\bsupplies?\b.{0,30}"
            r"\btransformed\s+permanent\b.{0,30}\bcharacteristics\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "nonmodal double-faced permanent back face up only characteristics",
    ),
    (
        re.compile(
            r"\b(?:(?:my|a|the)\s+)?(?:creature\s+)?token\s+"
            r"(?:was\s+)?(?:put|moved)\s+into\s+"
            r"(?:(?:my|a|the)\s+)?"
            r"(?:command(?:\s+zone)?|exile|graveyard|hand|library)\b",
            re.IGNORECASE,
        ),
        "token zone ceases exist",
    ),
    (
        re.compile(
            r"\bplayers?\s+with\s+(?:zero|0)\s+life\b",
            re.IGNORECASE,
        ),
        "state-based actions player has 0 less life loses game",
    ),
    (
        re.compile(
            r"\bwhere\b.{0,60}\blayer\b.{0,60}"
            r"\bcontrol(?:-changing)?\s+effects?\b.{0,30}\bappl(?:y|ied)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "layer 2 control-changing effects applied",
    ),
    (
        re.compile(
            r"\b(?:in\s+)?which\s+layer\b.{0,80}\bcopy\s+effects?\s+"
            r"(?:are\s+)?applied\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "layer rules effects modify copiable values",
    ),
    (
        re.compile(
            r"\b(?:how\s+(?:can|do)\s+(?:i|you)\s+)?identify\s+"
            r"(?:a\s+)?replacement\s+effect\b",
            re.IGNORECASE,
        ),
        "replacement effects watch event replace",
    ),
    (
        re.compile(
            r"\breplacement\s+effect\b.{0,80}\bexist\b.{0,80}\bevent\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "replacement effects exist before event occurs",
    ),
    (
        re.compile(
            r"(?:"
            r"\btransform\b.{0,80}\bpermanent\b"
            r"|\bpermanent\b.{0,40}\btransform\b"
            r")"
            r".{0,80}\binstant\b.{0,40}\bsorcery\b.{0,40}\bface\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "transform convert permanent double-faced token created instant sorcery "
        "face nothing happens",
    ),
    (
        re.compile(
            r"\ball\s+players\s+pass\b.{0,100}\b(?:object|stack)\b"
            r".{0,60}\bstack\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "players pass without actions between passing spell ability top stack resolves",
    ),
    (
        re.compile(
            r"\b(?:second\s+)?trigger(?:ed\s+abilit(?:y|ies))?\b"
            r".{0,80}\bput\b.{0,30}\bstack\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "ability triggered controller puts stack object priority topmost not card next player",
    ),
    (
        re.compile(
            r"\btriggered\s+ability\b.{0,40}\btrigger\b.{0,80}"
            r"\bpermanent\b.{0,40}\bleav(?:e|es|ing)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "triggered ability looks back time existence immediately prior event",
    ),
    (
        re.compile(
            r"\bchanges?\s+power\s+(?:and|or)\s+toughness\b",
            re.IGNORECASE,
        ),
        "power toughness changing effects",
    ),
    (
        re.compile(
            r"\blook\s+at\s+both\s+faces\s+of\s+a\s+"
            r"double-faced\s+card\b",
            re.IGNORECASE,
        ),
        "allowed look double-faced both faces card",
    ),
    (
        re.compile(r"\bcast\s+(?:it|this|that)\b", re.IGNORECASE),
        "cast spell",
    ),
    (
        re.compile(
            r"\b(?:every|all)\s+players?\s+passes?\s+priority\s+in\s+succession\b",
            re.IGNORECASE,
        ),
        "players pass succession",
    ),
    (
        re.compile(
            r"\b(?:the\s+)?(?:active\s+)?player\s+passed\s+priority\b",
            re.IGNORECASE,
        ),
        "player passes priority next player turn order receives",
    ),
    (
        re.compile(r"\bcontrol(?:-changing)?\s+effects?\b", re.IGNORECASE),
        "control-changing effects",
    ),
    (
        re.compile(
            r"\b(?:multiple|two\s+or\s+more)\s+(?:applicable\s+)?"
            r"replacement\s+effects\b",
            re.IGNORECASE,
        ),
        "replacement prevention effects attempting modify event affected "
        "controller player chooses",
    ),
    (
        re.compile(
            r"\bwording\s+identifies\s+a\s+triggered\s+ability\b",
            re.IGNORECASE,
        ),
        "written condition triggered ability",
    ),
    (
        re.compile(r"\bstack\s+zone\s+used\s+for\b", re.IGNORECASE),
        "stack spell cast physical card put ability activated triggers top",
    ),
    (
        re.compile(
            r"\border\s+do\s+objects?\s+on\s+the\s+stack\s+resolve\b",
            re.IGNORECASE,
        ),
        "each time players pass succession spell ability top stack resolves",
    ),
    (
        re.compile(r"\bafter\s+a\s+spell\s+resolves\b", re.IGNORECASE),
        "active player receives priority mana ability resolves",
    ),
    (
        re.compile(
            r"\bcreature\s+without\s+flying\s+or\s+reach\b.{0,40}\bblock\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "defending player checks restrictions condition declaration blockers illegal",
    ),
    (
        re.compile(
            r"\bsupplies\s+a\s+transformed\s+permanent\b",
            re.IGNORECASE,
        ),
        "has back permanent",
    ),
    (
        re.compile(r"\bcard\s+instruction\s+override\b", re.IGNORECASE),
        "card text precedence",
    ),
)
_LEXICAL_BOILERPLATE_TERMS = frozenset(
    {
        "a",
        "an",
        "after",
        "and",
        "before",
        "between",
        "are",
        "can",
        "current",
        "did",
        "do",
        "does",
        "give",
        "gets",
        "has",
        "have",
        "happen",
        "happened",
        "happens",
        "how",
        "i",
        "in",
        "is",
        "it",
        "may",
        "me",
        "my",
        "next",
        "now",
        "of",
        "on",
        "please",
        "question",
        "tell",
        "the",
        "then",
        "they",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)
_GENERIC_GLOSSARY_PHRASES = frozenset(
    {
        "ability",
        "card",
        "characteristics",
        "counter",
        "creature",
        "effect",
        "general",
        "instant",
        "layer",
        "permanent",
        "player",
        "spell",
        "stack",
        "zone",
    }
)
_LEXICAL_ANCHOR_GENERIC_TERMS = (
    _LEXICAL_BOILERPLATE_TERMS
    | _GENERIC_GLOSSARY_PHRASES
    | frozenset(
        {
            "applied",
            "applies",
            "apply",
            "correction",
            "corrected",
            "effects",
            "general",
            "get",
            "gets",
            "if",
            "instruction",
            "instructions",
            "now",
            "or",
            "oracle",
            "rules",
            "text",
            "that",
            "were",
            "without",
        }
    )
)
_LEXICAL_ANCHOR_TERM_GROUPS = (
    ("token", "zone", "ceases", "exist"),
    ("token", "zone"),
    ("state-based", "actions"),
    ("player", "has", "0", "less", "life", "loses", "game"),
    ("layer", "6", "ability-adding", "keyword", "counters", "ability-removing"),
    (
        "replacement",
        "prevention",
        "effects",
        "attempting",
        "modify",
        "event",
        "affected",
        "controller",
        "player",
        "chooses",
    ),
    ("toughness", "damage", "marked", "greater", "equal", "lethal", "destroyed"),
    ("double-faced", "cards", "hidden", "zones", "indistinguishable"),
    (
        "nonmodal",
        "double-faced",
        "permanent",
        "back",
        "face",
        "up",
        "only",
        "characteristics",
    ),
    (
        "players",
        "pass",
        "without",
        "actions",
        "between",
        "passing",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ),
    ("flying", "blocked", "except", "creatures", "reach"),
    ("layer", "rules", "effects", "modify", "copiable", "values"),
    ("replacement", "effects", "watch", "event", "replace"),
    ("replacement", "effects", "exist", "before", "event", "occurs"),
    ("layer", "2", "control-changing", "effects", "applied"),
    (
        "transform",
        "convert",
        "permanent",
        "double-faced",
        "token",
        "created",
        "instant",
        "sorcery",
        "face",
        "nothing",
        "happens",
    ),
    (
        "triggered",
        "ability",
        "looks",
        "back",
        "time",
        "existence",
        "immediately",
        "prior",
        "event",
    ),
    (
        "all",
        "players",
        "pass",
        "succession",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ),
    (
        "ability",
        "triggered",
        "controller",
        "puts",
        "stack",
        "object",
        "priority",
        "topmost",
    ),
    ("allowed", "look", "double-faced", "both", "faces"),
    ("outside", "battlefield", "stack", "front", "face"),
    (
        "stack",
        "spell",
        "cast",
        "physical",
        "card",
        "put",
        "ability",
        "activated",
        "triggers",
        "top",
    ),
    ("power", "toughness", "changing", "effects"),
    ("back", "permanent", "characteristics"),
    ("modify", "replacement", "effects"),
    ("players", "choices"),
    (
        "players",
        "pass",
        "succession",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ),
    (
        "each",
        "time",
        "players",
        "pass",
        "succession",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ),
    ("active", "player", "receives", "priority", "mana", "ability", "resolves"),
    ("passes", "priority", "next", "player", "turn", "order", "receives"),
    ("whenever", "game", "checks", "state-based", "actions", "priority"),
    (
        "defending",
        "player",
        "checks",
        "restrictions",
        "condition",
        "declaration",
        "blockers",
        "illegal",
    ),
    ("spell", "resolves", "priority"),
    ("lethal", "marked", "damage"),
    ("state-based", "actions"),
    ("last", "known", "information"),
    ("modal", "double-faced", "cards"),
    ("double-faced", "cards"),
    ("replacement", "effects"),
    ("triggered", "ability"),
    ("mana", "ability"),
    ("power", "toughness"),
    ("lethal", "damage"),
    ("marked", "damage"),
    ("flying", "reach"),
    ("blockers", "declared"),
    ("card", "text", "precedence"),
    ("spell", "resolves"),
    ("pass", "succession"),
    ("control-changing", "effects"),
    ("stack", "put"),
    ("cast", "spell"),
    ("target", "spell"),
)
_LEXICAL_ANCHOR_SUPERSEDED_GROUPS: dict[tuple[str, ...], frozenset[tuple[str, ...]]] = {
    ("token", "zone", "ceases", "exist"): frozenset({("token", "zone")}),
    ("player", "has", "0", "less", "life", "loses", "game"): frozenset(
        {("state-based", "actions")}
    ),
    (
        "replacement",
        "prevention",
        "effects",
        "attempting",
        "modify",
        "event",
        "affected",
        "controller",
        "player",
        "chooses",
    ): frozenset(
        {
            ("modify", "replacement", "effects"),
            ("replacement", "effects"),
        }
    ),
    (
        "toughness",
        "damage",
        "marked",
        "greater",
        "equal",
        "lethal",
        "destroyed",
    ): frozenset(
        {
            ("lethal", "marked", "damage"),
            ("lethal", "damage"),
            ("marked", "damage"),
        }
    ),
    ("double-faced", "cards", "hidden", "zones", "indistinguishable"): frozenset(
        {("double-faced", "cards")}
    ),
    (
        "nonmodal",
        "double-faced",
        "permanent",
        "back",
        "face",
        "up",
        "only",
        "characteristics",
    ): frozenset(
        {
            ("back", "permanent", "characteristics"),
            ("double-faced", "cards"),
        }
    ),
    (
        "players",
        "pass",
        "without",
        "actions",
        "between",
        "passing",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ): frozenset(
        {
            (
                "players",
                "pass",
                "succession",
                "spell",
                "ability",
                "top",
                "stack",
                "resolves",
            ),
            ("pass", "succession"),
        }
    ),
    ("flying", "blocked", "except", "creatures", "reach"): frozenset(
        {("flying", "reach")}
    ),
    ("layer", "2", "control-changing", "effects", "applied"): frozenset(
        {("control-changing", "effects")}
    ),
    (
        "triggered",
        "ability",
        "looks",
        "back",
        "time",
        "existence",
        "immediately",
        "prior",
        "event",
    ): frozenset({("triggered", "ability")}),
    (
        "active",
        "player",
        "receives",
        "priority",
        "mana",
        "ability",
        "resolves",
    ): frozenset({("spell", "resolves", "priority"), ("spell", "resolves")}),
    (
        "each",
        "time",
        "players",
        "pass",
        "succession",
        "spell",
        "ability",
        "top",
        "stack",
        "resolves",
    ): frozenset(
        {
            (
                "players",
                "pass",
                "succession",
                "spell",
                "ability",
                "top",
                "stack",
                "resolves",
            )
        }
    ),
    ("whenever", "game", "checks", "state-based", "actions", "priority"): frozenset(
        {("state-based", "actions")}
    ),
}
_LEXICAL_PROTECTED_ANCHOR_CLAUSES = frozenset(
    " ".join(f'"{term}"' for term in group) for group in _LEXICAL_ANCHOR_TERM_GROUPS
)
_LEXICAL_PROTECTED_PARENT_TERM_GROUPS = {
    ("token", "zone", "ceases", "exist"): ("state-based", "actions"),
    ("player", "has", "0", "less", "life", "loses", "game"): (
        "state-based",
        "actions",
    ),
    (
        "toughness",
        "damage",
        "marked",
        "greater",
        "equal",
        "lethal",
        "destroyed",
    ): ("state-based", "actions"),
    ("layer", "6", "ability-adding", "keyword", "counters", "ability-removing"): (
        "series",
        "layers",
    ),
    ("flying", "blocked", "except", "creatures", "reach"): ("flying",),
}
_LEXICAL_PROTECTED_PARENT_QUERIES = {
    " ".join(f'"{term}"' for term in child): " ".join(
        f'"{term}"' for term in parent
    )
    for child, parent in _LEXICAL_PROTECTED_PARENT_TERM_GROUPS.items()
}
_CONTEXT_MARKER = re.compile(
    r"^(current question|prior user|prior assistant):[ \t]*\r?\n",
    re.IGNORECASE | re.MULTILINE,
)
_QUOTED_EVIDENCE = re.compile(r'["\u201c]([^"\u201d]+)["\u201d]')


def _to_passage(passage: Passage) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=str(passage.id),
        document_type=passage.document_type,
        citation_label=str(passage.passage_metadata.get("citation_label", passage.canonical_key)),
        canonical_url=str(passage.passage_metadata.get("canonical_url", "")),
        text=passage.text,
    )


def _whole_phrase_present(question: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", question) is not None


def _unquoted_card_alias_is_specific(question: str, alias: str) -> bool:
    if not _whole_phrase_present(question, alias):
        return False
    terms = _LEXICAL_TERM.findall(alias)
    return len(terms) > 1 or len(alias) >= 8


def _glossary_phrase_is_specific(phrase: str) -> bool:
    return phrase.casefold() not in _GENERIC_GLOSSARY_PHRASES


def _matched_glossary_phrase(question: str, phrase: str) -> str | None:
    if _whole_phrase_present(question, phrase):
        return phrase
    last_word = phrase.rsplit(" ", maxsplit=1)[-1]
    if (
        len(last_word) > 3
        and last_word.endswith("s")
        and not last_word.endswith(("ss", "us", "is"))
    ):
        singular = phrase[:-1]
        if _whole_phrase_present(question, singular):
            return singular
    elif len(last_word) > 3:
        plural = f"{phrase}s"
        if _whole_phrase_present(question, plural):
            return plural
    return None


def _expand_glossary_aliases(question: str) -> str:
    expansions = [
        phrase
        for alias, phrase in _GLOSSARY_QUERY_ALIASES.items()
        if _whole_phrase_present(question, alias)
    ]
    return " ".join((question, *expansions))


def _oracle_keyword_phrases(oracle_text: str) -> tuple[str, ...]:
    phrases: list[str] = []
    for raw_line in oracle_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _ORACLE_ABILITY_SUFFIX.sub("", line, count=1).strip()
        if heading == line and line.endswith((".", "?", "!")):
            continue
        for item in heading.split(","):
            terms = _LEXICAL_TERM.findall(item.casefold())
            if 1 <= len(terms) <= 4:
                phrases.append(" ".join(terms))
    return tuple(dict.fromkeys(phrases))


def _disjunctive_websearch_query(question: str) -> str:
    terms = tuple(dict.fromkeys(_LEXICAL_TERM.findall(question.casefold())))
    return " OR ".join(f'"{term}"' for term in terms[:_MAX_LEXICAL_FALLBACK_TERMS])


def _user_evidence_segments(question: str) -> tuple[str, tuple[str, ...]]:
    markers = tuple(_CONTEXT_MARKER.finditer(question))
    if not markers:
        return question, ()
    current: list[str] = []
    prior_user: list[str] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(question)
        evidence = question[marker.end() : end].strip()
        marker_name = marker.group(1).casefold()
        if marker_name == "current question":
            current.append(evidence)
        elif marker_name == "prior user":
            prior_user.append(evidence)
    return " ".join(current), tuple(prior_user)


def _user_evidence_text(question: str) -> str:
    current, prior_user = _user_evidence_segments(question)
    return " ".join((current, *reversed(prior_user))).strip()


def _normalized_user_evidence_segments(question: str) -> tuple[str, ...]:
    current, prior_user = _user_evidence_segments(question)
    return tuple(
        " ".join(segment.casefold().split())
        for segment in (current, *reversed(prior_user))
        if segment
    )


def _card_alias_candidates(analysis: QuestionAnalysis) -> tuple[str, ...]:
    segments = _normalized_user_evidence_segments(analysis.original)
    candidates: list[str] = []

    def add(candidate: str, *, quoted: bool = False) -> None:
        normalized = candidate.strip()
        if not normalized or len(normalized) > 255 or normalized in candidates:
            return
        terms = _LEXICAL_TERM.findall(normalized)
        if not quoted and len(terms) == 1 and len(normalized) < 8:
            return
        if len(candidates) < _MAX_CARD_ALIAS_CANDIDATES:
            candidates.append(normalized)

    for quoted_name in analysis.quoted_card_names:
        if any(_whole_phrase_present(segment, quoted_name) for segment in segments):
            add(quoted_name, quoted=True)

    for segment in segments:
        matches = tuple(_LEXICAL_TERM.finditer(segment))[:_MAX_CARD_ALIAS_SEGMENT_TERMS]
        for width in range(min(_MAX_CARD_ALIAS_TERMS, len(matches)), 0, -1):
            for start in range(0, len(matches) - width + 1):
                end = start + width - 1
                add(segment[matches[start].start() : matches[end].end()])
                if len(candidates) >= _MAX_CARD_ALIAS_CANDIDATES:
                    return tuple(candidates)
    return tuple(candidates)


def _card_alias_statement(
    analysis: QuestionAnalysis,
    *,
    limit: int,
) -> Select[tuple[str, str, str, uuid.UUID, uuid.UUID]]:
    candidates = _card_alias_candidates(analysis)
    return (
        select(
            CardAlias.alias,
            CardAlias.normalized_alias,
            Card.normalized_name,
            Card.oracle_id,
            Card.id,
        )
        .join(Card, Card.id == CardAlias.card_id)
        .join(SourceVersion, SourceVersion.id == Card.source_version_id)
        .where(
            SourceVersion.is_active.is_(True),
            CardAlias.normalized_alias.in_(candidates),
        )
        .order_by(func.length(CardAlias.normalized_alias).desc())
        .limit(limit * 3)
    )


def _glossary_key_candidates(question: str) -> tuple[str, ...]:
    segments = _normalized_user_evidence_segments(question)
    candidates: list[str] = []

    def add(candidate: str) -> None:
        normalized = candidate.strip()
        if (
            not normalized
            or len(normalized) > 255
            or normalized in candidates
            or len(candidates) >= _MAX_GLOSSARY_KEY_CANDIDATES
        ):
            return
        candidates.append(normalized)

    for segment in segments:
        matches = tuple(_LEXICAL_TERM.finditer(segment))[:_MAX_GLOSSARY_SEGMENT_TERMS]
        for width in range(min(_MAX_GLOSSARY_KEY_TERMS, len(matches)), 0, -1):
            for start in range(0, len(matches) - width + 1):
                end = start + width - 1
                candidate = segment[matches[start].start() : matches[end].end()]
                add(candidate)
                last_term = matches[end].group(0)
                if len(last_term) > 3 and last_term.endswith("s"):
                    add(candidate[:-1])
                elif len(last_term) > 3:
                    add(f"{candidate}s")
                if len(candidates) >= _MAX_GLOSSARY_KEY_CANDIDATES:
                    return tuple(candidates)
    return tuple(candidates)


def _glossary_statement(
    question: str,
    *,
    limit: int,
) -> Select[tuple[Passage]]:
    candidates = _glossary_key_candidates(question)
    return (
        select(Passage)
        .join(SourceVersion, SourceVersion.id == Passage.source_version_id)
        .where(
            SourceVersion.is_active.is_(True),
            Passage.is_active.is_(True),
            Passage.document_type == "glossary",
            Passage.canonical_key.in_(candidates),
        )
        .order_by(func.length(Passage.canonical_key).desc())
        .limit(limit * 3)
    )


async def _initial_exact_lookup_rows(
    session_factory: async_sessionmaker[AsyncSession],
    analysis: QuestionAnalysis,
    *,
    glossary_question: str,
    limit: int,
) -> tuple[list[Any], list[Passage]]:
    alias_candidates = _card_alias_candidates(analysis)
    glossary_candidates = _glossary_key_candidates(glossary_question)

    async def load_alias_rows() -> list[Any]:
        if not alias_candidates:
            return []
        async with session_factory() as session:
            return list(
                (await session.execute(_card_alias_statement(analysis, limit=limit))).all()
            )

    async def load_glossary_rows() -> list[Passage]:
        if not glossary_candidates:
            return []
        async with session_factory() as session:
            return list(
                (await session.execute(_glossary_statement(glossary_question, limit=limit)))
                .scalars()
                .all()
            )

    alias_rows, glossary_rows = await asyncio.gather(
        load_alias_rows(),
        load_glossary_rows(),
    )
    return alias_rows, glossary_rows


_PRE_PRIORITY_PROCEDURE = re.compile(
    r"\b(?:before|prior\s+to)\b.*\bpriority\b",
    re.IGNORECASE | re.DOTALL,
)


def _normalized_lexical_terms(evidence: str) -> tuple[str, ...]:
    normalized = evidence.casefold()
    domain_terms: set[str] = set()
    for pattern, replacement in _DOMAIN_LANGUAGE_REWRITES:
        if pattern.search(normalized):
            domain_terms.update(_LEXICAL_TERM.findall(replacement.casefold()))
        normalized = pattern.sub(replacement, normalized)
    terms = list(
        dict.fromkeys(
            _LEXICAL_QUERY_ALIASES.get(term, term)
            for term in _LEXICAL_TERM.findall(normalized)
            if term not in _LEXICAL_BOILERPLATE_TERMS or term in domain_terms
        )
    )
    if _PRE_PRIORITY_PROCEDURE.search(normalized):
        for term in ("whenever", "game", "state-based", "actions", "checks"):
            if term not in terms:
                terms.append(term)
    if (
        "token" in terms
        and "zone" not in terms
        and any(zone_term in terms for zone_term in _NONBATTLEFIELD_ZONE_TERMS)
    ):
        terms.append("zone")
    if "token" in terms and "zone" in terms:
        for term in ("ceases", "exist"):
            if term not in terms:
                terms.append(term)
    if "double-faced" in terms and any(
        zone_term in terms for zone_term in _NONBATTLEFIELD_ZONE_TERMS
    ):
        for term in ("outside", "battlefield", "stack", "front", "face", "characteristics"):
            if term not in terms:
                terms.append(term)
    if all(term in terms for term in ("lethal", "marked", "damage")) and "destroyed" not in terms:
        terms.append("destroyed")
    return tuple(terms)


def _informative_lexical_terms(question: str) -> tuple[str, ...]:
    current, prior_user = _user_evidence_segments(question)
    current_terms = _normalized_lexical_terms(current)
    prior_terms = tuple(
        dict.fromkeys(
            term
            for evidence in reversed(prior_user)
            for term in _normalized_lexical_terms(evidence)
            if term not in current_terms
        )
    )

    current_count = min(_MAX_CURRENT_LEXICAL_TERMS, len(current_terms))
    prior_count = min(_MAX_PRIOR_USER_LEXICAL_TERMS, len(prior_terms))
    remaining = _MAX_LEXICAL_FALLBACK_TERMS - current_count - prior_count
    current_count += min(remaining, len(current_terms) - current_count)
    remaining = _MAX_LEXICAL_FALLBACK_TERMS - current_count - prior_count
    prior_count += min(remaining, len(prior_terms) - prior_count)
    return (*current_terms[:current_count], *prior_terms[:prior_count])


def _informative_websearch_query(question: str) -> str:
    terms = _informative_lexical_terms(question)
    return " ".join(f'"{term}"' for term in terms[:_MAX_LEXICAL_FALLBACK_TERMS])


def _terms_websearch_query(terms: tuple[str, ...]) -> str:
    return " OR ".join(f'"{term}"' for term in terms[:_MAX_LEXICAL_FALLBACK_TERMS])


def _lexical_anchor_websearch_query(
    question: str,
    coverage_terms: tuple[str, ...],
) -> str:
    coverage = set(coverage_terms)
    current, prior_user = _user_evidence_segments(question)
    evidence_segments = (current, *reversed(prior_user))
    clauses: list[tuple[str, ...]] = []

    def add_clause(terms: tuple[str, ...]) -> None:
        clause = tuple(dict.fromkeys(term for term in terms if term in coverage))
        if clause and clause not in clauses and len(clauses) < _MAX_LEXICAL_ANCHOR_CLAUSES:
            clauses.append(clause)

    for evidence in evidence_segments:
        for reference in _RULE_REFERENCE.findall(evidence.casefold()):
            add_clause((reference,))
    for evidence in evidence_segments:
        for quoted in _QUOTED_EVIDENCE.findall(evidence.casefold()):
            add_clause(_normalized_lexical_terms(quoted)[:4])

    segment_terms_by_evidence = tuple(
        tuple(term for term in _normalized_lexical_terms(evidence) if term in coverage)
        for evidence in evidence_segments
    )
    consumed_by_segment: list[set[str]] = []
    matched_domain_group = False
    for segment_terms in segment_terms_by_evidence:
        consumed: set[str] = set()
        matched_groups = tuple(
            group
            for group in _LEXICAL_ANCHOR_TERM_GROUPS
            if all(term in segment_terms for term in group)
        )
        superseded_groups = frozenset(
            superseded
            for group in matched_groups
            for superseded in _LEXICAL_ANCHOR_SUPERSEDED_GROUPS.get(group, ())
        )
        for group in matched_groups:
            if group not in superseded_groups and not set(group).issubset(consumed):
                add_clause(group)
                consumed.update(group)
                matched_domain_group = True
        consumed_by_segment.append(consumed)

    if matched_domain_group:
        return " OR ".join(" ".join(f'"{term}"' for term in clause) for clause in clauses)

    for segment_terms, consumed in zip(
        segment_terms_by_evidence,
        consumed_by_segment,
        strict=True,
    ):
        specific = [
            (index, term)
            for index, term in enumerate(segment_terms)
            if term not in consumed and term not in _LEXICAL_ANCHOR_GENERIC_TERMS
        ]
        ranked = sorted(
            specific,
            key=lambda item: (
                bool(re.search(r"[0-9./-]", item[1])),
                len(item[1]),
                -item[0],
            ),
            reverse=True,
        )[:2]
        if len(ranked) == 2 or (ranked and not clauses):
            add_clause(tuple(term for _, term in sorted(ranked)))

    if not clauses:
        add_clause(coverage_terms[:1])
    return " OR ".join(" ".join(f'"{term}"' for term in clause) for clause in clauses)


def _protected_anchor_clauses(anchor_text: str) -> tuple[str, ...]:
    return tuple(
        clause
        for clause in anchor_text.split(" OR ")
        if clause in _LEXICAL_PROTECTED_ANCHOR_CLAUSES
    )


def _without_phrases(question: str, phrases: set[str]) -> str:
    result = question
    for phrase in sorted(phrases, key=len, reverse=True):
        result = re.sub(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            " ",
            result,
            flags=re.IGNORECASE,
        )
    return result


def _authority_bonus() -> ColumnElement[float]:
    return cast(
        case(
            (
                Passage.document_type.in_(("rule", "glossary")),
                0.05,
            ),
            (
                and_(
                    Passage.document_type == "ruling",
                    Passage.passage_metadata["source"].astext == "wotc",
                ),
                0.05,
            ),
            else_=0.0,
        ),
        Float,
    )


def _lexical_authority_tier() -> ColumnElement[int]:
    return cast(
        case(
            (
                Passage.document_type.in_(("rule", "glossary")),
                2,
            ),
            (
                and_(
                    Passage.document_type == "ruling",
                    Passage.passage_metadata["source"].astext == "wotc",
                ),
                1,
            ),
            else_=0,
        ),
        Integer,
    )


def _lexical_tier_condition(authority_tier: int) -> ColumnElement[bool]:
    official = Passage.document_type.in_(("rule", "glossary"))
    wotc_ruling = and_(
        Passage.document_type == "ruling",
        Passage.passage_metadata["source"].astext == "wotc",
    )
    if authority_tier == 2:
        return official
    if authority_tier == 1:
        return wotc_ruling
    if authority_tier == 0:
        return ~or_(official, wotc_ruling)
    raise ValueError("authority tier must be 0, 1, or 2")


def _lexical_coverage_weights(coverage_terms: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(range(len(coverage_terms), 0, -1))


def _lexical_coverage_score(
    coverage_terms: tuple[str, ...],
    *,
    parent_rule: Any | None = None,
) -> ColumnElement[int]:
    def term_score(term: str, weight: int, position: int) -> Any:
        passage_match = Passage.search_vector.op("@@")(func.plainto_tsquery("english", term))
        if parent_rule is None or position >= _MAX_PARENT_CONTEXT_COVERAGE_TERMS:
            return case((passage_match, weight), else_=0)
        parent_match = parent_rule.search_vector.op("@@")(func.plainto_tsquery("english", term))
        return case(
            (passage_match, weight),
            (parent_match, weight + 1),
            else_=0,
        )

    return cast(
        sum(
            (
                term_score(term, weight, position)
                for position, (term, weight) in enumerate(
                    zip(
                        coverage_terms,
                        _lexical_coverage_weights(coverage_terms),
                        strict=True,
                    )
                )
            ),
            literal(0),
        ),
        Integer,
    )


def _lexical_tier_statement(
    query: ColumnElement[Any],
    *,
    authority_tier: int,
    limit: int,
    excluded_ids: tuple[uuid.UUID, ...],
    coverage_terms: tuple[str, ...] = (),
) -> Select[tuple[Passage, int, float]]:
    relevance = func.ts_rank_cd(Passage.search_vector, query)
    coverage = _lexical_coverage_score(coverage_terms)
    order_by = (
        (coverage.desc(), relevance.desc(), Passage.canonical_key, Passage.id)
        if coverage_terms
        else (relevance.desc(), Passage.canonical_key, Passage.id)
    )
    statement = (
        select(
            Passage,
            coverage.label("coverage"),
            relevance.label("relevance"),
        )
        .where(
            Passage.is_active.is_(True),
            _lexical_tier_condition(authority_tier),
            Passage.search_vector.op("@@")(query),
        )
        .order_by(*order_by)
        .limit(limit)
    )
    if excluded_ids:
        statement = statement.where(Passage.id.notin_(excluded_ids))
    return statement


def _lexical_ranked_statement(
    query: ColumnElement[Any],
    *,
    anchor_query: ColumnElement[Any] | None = None,
    limit: int,
    coverage_terms: tuple[str, ...] = (),
) -> Select[tuple[Passage, int, float, Passage | None]]:
    candidate_query = anchor_query if anchor_query is not None else query
    anchor_relevance = func.ts_rank_cd(Passage.search_vector, candidate_query)
    anchor_order_by: list[Any] = [
        _lexical_authority_tier().desc(),
        anchor_relevance.desc(),
        Passage.canonical_key,
        Passage.id,
    ]
    lexical_anchor = (
        select(Passage.id.label("passage_id"))
        .where(
            Passage.is_active.is_(True),
            Passage.search_vector.op("@@")(candidate_query),
        )
        .order_by(*anchor_order_by)
        .limit(_LEXICAL_COVERAGE_CANDIDATE_LIMIT)
        .cte("lexical_anchor")
    )
    relevance = func.ts_rank_cd(Passage.search_vector, query)
    parent_rule = aliased(Passage, name="parent_rule")
    coverage = _lexical_coverage_score(coverage_terms, parent_rule=parent_rule)
    order_by: list[Any] = [_lexical_authority_tier().desc()]
    if coverage_terms:
        order_by.append(coverage.desc())
    order_by.extend((relevance.desc(), Passage.canonical_key, Passage.id))
    return (
        select(
            Passage,
            coverage.label("coverage"),
            relevance.label("relevance"),
            parent_rule,
        )
        .join(lexical_anchor, lexical_anchor.c.passage_id == Passage.id)
        .outerjoin(parent_rule, _parent_rule_join_condition(parent_rule))
        .where(
            Passage.is_active.is_(True),
        )
        .order_by(*order_by)
        .limit(limit)
    )


async def _ranked_lexical_rows(
    session: AsyncSession,
    query: ColumnElement[Any],
    *,
    anchor_query: ColumnElement[Any] | None = None,
    limit: int,
    coverage_terms: tuple[str, ...] = (),
) -> list[tuple[Passage, Passage | None, float]]:
    if limit < 1:
        return []
    ranked_rows = (
        await session.execute(
            _lexical_ranked_statement(
                query,
                anchor_query=anchor_query,
                limit=limit,
                coverage_terms=coverage_terms,
            )
        )
    ).all()
    return [
        (passage, parent_rule, float(relevance))
        for passage, _, relevance, parent_rule in ranked_rows
    ]


def _protected_lexical_rule_statement(anchor_clauses: tuple[str, ...]) -> Any:
    if not anchor_clauses:
        raise ValueError("at least one lexical anchor clause is required")
    branches = []
    for clause_index, clause in enumerate(anchor_clauses):
        clause_query = func.websearch_to_tsquery("english", clause)
        relevance = func.ts_rank_cd(Passage.search_vector, clause_query)
        branch = select(
            literal(clause_index).label("clause_index"),
            Passage.id.label("passage_id"),
        ).where(
            Passage.is_active.is_(True),
            Passage.document_type == "rule",
            Passage.search_vector.op("@@")(clause_query),
        )
        parent_clause = _LEXICAL_PROTECTED_PARENT_QUERIES.get(clause)
        if parent_clause is not None:
            protected_parent = aliased(
                Passage,
                name=f"protected_parent_{clause_index}",
            )
            parent_query = func.websearch_to_tsquery("english", parent_clause)
            branch = branch.join(
                protected_parent,
                _parent_rule_join_condition(protected_parent),
            ).where(protected_parent.search_vector.op("@@")(parent_query))
        branches.append(
            branch.order_by(relevance.desc(), Passage.canonical_key, Passage.id).limit(1)
        )
    return union_all(*branches)


def _prioritize_protected_passages(
    passages: list[Passage],
    protected_ids: tuple[str, ...],
    *,
    limit: int,
) -> list[Passage]:
    passages_by_id = {str(passage.id): passage for passage in passages}
    prioritized: list[Passage] = []
    seen_ids: set[str] = set()

    def add(passage: Passage) -> None:
        passage_id = str(passage.id)
        if passage_id not in seen_ids:
            prioritized.append(passage)
            seen_ids.add(passage_id)

    for passage_id in protected_ids:
        passage = passages_by_id.get(passage_id)
        if passage is not None and passage_id not in seen_ids:
            parent_key = getattr(passage, "canonical_key", None)
            if parent_key is not None:
                for candidate in passages:
                    if (
                        getattr(candidate, "document_type", None) == "rule"
                        and _parent_rule_key(candidate) == parent_key
                    ):
                        add(candidate)
            add(passage)
    prioritized.extend(passage for passage in passages if str(passage.id) not in seen_ids)
    return prioritized[:limit]


def _nearest_vector_candidates(
    embedding: list[float],
    *,
    limit: int,
) -> Select[tuple[uuid.UUID, float]]:
    distance = Passage.embedding.cosine_distance(embedding)
    return (
        select(
            Passage.id.label("passage_id"),
            distance.label("distance"),
        )
        .where(Passage.is_active.is_(True))
        .order_by(distance)
        .limit(limit * _VECTOR_CANDIDATE_MULTIPLIER)
    )


def _parent_rule_join_condition(parent_rule: Any) -> ColumnElement[bool]:
    return and_(
        Passage.document_type == "rule",
        Passage.canonical_key.op("~")(r"^[0-9]{3}\.[0-9]+[a-z]$"),
        parent_rule.is_active.is_(True),
        parent_rule.document_type == "rule",
        parent_rule.source_version_id == Passage.source_version_id,
        parent_rule.canonical_key
        == func.left(Passage.canonical_key, func.length(Passage.canonical_key) - 1),
    )


def _vector_ranked_statement(
    embedding: list[float],
    *,
    limit: int,
) -> Select[tuple[Passage, float, Passage | None]]:
    nearest = _nearest_vector_candidates(embedding, limit=limit).subquery(
        "nearest_vector_candidates"
    )
    relevance = (1.0 - nearest.c.distance) + _authority_bonus()
    parent_rule = aliased(Passage, name="parent_rule")
    return (
        select(Passage, relevance.label("relevance"), parent_rule)
        .join(nearest, Passage.id == nearest.c.passage_id)
        .outerjoin(parent_rule, _parent_rule_join_condition(parent_rule))
        .order_by(relevance.desc(), Passage.canonical_key, Passage.id)
        .limit(limit)
    )


def _parent_rule_key(passage: Passage) -> str | None:
    if passage.document_type != "rule":
        return None
    match = _SUBRULE_KEY.fullmatch(passage.canonical_key)
    return match.group(1) if match is not None else None


def _merge_rule_parents(
    passages: list[Passage],
    parent_candidates: list[Passage],
    *,
    limit: int,
) -> list[Passage]:
    parent_keys = {
        parent_key for passage in passages if (parent_key := _parent_rule_key(passage)) is not None
    }
    parents_by_key = {
        passage.canonical_key: passage
        for passage in passages
        if passage.canonical_key in parent_keys
    }
    for parent_candidate in parent_candidates:
        if parent_candidate.canonical_key in parent_keys:
            parents_by_key.setdefault(
                parent_candidate.canonical_key,
                parent_candidate,
            )

    expanded: list[Passage] = []
    seen_ids: set[object] = set()
    for passage in passages:
        if passage.id not in seen_ids:
            expanded.append(passage)
            seen_ids.add(passage.id)
    parent_supplements: list[Passage] = []
    for passage in passages:
        parent_key = _parent_rule_key(passage)
        parent_passage = parents_by_key.get(parent_key) if parent_key is not None else None
        if (
            parent_passage is not None
            and parent_passage.id not in seen_ids
            and len(parent_supplements) < _MAX_RULE_PARENT_SUPPLEMENTS
        ):
            parent_supplements.append(parent_passage)
            seen_ids.add(parent_passage.id)
    direct_limit = max(0, limit - len(parent_supplements))
    return [*expanded[:direct_limit], *parent_supplements]


class PostgresRetrievalRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def exact(
        self,
        analysis: QuestionAnalysis,
        *,
        limit: int,
    ) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        user_evidence = " ".join(_normalized_user_evidence_segments(analysis.original))
        glossary_question = _expand_glossary_aliases(user_evidence)
        explicit_rule_keys = {
            reference
            for reference in analysis.rule_references
            if _whole_phrase_present(user_evidence, reference)
        }
        card_keys: set[str] = set()
        matched_card_ids: set[uuid.UUID] = set()
        card_priorities: dict[str, int] = {}
        glossary_keys: set[str] = set()
        matched_glossary_phrases: dict[str, str] = {}
        protected_glossary_keys: set[str] = set()
        linked_rule_keys: set[str] = set()
        linked_rule_glossaries: dict[str, set[str]] = {}
        protected_linked_rule_keys: set[str] = set()
        linked_rule_sections: set[str] = set()
        linked_section_terms: dict[str, set[str]] = {}
        linked_section_glossaries: dict[str, set[str]] = {}
        protected_linked_sections: set[str] = set()
        matched_glossary_embeddings: dict[str, list[float]] = {}
        section_passages: list[Passage] = []
        protected_section_ids: set[str] = set()
        passage_relevance: dict[str, float] = {}
        alias_rows, glossary_rows = await _initial_exact_lookup_rows(
            self._session_factory,
            analysis,
            glossary_question=glossary_question,
            limit=limit,
        )
        for alias, normalized_alias, card_name, oracle_id, card_id in alias_rows:
            is_quoted = normalized_alias in analysis.quoted_card_names
            is_unquoted_face_alias = (
                " // " in card_name and normalized_alias != card_name and not is_quoted
            )
            if is_unquoted_face_alias:
                continue
            if not is_quoted and not _unquoted_card_alias_is_specific(analysis.original, alias):
                continue
            if _whole_phrase_present(analysis.normalized, normalized_alias):
                card_key = str(oracle_id)
                card_keys.add(card_key)
                matched_card_ids.add(card_id)
                card_priorities[card_key] = max(
                    card_priorities.get(card_key, 0),
                    len(normalized_alias),
                )

        async with self._session_factory() as session:
            if matched_card_ids:
                oracle_texts = (
                    (
                        await session.execute(
                            select(CardFace.oracle_text)
                            .where(CardFace.card_id.in_(tuple(sorted(matched_card_ids, key=str))))
                            .order_by(CardFace.card_id, CardFace.position)
                        )
                    )
                    .scalars()
                    .all()
                )
                oracle_phrases = tuple(
                    dict.fromkeys(
                        phrase
                        for oracle_text in oracle_texts
                        for phrase in _oracle_keyword_phrases(oracle_text)
                    )
                )
                if oracle_phrases:
                    glossary_question = " ".join((glossary_question, *oracle_phrases))
                    glossary_rows = list(
                        (
                            await session.execute(
                                _glossary_statement(glossary_question, limit=limit)
                            )
                        )
                        .scalars()
                        .all()
                    )
            for glossary_passage in glossary_rows:
                glossary_term = glossary_passage.canonical_key
                glossary_text = glossary_passage.text
                matched_phrase = _matched_glossary_phrase(
                    glossary_question,
                    glossary_term,
                )
                if matched_phrase is not None:
                    glossary_key = str(glossary_term)
                    glossary_keys.add(glossary_key)
                    matched_glossary_phrases[glossary_key] = matched_phrase
                    matched_glossary_embeddings[glossary_key] = list(glossary_passage.embedding)
                    for reference in _RULE_REFERENCE.findall(glossary_text):
                        linked_rule_key = reference.casefold()
                        linked_rule_keys.add(linked_rule_key)
                        linked_rule_glossaries.setdefault(
                            linked_rule_key,
                            set(),
                        ).add(glossary_key)
                    for section in _RULE_SECTION_REFERENCE.findall(glossary_text):
                        if (
                            section not in linked_rule_sections
                            and len(linked_rule_sections) >= _MAX_LINKED_RULE_SECTIONS
                        ):
                            continue
                        linked_rule_sections.add(section)
                        linked_section_terms.setdefault(section, set()).add(matched_phrase)
                        linked_section_glossaries.setdefault(section, set()).add(glossary_key)

            if glossary_keys:
                protected_glossary_keys = {
                    key
                    for key, phrase in matched_glossary_phrases.items()
                    if _glossary_phrase_is_specific(key)
                    and not any(
                        other_key != key and _whole_phrase_present(other_phrase, phrase)
                        for other_key, other_phrase in matched_glossary_phrases.items()
                    )
                }
                protected_linked_rule_keys = {
                    rule_key
                    for rule_key, glossary_sources in linked_rule_glossaries.items()
                    if glossary_sources & protected_glossary_keys
                }
                protected_linked_sections = {
                    section
                    for section, glossary_sources in linked_section_glossaries.items()
                    if glossary_sources & protected_glossary_keys
                }

            canonical_keys = explicit_rule_keys | card_keys | glossary_keys | linked_rule_keys
            if not canonical_keys:
                return []
            ranking_query_text = _disjunctive_websearch_query(glossary_question)
            ranking_query = func.websearch_to_tsquery("english", ranking_query_text)
            lexical_relevance = func.ts_rank_cd(
                Passage.search_vector,
                ranking_query,
            )
            candidate_relevance = lexical_relevance
            canonical_rows = (
                await session.execute(
                    select(Passage, candidate_relevance.label("relevance"))
                    .where(
                        Passage.is_active.is_(True),
                        Passage.canonical_key.in_(canonical_keys),
                    )
                    .order_by(Passage.canonical_key, Passage.id)
                )
            ).all()
            passages = [passage for passage, _ in canonical_rows]
            passage_relevance.update(
                {str(passage.id): float(relevance) for passage, relevance in canonical_rows}
            )
            if linked_rule_sections:
                section_queries = {
                    section: func.websearch_to_tsquery(
                        "english",
                        _disjunctive_websearch_query(
                            _without_phrases(
                                glossary_question,
                                linked_section_terms[section],
                            )
                        )
                        or ranking_query_text,
                    )
                    for section in sorted(linked_rule_sections)
                }
                section_embeddings: dict[str, list[float]] = {}
                section_lexical_weights: dict[str, float] = {}
                for section in section_queries:
                    contextual_embeddings = [
                        glossary_embedding
                        for glossary_term, glossary_embedding in matched_glossary_embeddings.items()
                        if glossary_term not in linked_section_terms[section]
                    ]
                    if contextual_embeddings:
                        section_embeddings[section] = [
                            sum(values) / len(contextual_embeddings)
                            for values in zip(*contextual_embeddings, strict=True)
                        ]
                        section_lexical_weights[section] = _CONTEXTUAL_SECTION_LEXICAL_WEIGHT
                section_relevance = case(
                    *(
                        (
                            Passage.canonical_key.like(f"{section}.%"),
                            (
                                (
                                    1.0
                                    - Passage.embedding.cosine_distance(section_embeddings[section])
                                )
                                + (
                                    func.ts_rank_cd(
                                        Passage.search_vector,
                                        section_query,
                                    )
                                    * section_lexical_weights[section]
                                )
                                if section in section_embeddings
                                else func.ts_rank_cd(
                                    Passage.search_vector,
                                    section_query,
                                )
                            ),
                        )
                        for section, section_query in section_queries.items()
                    ),
                    else_=0.0,
                )
                section_lexical_relevance = case(
                    *(
                        (
                            Passage.canonical_key.like(f"{section}.%"),
                            func.ts_rank_cd(
                                Passage.search_vector,
                                section_query,
                            ),
                        )
                        for section, section_query in section_queries.items()
                    ),
                    else_=0.0,
                )
                section_rank = func.row_number().over(
                    partition_by=func.split_part(Passage.canonical_key, ".", 1),
                    order_by=(
                        section_relevance.desc(),
                        Passage.canonical_key,
                        Passage.id,
                    ),
                )
                ranked_sections = (
                    select(
                        Passage.id.label("passage_id"),
                        section_relevance.label("relevance"),
                        section_lexical_relevance.label("lexical_relevance"),
                        section_rank.label("section_rank"),
                    )
                    .where(
                        Passage.is_active.is_(True),
                        Passage.document_type == "rule",
                        or_(
                            *(
                                Passage.canonical_key.like(f"{section}.%")
                                for section in section_queries
                            )
                        ),
                    )
                    .subquery()
                )
                section_rows = (
                    await session.execute(
                        select(
                            Passage,
                            ranked_sections.c.relevance,
                            ranked_sections.c.lexical_relevance,
                        )
                        .join(
                            ranked_sections,
                            Passage.id == ranked_sections.c.passage_id,
                        )
                        .where(ranked_sections.c.section_rank <= _MAX_RULES_PER_LINKED_SECTION)
                        .order_by(
                            ranked_sections.c.relevance.desc(),
                            Passage.canonical_key,
                            Passage.id,
                        )
                    )
                ).all()
                section_passages = [passage for passage, _, _ in section_rows]
                protected_section_ids = set()
                seen_protected_sections: set[str] = set()
                for passage, _, lexical_relevance in section_rows:
                    section = passage.canonical_key.split(".", maxsplit=1)[0]
                    if (
                        float(lexical_relevance) > 0
                        and section in protected_linked_sections
                        and section not in seen_protected_sections
                    ):
                        protected_section_ids.add(str(passage.id))
                        seen_protected_sections.add(section)
                passage_relevance.update(
                    {
                        str(passage.id): max(
                            passage_relevance.get(str(passage.id), 0.0),
                            float(relevance),
                        )
                        for passage, relevance, _ in section_rows
                    }
                )
        passages.sort(key=lambda passage: (passage.canonical_key, passage.id))
        critical = [
            passage
            for passage in passages
            if passage.canonical_key in explicit_rule_keys or passage.canonical_key in card_keys
        ]
        explicit_rule_priorities = {
            rule_key: priority for priority, rule_key in enumerate(analysis.rule_references)
        }
        critical.sort(
            key=lambda passage: (
                0 if passage.canonical_key in explicit_rule_priorities else 1,
                explicit_rule_priorities.get(passage.canonical_key, 0),
                -card_priorities.get(passage.canonical_key, 0),
                passage.canonical_key,
                passage.id,
            )
        )
        glossaries = [
            passage
            for passage in passages
            if passage.canonical_key in glossary_keys and passage not in critical
        ]
        glossaries.sort(
            key=lambda passage: (
                -len(passage.canonical_key),
                -passage_relevance.get(str(passage.id), 0.0),
                passage.canonical_key,
                passage.id,
            )
        )
        linked_rules = [
            passage
            for passage in passages
            if passage.canonical_key in linked_rule_keys
            and passage not in critical
            and passage not in glossaries
        ]
        selected_ids = {passage.id for passage in [*critical, *glossaries, *linked_rules]}
        section_rules = [passage for passage in section_passages if passage.id not in selected_ids]
        linked_rules.sort(
            key=lambda passage: (
                passage.canonical_key not in protected_linked_rule_keys,
                -passage_relevance.get(str(passage.id), 0.0),
                passage.canonical_key,
                passage.id,
            )
        )
        protected_linked_rules = [
            passage
            for passage in linked_rules
            if passage.canonical_key in protected_linked_rule_keys
        ][:_MAX_PROTECTED_LINKED_RULES]
        unprotected_linked_rules = [
            passage for passage in linked_rules if passage not in protected_linked_rules
        ]
        section_priority = {
            section: priority
            for priority, section in enumerate(
                sorted(
                    linked_rule_sections,
                    key=lambda section: (
                        -max(len(term) for term in linked_section_terms[section]),
                        section,
                    ),
                )
            )
        }
        section_rules.sort(
            key=lambda passage: (
                section_priority.get(
                    passage.canonical_key.split(".", maxsplit=1)[0],
                    len(section_priority),
                ),
                -passage_relevance.get(str(passage.id), 0.0),
                passage.canonical_key,
                passage.id,
            )
        )
        other = [
            passage
            for passage in passages
            if passage not in critical and passage not in glossaries and passage not in linked_rules
        ]
        passages = [
            *critical,
            *glossaries[:1],
            *protected_linked_rules,
            *section_rules,
            *unprotected_linked_rules,
            *glossaries[1:],
            *other,
        ]
        critical_ids = {passage.id for passage in critical}
        linked_rule_ids = {passage.id for passage in linked_rules}
        protected_linked_rule_ids = {passage.id for passage in protected_linked_rules}
        section_rule_ids = {passage.id for passage in section_rules}
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source=(
                    "exact"
                    if passage.id in critical_ids
                    else "linked_rule"
                    if passage.id in linked_rule_ids
                    else "linked_section"
                    if passage.id in section_rule_ids
                    else "glossary"
                ),
                exact=(
                    passage.id in critical_ids
                    or passage.id in protected_linked_rule_ids
                    or str(passage.id) in protected_section_ids
                    or passage.canonical_key in protected_glossary_keys
                ),
            )
            for rank, passage in enumerate(passages[:limit], start=1)
        ]

    async def lexical(self, question: str, *, limit: int) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        coverage_terms = _informative_lexical_terms(question)
        query_text = _terms_websearch_query(coverage_terms) or question
        query = func.websearch_to_tsquery("english", query_text)
        anchor_text = _lexical_anchor_websearch_query(question, coverage_terms) or query_text
        anchor_query = func.websearch_to_tsquery("english", anchor_text)
        has_anchor_query = anchor_text != query_text
        anchor_clauses = _protected_anchor_clauses(anchor_text)
        protect_anchored_rules = bool(anchor_clauses)
        protected_rule_ids: tuple[str, ...] = ()
        async with self._session_factory() as session:
            passages = await _ranked_lexical_rows(
                session,
                query,
                anchor_query=anchor_query,
                limit=limit,
                coverage_terms=coverage_terms,
            )
            if not passages and has_anchor_query:
                protect_anchored_rules = False
                passages = await _ranked_lexical_rows(
                    session,
                    query,
                    anchor_query=query,
                    limit=limit,
                    coverage_terms=coverage_terms,
                )
            elif anchor_clauses:
                protected_rows = (
                    await session.execute(_protected_lexical_rule_statement(anchor_clauses))
                ).all()
                protected_rule_ids = tuple(
                    str(passage_id)
                    for _, passage_id in sorted(
                        protected_rows,
                        key=lambda row: row[0],
                    )
                )
            merged_passages = _merge_rule_parents(
                [passage for passage, _, _ in passages],
                [parent_rule for _, parent_rule, _ in passages if parent_rule is not None],
                limit=limit,
            )
            ranked_passages = _prioritize_protected_passages(
                merged_passages,
                protected_rule_ids,
                limit=limit,
            )
        protected_rule_id_set = set(protected_rule_ids)
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source="lexical",
                protected=(
                    protect_anchored_rules
                    and passage.document_type == "rule"
                    and str(passage.id) in protected_rule_id_set
                ),
            )
            for rank, passage in enumerate(ranked_passages, start=1)
        ]

    async def vector(self, embedding: list[float], *, limit: int) -> list[RetrievalCandidate]:
        if limit < 1:
            return []
        async with self._session_factory() as session:
            passages = (
                await session.execute(_vector_ranked_statement(embedding, limit=limit))
            ).all()
            ranked_passages = _merge_rule_parents(
                [passage for passage, _, _ in passages],
                [parent_rule for _, _, parent_rule in passages if parent_rule is not None],
                limit=limit,
            )
        return [
            RetrievalCandidate(
                passage=_to_passage(passage),
                rank=rank,
                source="vector",
            )
            for rank, passage in enumerate(ranked_passages, start=1)
        ]
