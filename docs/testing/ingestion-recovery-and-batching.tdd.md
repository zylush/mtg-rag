# Ingestion recovery and batching: TDD evidence

## Source and user journeys

Derived from [MTG-PLAN.md](../../MTG-PLAN.md) during the Google Cloud deployment.

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
full upstream downloads, Secret Manager injection, and activation of the rules
and cards corpora; the rulings edge case is covered below.

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
