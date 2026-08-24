import asyncio
from dataclasses import dataclass, field

import pytest

from app.generation.openai_adapter import RetrievedPassage
from app.retrieval.analysis import analyze_question
from app.retrieval.service import HybridRetrievalService, RetrievalCandidate


def _passage(passage_id: str, *, document_type: str = "rule") -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        document_type=document_type,
        citation_label=f"Rule {passage_id}",
        canonical_url=f"https://magic.wizards.com/rules#{passage_id}",
        text=f"Text for {passage_id}",
    )


@dataclass
class FakeEmbedding:
    calls: list[str] = field(default_factory=list)

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * 1536


class FakeRepository:
    def __init__(self) -> None:
        self.limits: list[int] = []
        self.exact_embeddings: list[list[float] | None] = []
        self.lexical_queries: list[str] = []

    async def exact(  # type: ignore[no-untyped-def]
        self,
        analysis,
        *,
        limit: int,
        embedding: list[float] | None = None,
    ):
        self.limits.append(limit)
        self.exact_embeddings.append(embedding)
        return [RetrievalCandidate(_passage("exact"), 1, "exact", exact=True)]

    async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
        self.limits.append(limit)
        self.lexical_queries.append(question)
        return [
            RetrievalCandidate(_passage("shared"), 1, "lexical"),
            RetrievalCandidate(_passage("lexical"), 2, "lexical"),
        ]

    async def vector(self, embedding: list[float], *, limit: int):
        self.limits.append(limit)
        return [
            RetrievalCandidate(_passage("shared"), 1, "vector"),
            RetrievalCandidate(_passage("vector"), 2, "vector"),
        ]


class ConcurrentRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.started: set[str] = set()
        self.all_started = asyncio.Event()

    async def _join(self, name: str) -> None:
        self.started.add(name)
        if len(self.started) == 3:
            self.all_started.set()
        await self.all_started.wait()

    async def exact(  # type: ignore[no-untyped-def]
        self,
        analysis,
        *,
        limit: int,
        embedding: list[float] | None = None,
    ):
        await self._join("exact")
        return await super().exact(analysis, limit=limit, embedding=embedding)

    async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
        await self._join("lexical")
        return await super().lexical(question, limit=limit)

    async def vector(self, embedding: list[float], *, limit: int):
        await self._join("vector")
        return await super().vector(embedding, limit=limit)


def test_question_analysis_extracts_explicit_card_names_and_rule_references() -> None:
    analysis = analyze_question('Does "Lightning Bolt" use rule 608.2h?')

    assert analysis.normalized == 'does "lightning bolt" use rule 608.2h?'
    assert analysis.quoted_card_names == ("lightning bolt",)
    assert analysis.rule_references == ("608.2h",)


@pytest.mark.asyncio
async def test_hybrid_retrieval_runs_exact_lexical_vector_rrf_and_pins_exact_first() -> None:
    repository = FakeRepository()
    embedding = FakeEmbedding()
    service = HybridRetrievalService(repository=repository, embedding=embedding)

    passages = await service.retrieve('What does "Lightning Bolt" do?')

    assert [passage.passage_id for passage in passages] == [
        "exact",
        "shared",
        "lexical",
        "vector",
    ]
    assert repository.limits == [20, 20, 20]
    assert repository.exact_embeddings == [None]
    assert embedding.calls == ['what does "lightning bolt" do?']
    assert passages[0].citation_required is True
    assert all(not passage.citation_required for passage in passages[1:])


@pytest.mark.asyncio
async def test_hybrid_retrieval_starts_independent_repository_paths_concurrently() -> None:
    repository = ConcurrentRepository()
    service = HybridRetrievalService(repository=repository, embedding=FakeEmbedding())

    passages = await asyncio.wait_for(
        service.retrieve_with_embedding("What is priority?", [0.0] * 1536),
        timeout=0.5,
    )

    assert repository.started == {"exact", "lexical", "vector"}
    assert {passage.passage_id for passage in passages} == {
        "exact",
        "shared",
        "lexical",
        "vector",
    }


@pytest.mark.asyncio
async def test_hybrid_retrieval_overlaps_embedding_with_embedding_independent_paths() -> None:
    embedding_started = asyncio.Event()
    text_paths_started = asyncio.Event()
    started: set[str] = set()

    class BlockingEmbedding(FakeEmbedding):
        async def embed(self, text: str) -> list[float]:
            self.calls.append(text)
            embedding_started.set()
            await text_paths_started.wait()
            return [0.0] * 1536

    class EarlyTextRepository(FakeRepository):
        async def _start(self, name: str) -> None:
            await embedding_started.wait()
            started.add(name)
            if started == {"exact", "lexical"}:
                text_paths_started.set()

        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            await self._start("exact")
            return await super().exact(analysis, limit=limit, embedding=embedding)

        async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
            await self._start("lexical")
            return await super().lexical(question, limit=limit)

    repository = EarlyTextRepository()
    service = HybridRetrievalService(repository=repository, embedding=BlockingEmbedding())

    passages = await asyncio.wait_for(
        service.retrieve("What is priority?"),
        timeout=0.5,
    )

    assert started == {"exact", "lexical"}
    assert {passage.passage_id for passage in passages} == {
        "exact",
        "shared",
        "lexical",
        "vector",
    }


@pytest.mark.asyncio
async def test_hybrid_retrieval_starts_vector_when_embedding_resolves() -> None:
    embedding_started = asyncio.Event()
    text_paths_started = asyncio.Event()
    vector_started = asyncio.Event()
    started: set[str] = set()

    class CoordinatedEmbedding(FakeEmbedding):
        async def embed(self, text: str) -> list[float]:
            self.calls.append(text)
            embedding_started.set()
            await text_paths_started.wait()
            return [0.0] * 1536

    class SlowTextRepository(FakeRepository):
        async def _text(self, name: str) -> None:
            await embedding_started.wait()
            started.add(name)
            if started == {"exact", "lexical"}:
                text_paths_started.set()
            await vector_started.wait()

        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            await self._text("exact")
            return await super().exact(analysis, limit=limit, embedding=embedding)

        async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
            await self._text("lexical")
            return await super().lexical(question, limit=limit)

        async def vector(self, embedding: list[float], *, limit: int):
            vector_started.set()
            return await super().vector(embedding, limit=limit)

    passages = await asyncio.wait_for(
        HybridRetrievalService(
            repository=SlowTextRepository(),
            embedding=CoordinatedEmbedding(),
        ).retrieve("What is priority?"),
        timeout=0.5,
    )

    assert vector_started.is_set()
    assert {passage.passage_id for passage in passages} == {
        "exact",
        "shared",
        "lexical",
        "vector",
    }


@pytest.mark.asyncio
async def test_hybrid_retrieval_cancels_text_paths_when_embedding_fails() -> None:
    text_paths_started = asyncio.Event()
    started: set[str] = set()
    cancelled: set[str] = set()
    sibling_tasks: list[asyncio.Task[object]] = []

    class FailingEmbedding(FakeEmbedding):
        async def embed(self, text: str) -> list[float]:
            self.calls.append(text)
            await text_paths_started.wait()
            raise RuntimeError("embedding failed")

    class BlockingTextRepository(FakeRepository):
        async def _block(self, name: str) -> None:
            task = asyncio.current_task()
            assert task is not None
            sibling_tasks.append(task)
            started.add(name)
            if started == {"exact", "lexical"}:
                text_paths_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.add(name)
                raise

        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            await self._block("exact")
            return []

        async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
            await self._block("lexical")
            return []

    try:
        with pytest.raises(RuntimeError, match="embedding failed"):
            await HybridRetrievalService(
                repository=BlockingTextRepository(),
                embedding=FailingEmbedding(),
            ).retrieve("What is priority?")

        assert cancelled == {"exact", "lexical"}
        assert all(task.done() for task in sibling_tasks)
    finally:
        for task in sibling_tasks:
            task.cancel()
        await asyncio.gather(*sibling_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_preparation_cancels_lexical_when_exact_fails() -> None:
    lexical_started = asyncio.Event()
    lexical_cancelled = asyncio.Event()
    lexical_tasks: list[asyncio.Task[object]] = []

    class FailingExactRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            await lexical_started.wait()
            raise RuntimeError("exact failed")

        async def lexical(self, question: str, *, limit: int):  # type: ignore[no-untyped-def]
            task = asyncio.current_task()
            assert task is not None
            lexical_tasks.append(task)
            lexical_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                lexical_cancelled.set()
                raise

    service = HybridRetrievalService(
        repository=FailingExactRepository(),
        embedding=FakeEmbedding(),
    )
    try:
        with pytest.raises(RuntimeError, match="exact failed"):
            await service.prepare_retrieval("What is priority?")

        assert lexical_cancelled.is_set()
        assert all(task.done() for task in lexical_tasks)
    finally:
        for task in lexical_tasks:
            task.cancel()
        await asyncio.gather(*lexical_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_hybrid_retrieval_preserves_structured_sections_for_lexical_only() -> None:
    repository = FakeRepository()
    embedding = FakeEmbedding()
    service = HybridRetrievalService(repository=repository, embedding=embedding)
    question = (
        "Current question:\nWhat happens next?\n\n"
        "Prior user:\nMy creature token moved into my graveyard."
    )

    await service.retrieve(question)

    assert repository.lexical_queries == [question]
    assert embedding.calls == [
        "current question: what happens next? prior user: my creature token "
        "moved into my graveyard."
    ]


@pytest.mark.asyncio
async def test_retrieval_context_is_capped_at_eight_passages() -> None:
    class ManyRepository(FakeRepository):
        async def lexical(self, question: str, *, limit: int):
            return [
                RetrievalCandidate(_passage(f"p-{index}"), index + 1, "lexical")
                for index in range(20)
            ]

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    service = HybridRetrievalService(repository=ManyRepository(), embedding=FakeEmbedding())

    passages = await service.retrieve("What is priority?")

    assert len(passages) == 8


@pytest.mark.asyncio
async def test_single_path_approximate_passage_is_not_marked_required() -> None:
    class ApproximateRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return []

        async def lexical(self, question: str, *, limit: int):
            return [
                RetrievalCandidate(_passage("rule-a"), 1, "lexical"),
                RetrievalCandidate(_passage("rule-b"), 2, "lexical"),
            ]

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    service = HybridRetrievalService(
        repository=ApproximateRepository(),
        embedding=FakeEmbedding(),
    )

    passages = await service.retrieve("What happens?")

    assert passages[0].passage_id == "rule-a"
    assert all(not passage.citation_required for passage in passages)


@pytest.mark.asyncio
async def test_corroborated_official_passage_is_required_without_exact_evidence() -> None:
    class CorroboratedRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return []

        async def lexical(self, question: str, *, limit: int):
            return [RetrievalCandidate(_passage("rule-a"), 1, "lexical")]

        async def vector(self, embedding: list[float], *, limit: int):
            return [RetrievalCandidate(_passage("rule-a"), 1, "vector")]

    service = HybridRetrievalService(
        repository=CorroboratedRepository(),
        embedding=FakeEmbedding(),
    )

    passages = await service.retrieve("What happens?")

    assert passages[0].passage_id == "rule-a"
    assert passages[0].citation_required is True


@pytest.mark.asyncio
async def test_explicit_exact_card_support_is_marked_as_primary_citation_required() -> None:
    class CardOnlyRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                RetrievalCandidate(
                    _passage("card-support", document_type="card"),
                    1,
                    "exact",
                    exact=True,
                )
            ]

        async def lexical(self, question: str, *, limit: int):
            return []

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    passages = await HybridRetrievalService(
        repository=CardOnlyRepository(),
        embedding=FakeEmbedding(),
    ).retrieve("What does the named card do?")

    assert passages[0].passage_id == "card-support"
    assert passages[0].citation_required is True


@pytest.mark.asyncio
async def test_specific_exact_glossary_definition_is_citation_required() -> None:
    class GlossaryOnlyRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                RetrievalCandidate(
                    _passage("glossary-support", document_type="glossary"),
                    1,
                    "glossary",
                    exact=True,
                )
            ]

        async def lexical(self, question: str, *, limit: int):
            return []

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    passages = await HybridRetrievalService(
        repository=GlossaryOnlyRepository(),
        embedding=FakeEmbedding(),
    ).retrieve("Please give the rules definition of flying.")

    assert passages[0].citation_required is True


@pytest.mark.asyncio
async def test_definition_requires_glossary_but_not_its_linked_rule() -> None:
    class DefinitionRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                RetrievalCandidate(
                    _passage("glossary-support", document_type="glossary"),
                    1,
                    "glossary",
                    exact=True,
                ),
                RetrievalCandidate(
                    _passage("linked-rule"),
                    2,
                    "linked_rule",
                    exact=True,
                ),
            ]

        async def lexical(self, question: str, *, limit: int):
            return []

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    passages = await HybridRetrievalService(
        repository=DefinitionRepository(),
        embedding=FakeEmbedding(),
    ).retrieve("Please give the rules definition of flying.")

    required = {passage.passage_id for passage in passages if passage.citation_required}
    assert required == {"glossary-support"}


@pytest.mark.asyncio
async def test_protected_procedure_is_required_without_exact_expansion_requirements() -> None:
    class ProcedureRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                RetrievalCandidate(
                    _passage("broad-glossary", document_type="glossary"),
                    1,
                    "glossary",
                    exact=True,
                ),
                RetrievalCandidate(
                    _passage("broad-linked-rule"),
                    2,
                    "linked_section",
                    exact=True,
                ),
            ]

        async def lexical(self, question: str, *, limit: int):
            return [
                RetrievalCandidate(
                    _passage("direct-procedure"),
                    1,
                    "lexical",
                    protected=True,
                )
            ]

        async def vector(self, embedding: list[float], *, limit: int):
            return [
                RetrievalCandidate(
                    _passage("broad-glossary", document_type="glossary"),
                    1,
                    "vector",
                )
            ]

    passages = await HybridRetrievalService(
        repository=ProcedureRepository(),
        embedding=FakeEmbedding(),
    ).retrieve("In which layer are copy effects applied?")

    required = {passage.passage_id for passage in passages if passage.citation_required}
    assert required == {"direct-procedure"}


@pytest.mark.asyncio
async def test_pre_priority_procedure_requires_both_protected_branches() -> None:
    class TwoBranchRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return []

        async def lexical(self, question: str, *, limit: int):
            return [
                RetrievalCandidate(
                    _passage("priority-after-resolution"),
                    1,
                    "lexical",
                    protected=True,
                ),
                RetrievalCandidate(
                    _passage("state-actions-before-priority"),
                    2,
                    "lexical",
                    protected=True,
                ),
            ]

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    passages = await HybridRetrievalService(
        repository=TwoBranchRepository(),
        embedding=FakeEmbedding(),
    ).retrieve("After a spell resolves, what happens before a player gets priority?")

    required = {passage.passage_id for passage in passages if passage.citation_required}
    assert required == {
        "priority-after-resolution",
        "state-actions-before-priority",
    }


@pytest.mark.asyncio
async def test_contextual_card_ability_requires_its_linked_rule() -> None:
    class ContextualAbilityRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                RetrievalCandidate(
                    _passage("context-card", document_type="card"),
                    1,
                    "exact",
                    exact=True,
                ),
                RetrievalCandidate(
                    _passage("linked-ability-rule"),
                    2,
                    "linked_rule",
                    exact=True,
                ),
            ]

        async def lexical(self, question: str, *, limit: int):
            return []

        async def vector(self, embedding: list[float], *, limit: int):
            return []

    question = (
        "Current question:\nWhat if it loses that ability?\n\n"
        "Prior user:\nMy creature is Slippery Bogle."
    )
    passages = await HybridRetrievalService(
        repository=ContextualAbilityRepository(),
        embedding=FakeEmbedding(),
    ).retrieve(question)

    required = {passage.passage_id for passage in passages if passage.citation_required}
    assert required == {"context-card", "linked-ability-rule"}


@pytest.mark.asyncio
async def test_glossary_candidates_do_not_displace_a_linked_governing_rule() -> None:
    class GlossaryHeavyRepository(FakeRepository):
        async def exact(  # type: ignore[no-untyped-def]
            self,
            analysis,
            *,
            limit: int,
            embedding: list[float] | None = None,
        ):
            return [
                *[
                    RetrievalCandidate(
                        _passage(f"glossary-{index}"),
                        index,
                        "glossary",
                    )
                    for index in range(1, 9)
                ],
                RetrievalCandidate(
                    _passage("governing-rule"),
                    9,
                    "linked_rule",
                    exact=True,
                ),
            ]

    service = HybridRetrievalService(
        repository=GlossaryHeavyRepository(),
        embedding=FakeEmbedding(),
    )

    passages = await service.retrieve("What is priority?")

    assert passages[0].passage_id == "governing-rule"
    assert "shared" in {passage.passage_id for passage in passages}
