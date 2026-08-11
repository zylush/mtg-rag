from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping


class ScryfallParseError(ValueError):
    """Raised when required bulk-data fields are invalid."""


@dataclass(frozen=True)
class ParsedCardFace:
    position: int
    name: str
    oracle_text: str


@dataclass(frozen=True)
class ParsedOracleCard:
    oracle_id: str
    representative_printing_id: str
    name: str
    layout: str
    faces: tuple[ParsedCardFace, ...]
    aliases: tuple[str, ...]
    document_text: str


@dataclass(frozen=True)
class ParsedRuling:
    oracle_id: str
    published_at: date
    source: str
    attribution: str
    comment: str


def _release_date(card: Mapping[str, Any]) -> str:
    value = card.get("released_at")
    return value if isinstance(value, str) else "0000-00-00"


def _required_string(item: Mapping[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ScryfallParseError(f"missing required field: {field}")
    return value.strip()


def _faces(card: Mapping[str, Any]) -> tuple[ParsedCardFace, ...]:
    raw_faces = card.get("card_faces")
    if isinstance(raw_faces, list) and raw_faces:
        return tuple(
            ParsedCardFace(
                position=index,
                name=_required_string(face, "name"),
                oracle_text=str(face.get("oracle_text") or "").strip(),
            )
            for index, face in enumerate(raw_faces)
            if isinstance(face, Mapping)
        )
    return (
        ParsedCardFace(
            position=0,
            name=_required_string(card, "name"),
            oracle_text=str(card.get("oracle_text") or "").strip(),
        ),
    )


def parse_oracle_cards(cards: Iterable[Mapping[str, Any]]) -> tuple[ParsedOracleCard, ...]:
    """Normalize one English, paper card document per Oracle identity."""
    by_oracle_id: dict[str, Mapping[str, Any]] = {}
    for card in cards:
        if card.get("lang") != "en" or card.get("digital") is True:
            continue
        oracle_id = _required_string(card, "oracle_id")
        existing = by_oracle_id.get(oracle_id)
        if existing is None or _release_date(card) > _release_date(existing):
            by_oracle_id[oracle_id] = card

    parsed: list[ParsedOracleCard] = []
    for oracle_id in sorted(by_oracle_id):
        card = by_oracle_id[oracle_id]
        faces = _faces(card)
        aliases = tuple(dict.fromkeys(face.name for face in faces))
        parts = [f"{face.name}\n{face.oracle_text}".strip() for face in faces]
        parsed.append(
            ParsedOracleCard(
                oracle_id=oracle_id,
                representative_printing_id=_required_string(card, "id"),
                name=_required_string(card, "name"),
                layout=str(card.get("layout") or "normal"),
                faces=faces,
                aliases=aliases,
                document_text="\n\n".join(parts),
            )
        )
    return tuple(parsed)


def parse_rulings(rulings: Iterable[Mapping[str, Any]]) -> tuple[ParsedRuling, ...]:
    parsed: list[ParsedRuling] = []
    attribution = {"wotc": "Wizards of the Coast", "scryfall": "Scryfall"}
    priority = {"wotc": 0, "scryfall": 1}
    for ruling in rulings:
        source = _required_string(ruling, "source").lower()
        if source not in attribution:
            raise ScryfallParseError(f"unsupported ruling source: {source}")
        try:
            published_at = date.fromisoformat(_required_string(ruling, "published_at"))
        except ValueError as exc:
            raise ScryfallParseError("invalid published_at") from exc
        parsed.append(
            ParsedRuling(
                oracle_id=_required_string(ruling, "oracle_id"),
                published_at=published_at,
                source=source,
                attribution=attribution[source],
                comment=_required_string(ruling, "comment"),
            )
        )
    parsed.sort(key=lambda item: (priority[item.source], -item.published_at.toordinal(), item.comment))
    return tuple(parsed)

