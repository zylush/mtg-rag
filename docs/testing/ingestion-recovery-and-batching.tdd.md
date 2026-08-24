# Ingestion recovery and batching: TDD evidence

## Source and user journeys

Derived from [Architecture.md](../architecture/Architecture.md#6-ingestion-architecture) during the Google Cloud deployment.

As an operator, I can retry a failed authoritative corpus snapshot, so that a
transient parser or validation failure does not block the next scheduled refresh.

As an operator, I can import the full card corpus within the Cloud Run Job time
limit, so that the initial release has grounded card and rules retrieval.

## RED

The initial Cloud Run ingestion execution reached the public WotC and Scryfall
sources but failed twice: the current WotC rules document contains a `Glossary`
entry in its contents before the real glossary heading, then the automatic retry
hit the unique `(source_name, sha256)` constraint for the failed rules snapshot.

Commands and relevant results:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_rules_parser.py -q
# 1 failed, 3 passed: RulesParseError: no numbered rules found

..\.venv\Scripts\pytest.exe tests\integration\test_postgres_ingestion.py::test_repository_retries_a_failed_snapshot_without_duplicate_staged_records -q
# 1 failed: duplicate key value violates unique constraint uq_source_versions_source_name
```

Checkpoint: `9f617e6 test: reproduce ingestion retry failures`.

A deployment review also found that the initial full import embedded every new
passage with a separate request. The batching tests established the intended
contract before implementation:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_embedding_adapter.py tests\unit\test_ingestion_pipeline.py -q
# 3 failed, 6 passed: OpenAIEmbeddingAdapter has no embed_many; pipeline made no batch calls
```

Checkpoint: `6177571 test: require batched ingestion embeddings`.

## GREEN

The parser now selects the final glossary heading. The repository resets only a
failed, inactive snapshot record before retrying it; active or nonfailed versions
remain protected. The embedding adapter accepts bounded batches, restores API
response order by index, and the ingestion pipeline sends at most 128 changed
documents per request.

Commands and results:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_rules_parser.py tests\integration\test_postgres_ingestion.py::test_repository_retries_a_failed_snapshot_without_duplicate_staged_records -q
# 5 passed

..\.venv\Scripts\pytest.exe tests\unit\test_embedding_adapter.py tests\unit\test_ingestion_pipeline.py -q
# 9 passed

..\.venv\Scripts\pytest.exe --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
..\.venv\Scripts\ruff.exe check app tests
..\.venv\Scripts\mypy.exe app
# 127 passed; total branch coverage 85.74%; Ruff and mypy passed
```

Checkpoints: `82f6d7b fix: make corpus ingestion retries safe` and
`a45e6a6 fix: batch corpus embedding requests`.

## Guarantees

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| The parser ignores the contents listing and parses numbered rules under the real glossary boundary. | `test_rules_parser_uses_the_final_glossary_heading_after_the_contents_listing` | Unit | PASS |
| A failed inactive source version can be restaged without creating a duplicate source-version record. | `test_repository_retries_a_failed_snapshot_without_duplicate_staged_records` | PostgreSQL integration | PASS |
| Retrying clears stale staged passages before restaging the same immutable source version. | Same PostgreSQL integration test | PostgreSQL integration | PASS |
| The adapter submits multiple texts in one request and restores the API's indexed response order. | `test_embedding_adapter_batches_inputs_and_restores_response_index_order` | Unit | PASS |
| Empty embedding batches are rejected locally. | `test_embedding_adapter_rejects_an_empty_batch` | Unit | PASS |
| New corpus passages are sent in deterministic 128-document batches. | `test_pipeline_batches_new_embeddings_in_stable_request_order` | Unit | PASS |

## Known boundary

This evidence validates parsing, retry state, and request batching without using
the production OpenAI key. The Cloud Run execution operationally verified the
full upstream downloads, Secret Manager injection, and activation of the rules,
cards, and rulings corpora; the rulings edge case is covered below.

## Rulings-feed follow-up

The live Scryfall rulings import reached the final source after successfully
embedding and staging the cards corpus. It then encountered a record with no
substantive `comment` field. Such a record cannot support a citation, so it is
ignored; nonblank rulings retain all existing identity, date, source, and
attribution validation.

RED:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_scryfall_parser.py -q
# 1 failed, 3 passed: ScryfallParseError: missing required field: comment
```

GREEN:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_scryfall_parser.py -q
# 4 passed

..\.venv\Scripts\pytest.exe --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
..\.venv\Scripts\ruff.exe check app tests
..\.venv\Scripts\mypy.exe app
# 128 passed; total branch coverage 85.76%; Ruff and mypy passed
```

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| Blank or absent ruling comments do not abort the source refresh. | `test_rulings_skip_records_without_substantive_comment_text` | Unit | PASS |
| A usable ruling survives the same feed and remains available as grounded content. | `test_rulings_skip_records_without_substantive_comment_text` | Unit | PASS |

Checkpoints: `7d56c12 test: reproduce blank Scryfall ruling comments` and
`32e0f52 fix: ignore blank Scryfall rulings`.

## Bounded staging follow-up

The first full rulings activation completed, but Cloud Run reported a task retry
after a `SIGKILL`. The succeeding attempt found every source unchanged, proving
the activation itself was durable. Because the original pipeline retained every
embedding for the full corpus before a single database stage, this change bounds
the embedding lookup, request, and database staging state to 128 passages at a
time. The exact platform reason for the signal is not asserted here.

RED:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_ingestion_pipeline.py -q
# 2 failed, 3 passed: pipeline loaded all active embeddings and staged once
```

GREEN:

```text
cd backend
..\.venv\Scripts\pytest.exe tests\unit\test_ingestion_pipeline.py -q
# 5 passed

..\.venv\Scripts\pytest.exe --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
..\.venv\Scripts\ruff.exe check app tests
..\.venv\Scripts\mypy.exe app
# 128 passed; total branch coverage 85.66%; Ruff and mypy passed
```

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| A corpus larger than 128 documents looks up active embeddings and stages passages in 128-document batches. | `test_pipeline_batches_new_embeddings_in_stable_request_order` | Unit | PASS |
| An unchanged document reuses its cached vector while new documents in the same bounded stage are embedded. | `test_pipeline_snapshots_stages_validates_then_activates_and_embeds_only_changes` | Unit | PASS |
| Existing one-shot callers retain a repository compatibility method while the production pipeline uses bounded stages. | Full backend test suite | Unit + PostgreSQL integration | PASS |

Checkpoints: `d7bc64f test: require bounded ingestion staging` and
`5005e52 fix: bound ingestion staging memory`.

## WotC CRLF compatibility follow-up

The scheduled development ingestion fetched the August 8, 2026 WotC rules file but
failed with `RulesParseError: missing glossary section`. The document still contains
the final `Glossary` heading; its line endings are now CRLF, while the parser's exact
delimiter accepted LF only.

RED:

```text
.\.venv\Scripts\pytest.exe backend\tests\unit\test_rules_parser.py::test_rules_parser_accepts_wotc_crlf_line_endings -q
# 1 failed: RulesParseError: missing glossary section
```

GREEN:

```text
.\.venv\Scripts\pytest.exe backend\tests\unit\test_rules_parser.py -q
# 5 passed

.\.venv\Scripts\ruff.exe check backend\app\ingestion\rules.py backend\tests\unit\test_rules_parser.py
# All checks passed
```

The exact downloaded payload was then parsed locally without retaining or printing
its substantive contents: effective date `2026-08-07`, 3,161 numbered rules, and 740
glossary entries. The parser normalizes CRLF and lone-CR endings to LF before locating
the final glossary boundary. No checkpoint commit was created because the worktree
already contains operator-owned changes that must remain uncommitted and intact.

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| The live WotC CRLF payload reaches the final glossary boundary. | `test_rules_parser_accepts_wotc_crlf_line_endings` | Unit + live-shape check | PASS |
| Existing LF fixtures and final-heading selection remain unchanged. | Full `test_rules_parser.py` | Unit | PASS |
| Retrying the failed matching SHA reuses and clears the inactive staged version. | `test_repository_retries_a_failed_snapshot_without_duplicate_staged_records` | PostgreSQL integration | PASS |

## Authorized card-only cap follow-up (2026-08-20)

User journey: as the development operator, I need the authorized card refresh to stay within
1,062 embedding inputs and nine requests, while any unrelated source remains frozen and cannot be
picked up later by the daily scheduler.

The all-source read-only preflight correctly aborted external work. Rules needed zero embeddings,
cards needed 1,062 inputs in nine requests, and rulings independently needed 1,633 inputs in 13
requests. No Cloud Build, Terraform apply, GCS write, database write, or OpenAI call occurred, and
the exact temporary proxy was stopped.

RED:

```text
pytest tests/unit/test_ingestion_cli.py tests/unit/test_runtime_manifests.py -q
# collection error: app.ingestion.cli had no _parse_sources selector
```

GREEN:

```text
pytest tests/unit/test_ingestion_cli.py tests/unit/test_runtime_manifests.py -q
# 28 passed

pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80 -q
# 215 passed; 85.22% total branch coverage

ruff check app tests
mypy app
terraform fmt -check -recursive
terraform validate
# All passed; Terraform configuration is valid
```

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| No source argument preserves the dependency-ordered rules/cards/rulings behavior. | `test_ingestion_source_arguments_default_to_all_and_accept_cards` | Unit | PASS |
| A card-only execution invokes no rules or rulings pipeline work. | `test_refresh_can_select_only_the_authorized_card_source` | Unit | PASS |
| Duplicate source arguments fail before ingestion. | `test_ingestion_source_arguments_reject_duplicates` | Unit | PASS |
| Development scheduler executions remain card-only while production retains the all-source default. | `test_development_ingestion_scheduler_is_card_only_but_production_is_not` | Manifest | PASS |

No checkpoint commit was created because the worktree contains broad operator-owned changes that
must remain intact. Applying the development-only scheduler argument remains an explicit external
approval boundary; production is unchanged.

## Authorized development activation result (2026-08-20 UTC)

The operator authorized the saved one-change guard plan. Apply completed with `0 added, 1 changed,
0 destroyed`; live ingestion generation 12 was `Ready` with `args=[cards]` and
`maxRetries=0`. Cloud Build `cf4fc5ab-88e8-40d2-96cc-e0687f1caae3` then passed all gates and
published digest
`sha256:5142c179060c6058433461c91ee36a353d3fb83c95a2239a96d1b4986b70d865`. A fresh plan
applied four development image updates in place, zero additions, and zero deletions; the ingestion
guard remained unchanged. No production plan or apply was run.

The final read-only preflight repeated the authorized selected-source cap exactly: 1,062 new card
embedding inputs in nine requests, zero changed cards, and zero removed cards. Rules needed zero
inputs but rulings independently needed 1,633 inputs, so the deployed card selector kept both
unselected.

Execution `mtg-rag-dev-ingestion-s7tff` ran once on attempt zero and completed successfully.
Logs show exactly nine successful embedding requests and
`new_embedding_count=1062, source=cards, status=activated`. Active cards moved from version
`e13d27f7-6ef2-4045-b49f-5c2cdbc6ee1e` with 36,494 passages to version
`77b19b9f-bbae-4d93-a050-ed21243d6d65` with 37,556 passages. Exactly one active
`Black Lotus` passage is present.

Rules stayed at version `bd0b2abc-c4d9-4efa-80bd-34a7c5aee3ca`, SHA-256
`68dab840bfb200a4fca4a061793269c40d57f83364cb1091ea9094b5b8f04769`, and 3,901 passages.
Rulings stayed at version `6a0662bc-d599-4497-b857-4c1630601dd2`, SHA-256
`350c3dd1a62d0a19683620006c2f0e610680ecc2f93ae973d4d1771666901617`, and 77,314 passages.
Each temporary proxy was stopped by verified PID/path and port 5433 was closed.
