from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Card, CardAlias, CardFace, Passage, SourceVersion
from app.retrieval.analysis import analyze_question
from app.retrieval.repository import PostgresRetrievalRepository


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _embedding(first: float) -> list[float]:
    return [first, 1.0 - first, *([0.0] * 1534)]


def _version(source_name: str, *, active: bool) -> SourceVersion:
    suffix = uuid.uuid4().hex
    return SourceVersion(
        source_name=source_name,
        source_type="fixture",
        source_url=f"https://media.wizards.com/{suffix}.txt",
        effective_date=date(2026, 8, 1),
        fetched_at=datetime.now(UTC),
        sha256=suffix.ljust(64, "0"),
        parser_version="1",
        schema_version="1",
        raw_gcs_uri=f"gs://snapshots/{suffix}",
        status="active" if active else "inactive",
        is_active=active,
        activated_at=datetime.now(UTC) if active else None,
    )


def _passage(
    *,
    source_version_id: uuid.UUID,
    document_type: str,
    canonical_key: str,
    body: str,
    first_dimension: float,
    source: str | None = None,
    active: bool = True,
) -> Passage:
    metadata = {
        "citation_label": canonical_key,
        "canonical_url": f"https://example.test/{canonical_key}",
    }
    if source is not None:
        metadata["source"] = source
    return Passage(
        source_version_id=source_version_id,
        document_type=document_type,
        canonical_key=canonical_key,
        text=body,
        passage_metadata=metadata,
        search_vector=func.to_tsvector("english", body),
        embedding=_embedding(first_dimension),
        is_active=active,
    )


@pytest.fixture
async def retrieval_fixture(session_factory):  # type: ignore[no-untyped-def]
    active_version = _version(f"retrieval-{uuid.uuid4().hex}", active=True)
    inactive_version = _version(f"inactive-{uuid.uuid4().hex}", active=False)
    oracle_id = uuid.uuid4()
    printing_id = uuid.uuid4()
    split_oracle_id = uuid.uuid4()
    bogle_oracle_id = uuid.uuid4()
    card = Card(
        oracle_id=oracle_id,
        source_version_id=active_version.id,
        representative_printing_id=printing_id,
        name="Lightning Bolt",
        normalized_name="lightning bolt",
        layout="normal",
        document_text="Lightning Bolt deals 3 damage to any target.",
    )
    split_card = Card(
        oracle_id=split_oracle_id,
        source_version_id=active_version.id,
        representative_printing_id=uuid.uuid4(),
        name="Who // What // When // Where // Why",
        normalized_name="who // what // when // where // why",
        layout="split",
        document_text="A split card used to verify safe face-name matching.",
    )
    bogle_card = Card(
        oracle_id=bogle_oracle_id,
        source_version_id=active_version.id,
        representative_printing_id=uuid.uuid4(),
        name="Slippery Bogle",
        normalized_name="slippery bogle",
        layout="normal",
        document_text="Hexproof",
    )
    async with session_factory.begin() as session:
        await session.execute(delete(SourceVersion))
        session.add_all([active_version, inactive_version])
        await session.flush()
        card.source_version_id = active_version.id
        split_card.source_version_id = active_version.id
        bogle_card.source_version_id = active_version.id
        session.add_all([card, split_card, bogle_card])
        await session.flush()
        session.add_all(
            [
                CardAlias(
                card_id=card.id,
                alias="Lightning Bolt",
                normalized_alias="lightning bolt",
                ),
                CardAlias(
                    card_id=split_card.id,
                    alias="What",
                    normalized_alias="what",
                ),
                CardAlias(
                    card_id=bogle_card.id,
                    alias="Slippery Bogle",
                    normalized_alias="slippery bogle",
                ),
                CardFace(
                    card_id=card.id,
                    position=0,
                    name="Lightning Bolt",
                    oracle_text=card.document_text,
                ),
                CardFace(
                    card_id=bogle_card.id,
                    position=0,
                    name="Slippery Bogle",
                    oracle_text="Hexproof",
                ),
            ]
        )
        passages = [
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="608.2h",
                body="The spell resolves using the last known information.",
                first_dimension=0.2,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="card",
                canonical_key=str(oracle_id),
                body=card.document_text,
                first_dimension=0.4,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="ruling",
                canonical_key="ruling-wotc",
                body="A target spell is countered when all its targets are illegal.",
                first_dimension=0.5,
                source="wotc",
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="ruling",
                canonical_key="ruling-scryfall",
                body="A target spell is countered when all its targets are illegal.",
                first_dimension=0.5,
                source="scryfall",
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="flying",
                body="Flying is an evasion ability. See rule 702.9, Flying.",
                first_dimension=1.0,
            ),
            _passage(
                source_version_id=inactive_version.id,
                document_type="glossary",
                canonical_key="inactive-best",
                body="Inactive passage must never be returned.",
                first_dimension=1.0,
                active=False,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="target",
                body=(
                    "Target. A preselected object, player, and/or zone a spell or ability "
                    "will affect. See rule 115, Targets."
                ),
                first_dimension=0.1,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="115.1",
                body="A target spell is countered when all its targets are illegal.",
                first_dimension=0.5,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="card",
                canonical_key=str(split_oracle_id),
                body=split_card.document_text,
                first_dimension=0.3,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="702.9",
                body="Flying restricts which creatures can block an attacking creature.",
                first_dimension=0.9,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="state-based actions",
                body="Game actions that happen automatically. See rule 704, State-Based Actions.",
                first_dimension=0.8,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.3",
                body="Whenever a player would get priority, the game checks state-based actions.",
                first_dimension=0.7,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.5d",
                body="If a token is in a zone other than the battlefield, it ceases to exist.",
                first_dimension=0.6,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="creature",
                body="Creature is a permanent. See rule 302, Creatures.",
                first_dimension=0.6,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="graveyard",
                body="A graveyard is a zone. See rule 404, Graveyard.",
                first_dimension=0.6,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="token",
                body="A token represents a permanent. See rule 111, Tokens.",
                first_dimension=0.6,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="block",
                body="To block is to defend in combat. See rule 509, Declare Blockers Step.",
                first_dimension=0.4,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="reach",
                body="Reach can block flying creatures. See rule 702.17, Reach.",
                first_dimension=0.4,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="702.17",
                body="Reach.",
                first_dimension=0.1,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="509.1c",
                body="The declaration of blockers must obey every blocking restriction.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="509.3d",
                body="An ability can trigger when an attacking creature becomes blocked.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="509.3f",
                body="Blocking-trigger characteristics are checked when blockers are declared.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="509.3b",
                body="An ability can trigger whenever a creature blocks.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.4",
                body="Resolution completes before applicable conditions are checked.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.5u",
                body="Players make a sector designation choice for certain creatures.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.5k",
                body="The world rule applies to certain permanents.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="704.6d",
                body="A commander variant performs additional checks.",
                first_dimension=0.95,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="player",
                body="A participant in the game. See rule 102, Players.",
                first_dimension=0.99,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="102.1",
                body="A player is one of the people in the game.",
                first_dimension=0.99,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="102.2",
                body="In a two-player game, a player's opponent is the other player.",
                first_dimension=0.98,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="102.3",
                body="In a multiplayer game, a player may have multiple opponents.",
                first_dimension=0.97,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="102.4",
                body="A spell or ability may use the word team instead of player.",
                first_dimension=0.96,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="card",
                canonical_key=str(bogle_oracle_id),
                body=bogle_card.document_text,
                first_dimension=0.5,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="glossary",
                canonical_key="hexproof",
                body="Hexproof is an ability. See rule 702.11, Hexproof.",
                first_dimension=0.5,
            ),
            _passage(
                source_version_id=active_version.id,
                document_type="rule",
                canonical_key="702.11",
                body="Hexproof restricts which opponents may target an object or player.",
                first_dimension=0.5,
            ),
        ]
        session.add_all(passages)
    return PostgresRetrievalRepository(session_factory), passages


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_finds_rule_and_unquoted_active_card_alias(retrieval_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passages = retrieval_fixture

    result = await repository.exact(
        analyze_question("How do Lightning Bolt and rule 608.2h interact?"), limit=20
    )

    assert {candidate.passage.passage_id for candidate in result} == {
        str(passages[0].id),
        str(passages[1].id),
    }
    assert all(candidate.exact for candidate in result)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_resolves_a_prior_users_cards_referenced_ability(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, _ = retrieval_fixture
    contextual_query = (
        "Current question:\nWhat is that ability?\n\n"
        "Prior user:\nSlippery Bogle has an ability I do not recognize."
    )

    result = await repository.exact(analyze_question(contextual_query), limit=20)

    assert "702.11" in {
        candidate.passage.citation_label for candidate in result
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_card_candidates_prioritize_the_longest_matched_alias(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    card_specs = [
        ("Me", uuid.UUID("00000000-0000-4000-8000-000000000001")),
        ("Black", uuid.UUID("00000000-0000-4000-8000-000000000002")),
        ("Lotus", uuid.UUID("00000000-0000-4000-8000-000000000003")),
        ("Oracle", uuid.UUID("00000000-0000-4000-8000-000000000004")),
        ("Black Lotus", uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")),
    ]
    created: list[tuple[Card, Passage]] = []
    async with session_factory.begin() as session:
        for name, oracle_id in card_specs:
            card = Card(
                oracle_id=oracle_id,
                source_version_id=source_version_id,
                representative_printing_id=uuid.uuid4(),
                name=name,
                normalized_name=name.casefold(),
                layout="normal",
                document_text=f"{name} fixture text.",
            )
            session.add(card)
            await session.flush()
            session.add(
                CardAlias(
                    card_id=card.id,
                    alias=name,
                    normalized_alias=name.casefold(),
                )
            )
            passage = _passage(
                source_version_id=source_version_id,
                document_type="card",
                canonical_key=str(oracle_id),
                body=card.document_text,
                first_dimension=0.5,
            )
            session.add(passage)
            created.append((card, passage))

    result = await repository.exact(
        analyze_question("Give me Black Lotus Oracle text."),
        limit=20,
    )

    target_id = str(created[-1][1].id)
    protected_cards = [
        candidate
        for candidate in result
        if candidate.exact and candidate.passage.document_type == "card"
    ]
    assert protected_cards[0].passage.passage_id == target_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_finds_glossary_term_mentioned_in_question(retrieval_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passages = retrieval_fixture

    result = await repository.exact(
        analyze_question("What Comprehensive Rule defines a target?"), limit=20
    )

    assert [candidate.passage.passage_id for candidate in result] == [
        str(passages[6].id),
        str(passages[7].id),
    ]
    assert [candidate.passage.document_type for candidate in result] == [
        "glossary",
        "rule",
    ]
    assert result[0].source == "glossary"
    assert result[0].exact is True
    assert result[1].source == "linked_section"
    assert result[1].exact is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_protects_the_most_specific_glossary_phrase(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    glossary_passages = [
        _passage(
            source_version_id=source_version_id,
            document_type="glossary",
            canonical_key=canonical_key,
            body=body,
            first_dimension=0.5,
        )
        for canonical_key, body in (
            ("ability", "An ability is rules text. See rule 113.1."),
            ("mana", "Mana is the primary resource. See rule 106.1."),
            (
                "mana ability",
                "A mana ability produces mana. See rule 605.1.",
            ),
        )
    ]
    linked_rules = [
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key=canonical_key,
            body=body,
            first_dimension=0.5,
        )
        for canonical_key, body in (
            ("106.1", "Mana is the primary resource of the game."),
            ("113.1", "An ability can be one of several kinds."),
            ("605.1", "Activated mana abilities meet specific criteria."),
        )
    ]
    async with session_factory.begin() as session:
        session.add_all([*glossary_passages, *linked_rules])

    result = await repository.exact(
        analyze_question("What is a mana ability?"),
        limit=20,
    )
    matched_glossaries = [
        candidate
        for candidate in result
        if candidate.passage.document_type == "glossary"
        and candidate.passage.citation_label in {"ability", "mana", "mana ability"}
    ]

    assert matched_glossaries[0].passage.citation_label == "mana ability"
    assert matched_glossaries[0].exact is True
    assert all(not candidate.exact for candidate in matched_glossaries[1:])
    linked_by_key = {
        candidate.passage.citation_label: candidate
        for candidate in result
        if candidate.passage.citation_label in {"106.1", "113.1", "605.1"}
    }
    assert linked_by_key["605.1"].exact is True
    assert linked_by_key["106.1"].exact is False
    assert linked_by_key["113.1"].exact is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_glossary_lookup_matches_singular_and_known_acronym_variants(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    glossary = _passage(
        source_version_id=passages[0].source_version_id,
        document_type="glossary",
        canonical_key="double-faced cards",
        body="Double-faced cards have two faces. See rule 712, Double-Faced Cards.",
        first_dimension=0.5,
    )
    replacement_glossary = _passage(
        source_version_id=passages[0].source_version_id,
        document_type="glossary",
        canonical_key="replacement effect",
        body="Replacement effects change events. See rule 614, Replacement Effects.",
        first_dimension=0.5,
    )
    async with session_factory.begin() as session:
        session.add_all([glossary, replacement_glossary])

    for question in (
        "Which face of a double-faced card applies?",
        "What characteristics does a DFC have in exile?",
    ):
        result = await repository.exact(
            analyze_question(question),
            limit=20,
        )

        match = next(
            candidate
            for candidate in result
            if candidate.passage.passage_id == str(glossary.id)
        )
        assert match.exact is True

    plural_result = await repository.exact(
        analyze_question("Who chooses between multiple replacement effects?"),
        limit=20,
    )
    plural_match = next(
        candidate
        for candidate in plural_result
        if candidate.passage.passage_id == str(replacement_glossary.id)
    )
    assert plural_match.exact is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_glossary_lookup_includes_its_linked_governing_rule(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.exact(analyze_question("What does flying mean?"), limit=20)

    assert [candidate.passage.passage_id for candidate in result[:2]] == [
        str(passages[4].id),
        str(passages[9].id),
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_protects_specific_links_before_broad_section_expansions(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.exact(
        analyze_question(
            "My attacking creature has flying. Can a creature with reach block it?"
        ),
        limit=20,
    )

    protected_ids = [
        candidate.passage.passage_id for candidate in result if candidate.exact
    ][:4]
    assert str(passages[9].id) in protected_ids
    assert str(passages[18].id) in protected_ids


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_glossary_lookup_expands_a_linked_rule_section_by_relevance(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.exact(
        analyze_question(
            "A token is in my graveyard when state-based actions happen. What happens?"
        ),
        limit=20,
    )

    assert str(passages[12].id) in {
        candidate.passage.passage_id for candidate in result[:6]
    }
    linked_section = next(
        candidate
        for candidate in result
        if candidate.passage.passage_id == str(passages[12].id)
    )
    assert linked_section.source == "linked_section"
    assert linked_section.exact is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generic_glossary_section_without_specific_support_is_not_protected(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, _ = retrieval_fixture

    result = await repository.exact(
        analyze_question("What happens to a player with zero life?"),
        limit=20,
    )

    generic_section = [
        candidate
        for candidate in result
        if candidate.passage.citation_label.startswith("102.")
    ]
    assert len(generic_section) == 4
    assert all(candidate.source == "linked_section" for candidate in generic_section)
    assert all(not candidate.exact for candidate in generic_section)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_specific_section_evidence_is_not_crowded_out_by_glossary_links(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    glossary = _passage(
        source_version_id=source_version_id,
        document_type="glossary",
        canonical_key="replacement effect",
        body=(
            "A replacement effect changes an event. See rules 614, Replacement "
            "Effects, including rules 614.1, 614.2, 614.4, and 614.17."
        ),
        first_dimension=0.5,
    )
    rule_bodies = {
        "614.1": "A replacement effect modifies an event.",
        "614.2": "Replacement effects apply continuously.",
        "614.4": "A replacement effect can modify a game event.",
        "614.6": (
            "A replacement effect must exist immediately before an event it would affect."
        ),
        "614.17": "Some replacement effects replace card draws.",
    }
    rules = [
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key=canonical_key,
            body=body,
            first_dimension=0.5,
        )
        for canonical_key, body in rule_bodies.items()
    ]
    async with session_factory.begin() as session:
        session.add_all([glossary, *rules])

    result = await repository.exact(
        analyze_question(
            "When must a replacement effect exist to affect an event?"
        ),
        limit=20,
    )
    protected = [
        candidate.passage.citation_label
        for candidate in result
        if candidate.exact
    ][:4]

    assert "614.6" in protected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_requires_quotes_for_split_card_face_alias(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    unquoted = await repository.exact(analyze_question("What happens next?"), limit=20)
    quoted = await repository.exact(analyze_question('What does "What" do?'), limit=20)

    split_passage_id = str(passages[8].id)
    assert split_passage_id not in {
        candidate.passage.passage_id for candidate in unquoted
    }
    assert split_passage_id in {
        candidate.passage.passage_id for candidate in quoted
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_exact_lookup_requires_quotes_for_lowercase_common_card_alias(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    oracle_id = uuid.uuid4()
    card = Card(
        oracle_id=oracle_id,
        source_version_id=source_version_id,
        representative_printing_id=uuid.uuid4(),
        name="Copy",
        normalized_name="copy",
        layout="normal",
        document_text="Copy fixture text.",
    )
    passage = _passage(
        source_version_id=source_version_id,
        document_type="card",
        canonical_key=str(oracle_id),
        body=card.document_text,
        first_dimension=0.5,
    )
    async with session_factory.begin() as session:
        session.add(card)
        await session.flush()
        session.add(
            CardAlias(
                card_id=card.id,
                alias="Copy",
                normalized_alias="copy",
            )
        )
        session.add(passage)

    unquoted = await repository.exact(
        analyze_question("Can I copy this effect?"),
        limit=20,
    )
    quoted = await repository.exact(
        analyze_question('What does "Copy" do?'),
        limit=20,
    )

    passage_id = str(passage.id)
    assert passage_id not in {
        candidate.passage.passage_id for candidate in unquoted
    }
    assert passage_id in {
        candidate.passage.passage_id for candidate in quoted
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("question", "expected_key", "expected_body"),
    [
        (
            "Who chooses between multiple applicable replacement effects?",
            "616.1",
            (
                "If two or more replacement effects modify an event, the affected "
                "player chooses one to apply."
            ),
        ),
        (
            "What wording identifies a triggered ability?",
            "603.1",
            (
                "Triggered abilities have a trigger condition and an effect and are "
                "written with when, whenever, or at."
            ),
        ),
        (
            "What happens when every player passes priority in succession?",
            "117.4",
            "If all players pass in succession, the top stack object resolves.",
        ),
        (
            "What is the stack zone used for?",
            "405.1",
            "When a spell is cast, its physical card is put on the stack.",
        ),
        (
            "After a spell resolves, what happens before a player gets priority?",
            "704.3",
            (
                "Before a player gets priority, the game checks and performs all "
                "applicable state-based actions."
            ),
        ),
        (
            "May a player look at both faces of a double-faced card they can see?",
            "712.6",
            (
                "Players allowed to look at a double-faced card may look at both "
                "sides of that card."
            ),
        ),
        (
            "Which face supplies a transformed permanent characteristics?",
            "712.8e",
            (
                "A transformed permanent with its back face up has only the "
                "characteristics of its back face."
            ),
        ),
        (
            "Where in the layer system do control effects apply?",
            "613.1b",
            "Layer 2 applies control-changing effects.",
        ),
        (
            "Does a card instruction override the general game rules?",
            "101.1",
            (
                "When card text contradicts the rules, the card takes precedence "
                "for that situation."
            ),
        ),
    ],
)
async def test_lexical_search_ranks_distinct_official_term_coverage(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
    question: str,
    expected_key: str,
    expected_body: str,
    ) -> None:
    repository, passages = retrieval_fixture
    expected = next(
        (
            passage
            for passage in passages
            if passage.document_type == "rule"
            and passage.canonical_key == expected_key
        ),
        None,
    )
    if expected is None:
        expected = _passage(
            source_version_id=passages[0].source_version_id,
            document_type="rule",
            canonical_key=expected_key,
            body=expected_body,
            first_dimension=0.25,
        )
    strict_editorial_match = _passage(
        source_version_id=passages[0].source_version_id,
        document_type="ruling",
        canonical_key=f"editorial-{uuid.uuid4().hex}",
        body=f"Editorial paraphrase: {question}",
        first_dimension=0.25,
        source="wotc",
    )
    async with session_factory.begin() as session:
        session.add(strict_editorial_match)
        if expected not in passages:
            session.add(expected)

    result = await repository.lexical(question, limit=20)

    assert str(expected.id) in {
        candidate.passage.passage_id for candidate in result[:8]
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_ranks_wotc_ruling_above_editorial_tie(retrieval_fixture) -> None:  # type: ignore[no-untyped-def]
    repository, passages = retrieval_fixture

    result = await repository.lexical("target spell countered", limit=20)

    ruling_ids = [
        candidate.passage.passage_id
        for candidate in result
        if candidate.passage.document_type == "ruling"
    ]
    assert ruling_ids[:2] == [str(passages[2].id), str(passages[3].id)]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_treats_rules_as_authoritative_source(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.lexical("target spell countered", limit=20)

    matching_ids = [
        candidate.passage.passage_id
        for candidate in result
        if candidate.passage.passage_id in {str(passages[2].id), str(passages[7].id)}
    ]
    assert matching_ids[:2] == [str(passages[7].id), str(passages[2].id)]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_tiers_matching_rules_above_repetitive_rulings(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    rule = _passage(
        source_version_id=source_version_id,
        document_type="rule",
        canonical_key="704.5g",
        body="A creature has lethal marked damage.",
        first_dimension=0.5,
    )
    ruling = _passage(
        source_version_id=source_version_id,
        document_type="ruling",
        canonical_key="ruling-repetitive",
        body=(
            "A creature with lethal marked damage has lethal damage marked "
            "on that creature."
        ),
        first_dimension=0.5,
        source="wotc",
    )
    async with session_factory.begin() as session:
        session.add_all([rule, ruling])

    result = await repository.lexical(
        "What happens to a creature with lethal marked damage?",
        limit=20,
    )
    ids = [candidate.passage.passage_id for candidate in result]

    assert ids.index(str(rule.id)) < ids.index(str(ruling.id))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_falls_back_for_long_conversation_context(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    contextual_query = (
        "Current question: What happens next? "
        "Prior user: The spell resolves using last known information. "
        "Prior assistant: unrelated hexproof creature graveyard priority."
    )

    result = await repository.lexical(contextual_query, limit=20)

    assert str(passages[0].id) in {
        candidate.passage.passage_id for candidate in result[:8]
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_search_resolves_a_prior_users_token_zone_transition(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    expected = next(
        passage for passage in passages if passage.canonical_key == "704.5d"
    )
    contextual_query = (
        "Current question:\nWhy did it disappear?\n\n"
        "Prior user:\nMy creature token moved into my graveyard."
    )

    result = await repository.lexical(contextual_query, limit=20)

    assert str(expected.id) in {
        candidate.passage.passage_id for candidate in result[:8]
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_contextual_priority_anchor_marks_the_governing_rule_as_protected(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    governing_rule = _passage(
        source_version_id=passages[0].source_version_id,
        document_type="rule",
        canonical_key="117.3d",
        body=(
            "If a player passes priority, the next player in turn order receives "
            "priority."
        ),
        first_dimension=0.25,
    )
    async with session_factory.begin() as session:
        session.add(governing_rule)

    contextual_query = (
        "Current question:\nWho gets it next?\n\n"
        "Prior user:\nThe active player passed priority.\n\n"
        "Prior assistant:\nPriority passes in turn order."
    )

    result = await repository.lexical(contextual_query, limit=20)

    candidate = next(
        item
        for item in result
        if item.passage.passage_id == str(governing_rule.id)
    )
    assert candidate.rank <= 4
    assert candidate.protected is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pre_priority_anchor_protects_resolution_and_state_action_rules(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    resolution_rule = _passage(
        source_version_id=source_version_id,
        document_type="rule",
        canonical_key="117.3b",
        body=(
            "The active player receives priority after a spell or ability "
            "(other than a mana ability) resolves."
        ),
        first_dimension=0.25,
    )
    noise = [
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key=f"103.9{suffix}",
            body="After a spell resolves, the active player receives priority.",
            first_dimension=0.25,
        )
        for suffix in ("a", "b", "c", "d")
    ]
    async with session_factory.begin() as session:
        session.add_all([resolution_rule, *noise])

    result = await repository.lexical(
        "After a spell resolves, what happens before a player gets priority?",
        limit=20,
    )
    protected_ids = {
        candidate.passage.passage_id
        for candidate in result
        if candidate.protected
    }
    state_action_rule = next(
        passage for passage in passages if passage.canonical_key == "704.3"
    )

    assert str(resolution_rule.id) in protected_ids
    assert str(state_action_rule.id) in protected_ids


@pytest.mark.asyncio
@pytest.mark.integration
async def test_retained_v8_anchor_branches_select_the_governing_rule(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    rules = [
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="613.1",
            body="Continuous effects are applied in a series of layers.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="613.1f",
            body=(
                "Layer 6 applies ability-adding effects, keyword counters, and "
                "ability-removing effects."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="614.12",
            body="Replacement effects may modify how permanents enter the battlefield.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="616.1",
                body=(
                    "Replacement and prevention effects attempting to modify an event are "
                    "chosen by the affected object's controller; the affected player "
                    "chooses one."
                ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="704.5",
            body="The state-based actions are as follows.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="704.5a",
            body="If a player has 0 or less life, that player loses the game.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="810.8a",
            body="Players win and lose the game only as a team, not as individuals.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="704.5g",
            body=(
                "A creature with toughness greater than 0 whose total damage marked "
                "is greater than or equal to its toughness has lethal damage and is destroyed."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="702.19b",
            body="Trample assigns lethal damage using damage already marked on a creature.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="712.7",
            body=(
                "Double-faced cards in hidden zones must be indistinguishable from "
                "other cards in the same zone."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="712.1",
            body="There are three kinds of double-faced cards.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="712.8e",
            body=(
                "While a nonmodal double-faced permanent has its back face up, it has "
                "only the characteristics of its back face."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="712.4b",
            body="The back faces of a meld pair determine melded characteristics.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="117.4",
            body=(
                "If all players pass without taking actions between passing, the top "
                "spell or ability on the stack resolves."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="405.5",
            body="When all players pass, the top spell or ability on the stack resolves.",
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="805.5b",
            body=(
                "If all teams pass without any player taking actions between passing, "
                "the top object on the stack resolves."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="702.9b",
            body=(
                "A creature with flying can't be blocked except by creatures with "
                "flying or reach."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="702.17b",
            body=(
                "A creature with flying can't be blocked except by creatures with "
                "flying or reach."
            ),
            first_dimension=0.25,
        ),
        _passage(
            source_version_id=source_version_id,
            document_type="rule",
            canonical_key="111.7",
            body=(
                "A token in a zone other than the battlefield ceases to exist. "
                "This is a state-based action."
            ),
            first_dimension=0.25,
        ),
    ]
    async with session_factory.begin() as session:
        session.add_all(rules)

    checks = (
        ("Which layer adds and removes abilities?", "613.1f", None),
        (
            "Who chooses between multiple applicable replacement effects?",
            "616.1",
            "614.12",
        ),
        ("What happens to a player with zero life?", "704.5a", "810.8a"),
        (
            "What happens to a creature with lethal marked damage?",
            "704.5g",
            "702.19b",
        ),
        (
            "How must double-faced cards be handled in hidden zones?",
            "712.7",
            "712.1",
        ),
        (
            "Which face supplies a transformed permanent characteristics?",
            "712.8e",
            "712.4b",
        ),
        (
            "What occurs after all players pass with an object on the stack?",
            "117.4",
            "805.5b",
        ),
        (
            "Current question:\nCan a creature with reach block it?\n\n"
            "Prior user:\nMy attacker has flying.\n\n"
            "Prior assistant:\nFlying limits which creatures can block it.",
            "702.9b",
            "702.17b",
        ),
        (
            "Current question:\nWhat happens to it then?\n\n"
            "Prior user:\nA creature token was put into my graveyard.\n\n"
            "Prior assistant:\nState-based actions will be checked.",
            "704.5d",
            "111.7",
        ),
    )

    for question, expected_key, false_key in checks:
        result = await repository.lexical(question, limit=20)
        ranks = {candidate.passage.citation_label: candidate.rank for candidate in result}
        expected = next(
            candidate
            for candidate in result
            if candidate.passage.citation_label == expected_key
        )

        assert expected.protected is True
        if false_key in ranks:
            assert expected.rank < ranks[false_key]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ranked_paths_include_a_matched_subrules_governing_parent(
    retrieval_fixture,  # type: ignore[no-untyped-def]
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture
    source_version_id = passages[0].source_version_id
    parent = _passage(
        source_version_id=source_version_id,
        document_type="rule",
        canonical_key="603.7",
        body="Additional rules govern delayed triggered abilities.",
        first_dimension=0.0,
    )
    child = _passage(
        source_version_id=source_version_id,
        document_type="rule",
        canonical_key="603.7h",
        body="A delayed triggered ability can be created by a replacement effect.",
        first_dimension=1.0,
    )
    async with session_factory.begin() as session:
        session.add_all([parent, child])

    lexical = await repository.lexical(
        "delayed triggered ability created replacement effect",
        limit=20,
    )
    vector = await repository.vector(_embedding(1.0), limit=20)

    for candidates in (lexical, vector):
        ids = [candidate.passage.passage_id for candidate in candidates]
        child_index = ids.index(str(child.id))
        parent_index = ids.index(str(parent.id))
        assert parent_index > child_index


@pytest.mark.asyncio
@pytest.mark.integration
async def test_vector_search_uses_cosine_distance_and_excludes_inactive_passages(
    retrieval_fixture,  # type: ignore[no-untyped-def]
) -> None:
    repository, passages = retrieval_fixture

    result = await repository.vector(_embedding(1.0), limit=20)

    assert result[0].passage.passage_id == str(passages[4].id)
    assert str(passages[5].id) not in {candidate.passage.passage_id for candidate in result}
    assert len(result) <= 20
