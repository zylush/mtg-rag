from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime


class RulesParseError(ValueError):
    """Raised when a Comprehensive Rules payload violates parser invariants."""


@dataclass(frozen=True)
class ParsedRule:
    rule_number: str
    text: str
    section_heading: str
    parent_rule: str | None
    previous_rule: str | None
    next_rule: str | None
    effective_date: date
    source_version_id: str


@dataclass(frozen=True)
class ParsedGlossaryEntry:
    term: str
    text: str
    effective_date: date
    source_version_id: str


@dataclass(frozen=True)
class ParsedComprehensiveRules:
    effective_date: date
    rules: tuple[ParsedRule, ...]
    glossary: tuple[ParsedGlossaryEntry, ...]


_EFFECTIVE_DATE = re.compile(r"effective as of ([A-Z][a-z]+ \d{1,2}, \d{4})", re.IGNORECASE)
_SECTION = re.compile(r"^(\d{3})\.\s+(.+)$")
_RULE = re.compile(r"^(\d{3}\.\d+[a-z]?)(?:\.)?\s+(.+)$")


def _effective_date(text: str) -> date:
    match = _EFFECTIVE_DATE.search(text)
    if match is None:
        raise RulesParseError("missing effective date")
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").date()
    except ValueError as exc:
        raise RulesParseError("invalid effective date") from exc


def _parent_rule(rule_number: str) -> str | None:
    if rule_number[-1].isalpha():
        return rule_number[:-1]
    return rule_number.split(".", maxsplit=1)[0]


def _parse_glossary(
    lines: list[str], effective_date: date, source_version_id: str
) -> tuple[ParsedGlossaryEntry, ...]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            current.append(stripped)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    entries: list[ParsedGlossaryEntry] = []
    for block in blocks:
        if len(block) < 2:
            continue
        entries.append(
            ParsedGlossaryEntry(
                term=block[0],
                text=" ".join(block[1:]),
                effective_date=effective_date,
                source_version_id=source_version_id,
            )
        )
    return tuple(entries)


def parse_comprehensive_rules(
    text: str, *, source_version_id: str
) -> ParsedComprehensiveRules:
    """Parse rules at canonical rule/subrule boundaries and preserve rule context."""
    if not text.strip():
        raise RulesParseError("empty rules payload")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    effective = _effective_date(text)
    body, separator, glossary_text = text.rpartition("\nGlossary\n")
    if not separator:
        raise RulesParseError("missing glossary section")

    sections: dict[str, str] = {}
    raw_rules: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    active_rule_index: int | None = None

    for line in body.splitlines():
        stripped = line.strip()
        rule_match = _RULE.match(stripped)
        if rule_match:
            number, rule_text = rule_match.groups()
            if number in seen:
                raise RulesParseError(f"duplicate rule number: {number}")
            seen.add(number)
            section = sections.get(number[:3], "")
            raw_rules.append((number, rule_text, section))
            active_rule_index = len(raw_rules) - 1
            continue

        section_match = _SECTION.match(stripped)
        if section_match:
            number, heading = section_match.groups()
            sections[number] = f"{number}. {heading}"
            active_rule_index = None
            continue

        if stripped and active_rule_index is not None:
            number, current_text, section = raw_rules[active_rule_index]
            raw_rules[active_rule_index] = (number, f"{current_text} {stripped}", section)

    if not raw_rules:
        raise RulesParseError("no numbered rules found")

    rules = tuple(
        ParsedRule(
            rule_number=number,
            text=rule_text,
            section_heading=section,
            parent_rule=_parent_rule(number),
            previous_rule=raw_rules[index - 1][0] if index > 0 else None,
            next_rule=raw_rules[index + 1][0] if index + 1 < len(raw_rules) else None,
            effective_date=effective,
            source_version_id=source_version_id,
        )
        for index, (number, rule_text, section) in enumerate(raw_rules)
    )
    glossary = _parse_glossary(glossary_text.splitlines(), effective, source_version_id)
    return ParsedComprehensiveRules(effective_date=effective, rules=rules, glossary=glossary)
