# Security model

## Data and trust boundaries

The browser holds a Firebase ID token and sends rules questions to the API. It never
receives an OpenAI key, database credential, service-account credential, or direct
database access. The API verifies the token, enforces request shape and quotas, then
calls PostgreSQL and OpenAI. The ingestion job alone fetches WotC and Scryfall sources
and writes versioned corpus records and GCS snapshots.

Questions, answers, citations, feedback, account IDs, and Firebase identifiers are
private application data. Source rules and card data are public upstream content.
Secrets, bearer tokens, and database connection strings are restricted credentials.

## Implemented controls

- Firebase token verification is mandatory outside the explicit local-development
  bypass; verified identity determines all user-owned database access.
- API schemas reject oversized and malformed input. SQL access uses SQLAlchemy bound
  parameters. Retrieved text is treated as untrusted evidence, not executable
  instructions.
- System and developer instructions tell the model to ignore instructions inside
  retrieved text. The citation validator rejects invented IDs and repairs once before
  abstaining.
- Per-user daily quotas are incremented transactionally in PostgreSQL. Cloud Run also
  caps instance count and concurrency to limit cost amplification.
- The API's CORS policy accepts one exact HTTPS frontend origin. Cloud Run ingress is
  load-balancer-only, and Cloud Armor applies the regional allowlist before requests
  reach it.
- Runtime containers use an unprivileged user. Build and runtime dependencies are
  pinned, CI performs secret scanning, Python and npm dependency audits, a non-root
  image inspection, and a digest-pinned HIGH/CRITICAL Trivy scan.
- Secret Manager injects secrets at runtime. Terraform state contains secret resource
  names but not secret values. Service accounts are separated by responsibility and
  granted only their required bucket, secret, database-connect, or invocation roles.
- Production deployments pin reviewed numeric Secret Manager versions for the OpenAI
  credential and database URL; the moving `latest` alias is allowed only outside
  production.
- The API service account receives a project custom role containing only
  `firebaseauth.users.get` for revoked-token checks and `firebaseauth.users.delete` for
  the account-deletion flow; ingestion has no Firebase user-management permission.
- PostgreSQL has automated backups, point-in-time recovery in production, encrypted
  transport requirements, and private Unix-socket connectivity from Cloud Run.
- Account deletion removes application-owned rows and then requests Firebase identity
  deletion. Errors are normalized and request IDs are returned for support without
  exposing internals.
- Logs and cache telemetry are content-free. They exclude questions, answers, retrieved
  passages, Authorization headers, and credentials.

## Verification

For every release, run the commands in `README.md` and preserve Cloud Build evidence.
In addition, verify:

- unauthenticated, invalid-token, cross-user history, quota-exhausted, deletion, and
  oversized-request cases;
- prompt-injection and citation-forgery cases in the versioned eval suite;
- `docker inspect` reports a non-root runtime user and no secret-valued environment
  entries;
- `terraform plan` creates no unintended public IAM, firewall, database IP, or secret
  versions;
- Firebase authorized domains exactly match intended origins, and the selected Google OAuth
  client authorizes only the exact project-owned `/__/auth/handler` callbacks;
- deletion is tested against both the database and Firebase project;
- production alerts reach their named responders.

## Residual risk and required decisions

Application-row deletion and Firebase identity deletion cannot be one distributed
transaction. If identity deletion fails after database deletion, retry the identity
operation using the request ID and incident record; the user data is already
unavailable to the application.

Semantic cache matching is probabilistic. Its key includes corpus versions, model,
prompt version, and locale; negative eval pairs must show zero unsafe reuse before
release. Cache hits still pass citation validation.

Geographic filtering is an access policy, not proof of residency or nationality.
VPNs, provider routing, upstream service locations, logs, backups, and support access
must be covered by the operator's privacy and legal review.

The repository now contains implementation-aligned privacy, Terms, attribution, and support
copy for local review, but that copy is not legal approval or a data-processing agreement.
Public launch is blocked until the operator publishes reviewed documents, records the WotC
policy/source-use decision, completes the Scryfall usage review, and obtains independent
rules-expert approval.

## Vulnerability handling

Do not include questions, answers, tokens, or secrets in a report. Record the affected
commit and image digest, request IDs, source-version IDs, severity, reproducibility, and
containment action. Rotate exposed credentials, roll back immutable images or corpus
versions, and rerun the complete security and evaluation gates before restoration.
