# MTG Rules Desk Visual Backend Architecture

This guide explains the two editable backend diagrams for MTG Rules Desk.

[Open the FigJam architecture board](https://www.figma.com/board/t4AWxq0yvdhVrTdMBwAmF1)

The architecture is split into two diagrams because the application has two different kinds of
work:

1. **Live RAG Request Flow** handles a user's question and returns a grounded answer.
2. **Versioned Knowledge Ingestion** updates the MTG rules knowledge used by the live system.

Keeping these flows separate makes the system easier to understand and prevents unrelated arrows
from overlapping.

## 1. How to read the diagrams

- A box represents a browser, deployable service, datastore, or external provider.
- A solid arrow represents normal application traffic or a direct data operation.
- A dotted arrow represents communication with a managed or external service.
- The arrow label summarizes what travels across that connection.
- The Firebase Hosting and load-balancer routes are alternatives. They are not two required hops
  in the same request.

## 2. Diagram one: Live RAG Request Flow

This diagram shows what happens when a person opens the web application and asks an MTG rules
question.

### Web browser

The desktop or mobile browser runs the React progressive web application. It displays the chat,
collects the question, obtains a Firebase ID token after sign-in, and sends authenticated API
requests.

The browser does not receive the OpenAI API key or the database password.

### Firebase Hosting

Firebase Hosting is the current development delivery path. It serves the compiled frontend and
forwards same-origin `/v1/**` requests to the Cloud Run API.

```text
browser -> Firebase Hosting -> Cloud Run FastAPI
```

Using a same-origin rewrite keeps frontend configuration simple and avoids exposing a separate API
hostname to the browser.

### HTTPS load balancer

The external HTTPS load balancer is the production delivery option. It can provide a global IP,
managed TLS certificate, HTTPS redirection, Cloud Armor policy, and a serverless connection to
Cloud Run.

```text
browser -> HTTPS load balancer -> Cloud Run FastAPI
```

The load balancer routes traffic. It does not create Cloud Run instances. Cloud Run's autoscaler
creates and removes instances according to demand and the configured scaling limits.

### Cloud Run FastAPI

The FastAPI container is the main backend. It owns the trusted application workflow:

1. Bound the request size and execution time.
2. Verify the Firebase ID token.
3. Check burst and daily usage limits.
4. Load the active rules, cards, and rulings version identifiers.
5. Check the exact answer cache.
6. Embed an eligible cache miss once.
7. Check the semantic cache when the question is safe to reuse.
8. Run exact, lexical, and vector retrieval on a cache miss.
9. Fuse the retrieval rankings and select at most eight passages.
10. Ask OpenAI to answer only from the selected evidence.
11. Validate every returned citation ID.
12. Save the answer, citations, history, and quota update atomically.

The model does not receive arbitrary SQL, HTTP, or ingestion tools.

### Cloud SQL and pgvector

Cloud SQL PostgreSQL is the system of record. It contains:

- Active versioned MTG passages.
- Full-text search indexes for lexical retrieval.
- pgvector embeddings for semantic retrieval.
- Exact and semantic answer-cache entries.
- Users, quotas, conversations, messages, citations, and feedback.

Hybrid retrieval combines three search paths:

- **Exact retrieval** for rule numbers, card names, aliases, and glossary phrases.
- **Lexical retrieval** for shared words and official rules terminology.
- **Vector retrieval** for questions that express the same meaning with different wording.

Reciprocal-rank fusion combines the result positions without pretending that lexical and cosine
scores use the same numerical scale.

### Secret Manager

Secret Manager stores the OpenAI and database credentials. Google Cloud injects the secrets into
the server-side Cloud Run process at runtime.

The secrets are not placed in:

- The React frontend bundle.
- Docker build arguments.
- Docker image layers.
- Terraform variables committed to Git.
- Application logs.

### Firebase Authentication

Firebase Authentication signs the user in and issues an ID token. FastAPI verifies that token
before it allows access to protected routes or user-owned conversations.

Authentication answers, "Who is making this request?" Application authorization still happens in
the backend and answers, "May this user access this conversation or operation?"

### OpenAI APIs

The backend uses two OpenAI capabilities:

- The Embeddings API converts questions and passages into 1,536-dimensional vectors.
- The Responses API generates a structured answer from bounded retrieved evidence.

OpenAI is called only from the backend. The generated citation IDs are not trusted until FastAPI
checks them against the active passages.

### Cloud Monitoring

Cloud Logging and Monitoring receive operational telemetry such as request duration, status,
cache result, error category, and model usage metadata. Raw secrets are never logged, and the
logging design avoids storing raw conversation content.

### Complete live request in plain language

```text
The browser sends a question and Firebase token.
The edge routes the request to Cloud Run.
FastAPI verifies the user and checks limits.
FastAPI checks version-aware caches.
FastAPI retrieves evidence from Cloud SQL and pgvector.
OpenAI writes an answer using only that evidence.
FastAPI validates the citations and stores the result.
The browser receives the answer and canonical citations.
```

## 3. Diagram two: Versioned Knowledge Ingestion

This diagram shows how the searchable MTG knowledge is refreshed independently of user chat
requests.

### Cloud Scheduler

Cloud Scheduler sends the daily trigger for the ingestion job. A manual run can also be started by
an authorized operator when necessary.

The scheduler triggers work. It does not parse documents or generate answers.

### Cloud Run ingestion job

The ingestion job performs the update pipeline:

1. Download each allowlisted source over bounded HTTPS.
2. Validate response type, size, and expected structure.
3. Calculate a SHA-256 digest for the downloaded payload.
4. Save an immutable raw snapshot.
5. Parse the source into rules, glossary entries, cards, and rulings.
6. Reuse embeddings for unchanged passages.
7. Embed new or changed passages in bounded batches.
8. Stage the new records without affecting the current live corpus.
9. Validate counts, identities, duplicates, and source relationships.
10. Atomically activate the complete new source version.

If any required step fails, the preceding active version remains available to users.

### The three versioned knowledge resources

| Resource | Purpose |
| --- | --- |
| WotC Comprehensive Rules | General game rules and glossary definitions |
| Oracle cards via Scryfall | Current card wording, identity, faces, and legalities |
| Card rulings via Scryfall | Dated card-specific clarification with source attribution |

These resources are stored with source metadata, fetch time, effective date when available,
content hash, parser version, and active-version status. WotC rules have precedence for general
rules questions. Current Oracle wording determines what a card says. Card rulings provide dated
clarification rather than replacing the Comprehensive Rules.

### Cloud Storage snapshots

Cloud Storage keeps immutable copies of the raw downloaded files. These snapshots provide:

- Evidence of exactly what was ingested.
- A source for debugging parser problems.
- Support for audits and reproducible ingestion.
- Recovery information when a later source version is bad.

The raw snapshot is saved before the database version is activated.

### OpenAI embeddings

The ingestion job sends only passage text that requires a new vector to the Embeddings API.
Unchanged passages can reuse their existing vectors.

The current system uses `text-embedding-3-small` with 1,536 dimensions. Vectors from a different
embedding model must not be mixed with the existing vectors. Changing the model requires a planned
full re-embedding and any required database migration.

### Cloud SQL active corpus

The job first writes into a staged version. After validation, one database transaction switches
the complete version to active.

This prevents users from searching a partially imported rulebook. They see either:

- The preceding complete source version, or
- The newly validated complete source version.

### Complete ingestion flow in plain language

```text
Cloud Scheduler starts the ingestion job.
The job downloads the three MTG resources.
Raw payloads are saved as immutable snapshots.
The job parses the sources at meaningful rules boundaries.
Changed passages receive new embeddings.
The job stages and validates the complete corpus.
Cloud SQL atomically marks the validated version active.
Future chat requests retrieve only from active passages.
```

## 4. How the two diagrams work together

The ingestion flow prepares trusted searchable knowledge. The live request flow consumes that
knowledge.

```text
Versioned sources
    -> ingestion and validation
    -> active Cloud SQL corpus
    -> hybrid retrieval
    -> bounded OpenAI answer
    -> validated citations
```

A user's question does not trigger a live download from WotC or Scryfall. This separation improves
latency, reliability, source consistency, and auditability.

## 5. Scaling and cost notes

The current development Cloud Run configuration uses:

| Setting | Value |
| --- | ---: |
| Minimum API instances | 0 |
| Maximum API instances | 3 |
| Maximum concurrency per instance | 20 |

Three instances do not mean only three users. At the configured ceiling, the API has roughly sixty
in-flight request slots. That number is not a throughput guarantee because OpenAI latency, CPU,
memory, database connections, cache hit rate, and request complexity also affect capacity.

The three-instance limit controls only Cloud Run compute growth. It does not place a hard cap on
OpenAI, Cloud SQL, storage, logging, or networking charges.

## 6. What the visual intentionally omits

The board focuses on runtime and ingestion relationships. It omits some supporting delivery
details to remain readable, including:

- Cloud Build quality gates.
- Artifact Registry image storage.
- Terraform resource provisioning.
- Detailed database tables.
- Internal FastAPI Python modules.
- Evaluation-suite execution.

Those details remain documented in [Architecture.md](Architecture.md),
[architecture-essentials.md](architecture-essentials.md), and [agent.md](agent.md).
