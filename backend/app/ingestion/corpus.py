from __future__ import annotations

import gzip
import hashlib
import io
import json
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.parse import quote

from app.ingestion.pipeline import CorpusDocument, ParsedCorpus
from app.ingestion.rules import parse_comprehensive_rules
from app.ingestion.scryfall import ScryfallParseError, parse_oracle_cards, parse_rulings


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


MAX_SCRYFALL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


def _gzip_json_lines(payload: bytes) -> Iterator[dict[str, Any]]:
    total_bytes = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            for line_number, line in enumerate(stream, start=1):
                total_bytes += len(line)
                if total_bytes > MAX_SCRYFALL_UNCOMPRESSED_BYTES:
                    raise ScryfallParseError("bulk payload exceeds uncompressed size limit")
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ScryfallParseError(
                        f"bulk JSON Lines record {line_number} is not an object"
                    )
                yield item
    except (gzip.BadGzipFile, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScryfallParseError("bulk payload is not valid gzip JSON Lines") from exc


def _json_records(payload: bytes) -> Iterable[dict[str, Any]]:
    if payload.startswith(b"\x1f\x8b"):
        return _gzip_json_lines(payload)

    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScryfallParseError("bulk payload is not valid UTF-8 JSON or JSON Lines") from exc
    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
        raise ScryfallParseError("bulk payload must contain objects")
    return decoded


def parse_rules_corpus(payload: bytes, version_id: str) -> ParsedCorpus:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("rules payload is not valid UTF-8") from exc
    parsed = parse_comprehensive_rules(text, source_version_id=version_id)
    documents: list[CorpusDocument] = []
    for rule in parsed.rules:
        body = f"{rule.rule_number}. {rule.text}"
        documents.append(
            CorpusDocument(
                canonical_key=rule.rule_number,
                document_type="rule",
                text=body,
                metadata={
                    "citation_label": f"Comprehensive Rules {rule.rule_number}",
                    "canonical_url": f"https://magic.wizards.com/en/rules#{rule.rule_number}",
                    "section_heading": rule.section_heading,
                    "parent_rule": rule.parent_rule,
                    "previous_rule": rule.previous_rule,
                    "next_rule": rule.next_rule,
                    "effective_date": rule.effective_date.isoformat(),
                },
                content_hash=_hash(body),
            )
        )
    for entry in parsed.glossary:
        key = entry.term.casefold()
        body = f"{entry.term}\n{entry.text}"
        documents.append(
            CorpusDocument(
                canonical_key=key,
                document_type="glossary",
                text=body,
                metadata={
                    "citation_label": f"Comprehensive Rules Glossary: {entry.term}",
                    "canonical_url": (
                        "https://magic.wizards.com/en/rules#glossary-" + quote(key, safe="")
                    ),
                    "effective_date": entry.effective_date.isoformat(),
                },
                content_hash=_hash(body),
            )
        )
    return ParsedCorpus(
        source_version_id=version_id,
        documents=tuple(documents),
        rules=parsed.rules,
        glossary=parsed.glossary,
        cards=(),
        rulings=(),
    )


def parse_cards_corpus(payload: bytes, version_id: str) -> ParsedCorpus:
    cards = parse_oracle_cards(_json_records(payload))
    documents = tuple(
        CorpusDocument(
            canonical_key=card.oracle_id,
            document_type="card",
            text=card.document_text,
            metadata={
                "citation_label": f"Oracle text: {card.name}",
                "canonical_url": (
                    "https://scryfall.com/search?q=" + quote(f"oracleid:{card.oracle_id}", safe="")
                ),
                "card_name": card.name,
                "layout": card.layout,
            },
            content_hash=_hash(card.document_text),
        )
        for card in cards
    )
    return ParsedCorpus(
        source_version_id=version_id,
        documents=documents,
        rules=(),
        glossary=(),
        cards=cards,
        rulings=(),
    )


def parse_rulings_corpus(payload: bytes, version_id: str) -> ParsedCorpus:
    rulings = parse_rulings(_json_records(payload))
    documents: list[CorpusDocument] = []
    for ruling in rulings:
        content_hash = _hash(ruling.comment)
        canonical_key = f"{ruling.oracle_id}:{ruling.published_at.isoformat()}:{content_hash[:16]}"
        documents.append(
            CorpusDocument(
                canonical_key=canonical_key,
                document_type="ruling",
                text=ruling.comment,
                metadata={
                    "citation_label": (
                        f"{ruling.attribution} ruling, {ruling.published_at.isoformat()}"
                    ),
                    "canonical_url": (
                        "https://scryfall.com/search?q="
                        + quote(f"oracleid:{ruling.oracle_id}", safe="")
                    ),
                    "oracle_id": ruling.oracle_id,
                    "published_at": ruling.published_at.isoformat(),
                    "source": ruling.source,
                    "attribution": ruling.attribution,
                },
                content_hash=content_hash,
            )
        )
    return ParsedCorpus(
        source_version_id=version_id,
        documents=tuple(documents),
        rules=(),
        glossary=(),
        cards=(),
        rulings=rulings,
    )
