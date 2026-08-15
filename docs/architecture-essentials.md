# MTG Rules Desk Architecture Essentials

This is the short learning guide for the system. Read it before the complete
[Architecture.md](Architecture.md).

## 1. The central idea

MTG Rules Desk follows one rule:

> Retrieve trusted evidence first, then let the model write from that evidence.

It is a traditional RAG application. The model does not freely browse, query SQL, or decide which
unbounded tools to call.

## 2. The system in one picture

```text
Browser
  |
  v
Firebase Hosting and Authentication
  |
  v
Cloud Run FastAPI backend
  |
  +--> exact + lexical + vector retrieval
  |       |
  |       v
  |    Cloud SQL PostgreSQL + pgvector
  |
  +--> OpenAI Responses API
  |
  +--> validated answer and citations
```

The browser never calls OpenAI. It sends the Firebase token and question to FastAPI. FastAPI owns
the secret, retrieval, quota, cache, citations, and conversation history.

## 3. Development proxy versus production load balancer

The current development site uses a Firebase Hosting rewrite:

```text
browser -> Firebase Hosting -> /v1 rewrite -> Cloud Run
```

The production infrastructure can instead use:

```text
browser -> external load balancer -> Cloud Armor -> serverless NEG -> Cloud Run
```

Terraform is the tool that creates the Google Cloud resources. It is not itself a load balancer.
The load balancer routes requests. The Cloud Run autoscaler creates and removes container
instances. The production Cloud Armor configuration allows Taiwan, Japan, South Korea, and
Singapore and denies other countries by default.

## 4. Cloud Run scaling

Development is configured with:

| Setting | Value |
| --- | ---: |
| Minimum instances | 0 |
| Maximum instances | 3 |
| Maximum concurrency per instance | 20 |

Three instances do not mean three users. One instance may handle multiple simultaneous requests,
and users are not permanently assigned to an instance. At the configured ceiling, the service has
roughly sixty in-flight request slots. This is not a guaranteed throughput because OpenAI latency,
CPU, memory, database capacity, and request complexity also matter.

Minimum zero allows scale-to-zero and reduces idle compute cost. The first request after an idle
period can experience a cold start. The maximum-three setting limits Cloud Run compute growth but
does not cap OpenAI, database, storage, logging, or networking charges.

## 5. The three knowledge sources

| Source | Use |
| --- | --- |
| WotC Comprehensive Rules | General rules and glossary definitions |
| Oracle cards via Scryfall | Current card wording and identity |
| Card rulings via Scryfall | Dated card-specific clarification |

WotC-authored rulings rank above Scryfall editorial rulings. Source, date, and active version are
preserved so an answer can be audited.

## 6. From source text to vectors

Raw source records are not placed directly into vector search.

```text
raw rules or Scryfall JSON
        |
        v
parse into structured MTG records
        |
        v
construct rule, glossary, card, or ruling text passage
        |
        v
OpenAI text-embedding-3-small
        |
        v
1,536-number vector stored in pgvector
```

Rules are split at numbered rule boundaries. Glossary entries are separate. Oracle cards are
grouped by Oracle identity, and multi-face cards preserve face order.

When source text is unchanged, ingestion can reuse its existing vector. Changed text is embedded
in batches. Changing the embedding model requires a full re-embedding because vectors created by
different models must not be compared.

## 7. Hybrid retrieval

Different search methods solve different problems.

### Exact search

Exact search handles card names, aliases, glossary phrases, and rule numbers such as `608.2b`.
Exact results are pinned first because an embedding should not guess a named identifier.

### Lexical search

PostgreSQL full-text search finds passages using shared words and rules terminology. It is strong
when the question and source use the same language.

### Vector search

An embedding is a numeric representation of meaning. Vector search compares the question vector
with passage vectors using cosine distance. It can connect different wording that expresses a
similar concept.

### Reciprocal-rank fusion

Lexical relevance and cosine similarity use different scales. Reciprocal-rank fusion combines
their rank positions:

```text
contribution = 1 / (60 + rank)
```

The system fuses up to twenty lexical and twenty vector results with exact results, pins exact
matches, and sends at most eight passages to the model.

## 8. Cosine similarity is not truth

Cosine similarity answers:

> Do these vectors point in a similar semantic direction?

It does not answer:

> Is this MTG ruling definitely correct?

Normal passage retrieval takes the best-ranked vector results without a fixed cosine cutoff and
balances them with exact and lexical evidence.

The strict `0.98` threshold is for semantic answer-cache reuse. A new question may reuse a cached
answer only when it is extremely similar and every other cache safeguard also passes.

## 9. Exact and semantic caching

An exact cache hit requires the same normalized question and system context. It skips both the
question embedding and answer generation.

A semantic cache hit requires:

- Cosine similarity of at least `0.98`.
- The same rules, cards, and rulings versions.
- The same embedding model and dimensions.
- The same generation model, prompt, and retrieval version.
- The same language and filters.
- Unexpired data with a maximum seven-day TTL.
- All cited passages still active.
- A high-confidence, simple, non-ambiguous question.

Complex interactions and multiplayer scenarios are regenerated. A cache failure does not block a
fresh answer. Cache hits still consume daily quota.

## 10. How answer correctness is protected

No single threshold guarantees correctness. The system uses a chain:

1. Trusted, versioned sources.
2. Section-aware passages.
3. Exact lookup for known identifiers.
4. Hybrid retrieval for broader recall.
5. A maximum of eight active passages.
6. A prompt that permits answers only from those passages.
7. Structured answer fields.
8. Server-side citation-ID validation.
9. One citation-repair attempt.
10. Clarification or abstention when support is missing.
11. Version-aware cache eligibility.
12. A maintained evaluation suite.

The model's `high`, `medium`, or `low` confidence is a label, not a calibrated probability. A high
label alone cannot make an answer correct.

## 11. Prompt-injection protection

Retrieved passages are untrusted data. If a passage says `ignore previous instructions`, the model
must treat it as quoted source text, not a command. Passages are separated from system
instructions, and the model receives no arbitrary SQL or web tools.

## 12. Authentication, secrets, and quotas

- Firebase Authentication proves the browser user's identity.
- FastAPI verifies the token and enforces conversation ownership.
- Secret Manager supplies the OpenAI and database credentials only to server-side processes.
- Docker images and frontend bundles do not contain the OpenAI key.
- Each user receives five ask attempts per minute and twenty successful answers per UTC day.
- Quota updates are atomic so simultaneous requests cannot over-consume the allowance.

## 13. Answer and citation flow

```text
question
  |
  v
cache check
  |
  v
hybrid retrieval
  |
  v
bounded evidence sent to OpenAI
  |
  v
structured answer with passage IDs
  |
  v
backend validates IDs and resolves labels/URLs
  |
  v
answer, citations, history, and quota committed together
```

If the model invents an unknown passage ID, the backend allows one repair. A second citation
failure produces a low-confidence abstention instead of unsupported prose.

## 14. Safe source updates

Ingestion downloads from allowlisted HTTPS sources, saves an immutable raw snapshot, parses and
embeds into staging, validates the result, and then activates the complete version atomically.

Users therefore see either the old complete corpus or the new complete corpus. They do not search
a half-imported rulebook. Failed imports preserve the preceding active version.

## 15. Key numbers

| Control | Value |
| --- | ---: |
| Embedding dimensions | 1,536 |
| Embedding batch maximum | 128 inputs |
| Lexical candidates | 20 |
| Vector candidates | 20 |
| Final generation passages | 8 |
| Semantic-cache similarity | 0.98 |
| Semantic-cache maximum TTL | 7 days |
| Question length | 2,000 characters |
| Ask burst | 5 per user per minute |
| Daily successful answers | 20 per user |
| Application timeout | 30 seconds |
| Cloud Run timeout | 40 seconds |
| Development max instances | 3 |
| Cloud Run concurrency | 20 per instance |

## 16. Useful vocabulary

| Term | Meaning |
| --- | --- |
| RAG | Retrieve evidence, then generate from it |
| Corpus | A collection of knowledge-source documents |
| Passage | One searchable unit, such as a rule, glossary entry, card, or ruling |
| Embedding | A list of numbers representing aspects of text meaning |
| Vector search | Find passages whose embeddings are close to the question embedding |
| Lexical search | Find passages using matching words and phrases |
| Hybrid retrieval | Combine exact, lexical, and vector search |
| RRF | Merge ranked lists by position instead of comparing incompatible raw scores |
| pgvector | PostgreSQL extension for storing and comparing vectors |
| Grounding | Require claims to be supported by supplied evidence |
| Abstention | Refuse unsupported prose and explain that evidence is insufficient |
| Atomic activation | Switch from one complete source version to another in one transaction |
| Load balancer | Public traffic router in front of application instances |
| Serverless NEG | The load balancer's connection to Cloud Run |

## 17. Suggested reading order

1. `backend/app/ask/service.py` for the end-to-end request flow.
2. `backend/app/retrieval/service.py` and `fusion.py` for hybrid retrieval.
3. `backend/app/generation/` for prompting, citation validation, repair, and abstention.
4. `backend/app/cache/` for exact and semantic caching.
5. `backend/app/ingestion/` for parsing, embeddings, activation, and rollback.
6. `backend/app/db/models.py` for the persisted data model.
7. `frontend/src/App.tsx` and `api-client.ts` for the browser experience.
8. `infra/` and `firebase.json` for Google Cloud delivery.

For full design details, continue with [Architecture.md](Architecture.md). For the assistant's
behavioral contract, read [agent.md](agent.md).
