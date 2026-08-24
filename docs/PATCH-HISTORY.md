# Patch history

This is the repository’s complete chronological patch ledger. It records every commit reachable from the configured Git refs, including feature work, tests, refactors, documentation, merges, and release qualification. Keeping the ledger in the repository makes the applied changes auditable without relying on a local Git UI.

**Snapshot:** 162 commits, 2026-08-12 through 2026-08-25
**Branch at capture:** `preview/single-screen-rag-desk`
**HEAD at capture:** `49873ff`
**Remote:** https://github.com/zylush/mtg-rag.git

The website’s [Patch history](https://mtg-rules-desk-dev.web.app/patch-history) view presents
versioned releases as concise bullet notes with independent section and per-release pagination.

## Release overview

| Period | Patch focus |
| --- | --- |
| 2026-08-12 | Established the tested RAG foundation: domain contracts, immutable corpus persistence, grounded Responses API behavior, authentication boundaries, local runtime, Postgres ownership/atomicity, retrieval, ingestion, and supporting tests. |
| 2026-08-13 | Hardened deployment and cloud integration, including Cloud SQL/Run/Build/IAM, Firebase hosting, environment handling, ingestion safety, and operational documentation. |
| 2026-08-14–18 | Expanded platform behavior and assurance around routing, auth, SEO, API/hosting integration, privacy, security, and operational readiness. |
| 2026-08-19 | Delivered the single-screen Rules Desk, responsive/PWA behavior, warm sign-in/install experience, branded assets, browser verification, and preview deployment. |
| 2026-08-25 | Qualified the development release, added resumable `/desk` chat history, and published versioned patch notes with concise bullets, release pagination, and oldest/newest sorting. |

## Current release checkpoint

- Live preview: [mtg-rules-desk-dev.web.app](https://mtg-rules-desk-dev.web.app)
- Website release notes: [mtg-rules-desk-dev.web.app/patch-history](https://mtg-rules-desk-dev.web.app/patch-history)
- Latest feature evidence: [resumable chat history desk TDD record](testing/chat-history-desk.tdd.md)
- Deployment record: [operations runbook](operations/OPERATIONS.md)
- The TDD record captures the automated verification results and the remaining manual screen-reader/Linux visual-baseline follow-ups.

## Complete commit ledger

The entries below are ordered oldest-first. To regenerate a fresh snapshot, run:

```text
git log --all --reverse --date=short --pretty=format:"%h|%ad|%an|%s"
```

### 2026-08-12

- `a582be5` — Fare Estimator — feat: establish tested RAG domain foundation
- `5ad5111` — Fare Estimator — test: define persistence and ingestion safety contracts
- `1d68547` — Fare Estimator — feat: add immutable corpus persistence contracts
- `f73c0e8` — Fare Estimator — test: define grounded Responses API behavior
- `cd86b49` — Fare Estimator — feat: add grounded Responses API adapter
- `e3ab650` — Fare Estimator — test: define authenticated API boundary
- `6caf31b` — Fare Estimator — feat: add authenticated FastAPI contract
- `e5f069d` — Fare Estimator — test: define local runtime and migration contracts
- `e4b2462` — Fare Estimator — feat: add reproducible Python and Postgres runtime
- `eb84e93` — Fare Estimator — test: define Postgres atomicity and ownership guarantees
- `8ea00c6` — Fare Estimator — feat: enforce Postgres atomicity and history ownership
- `09db0a4` — Fare Estimator — test: define hybrid retrieval orchestration
- `62244ad` — Fare Estimator — feat: add bounded hybrid retrieval orchestration
- `9967f33` — Fare Estimator — test: require rollback-safe versioned card identities
- `1d0a5a8` — Fare Estimator — fix: preserve cards across corpus versions
- `d5bd874` — Fare Estimator — test: define Postgres hybrid retrieval behavior
- `c16fca0` — Fare Estimator — feat: add Postgres exact lexical and vector retrieval
- `db902ec` — Fare Estimator — test: define semantic cache safety boundaries
- `0b95c4b` — Fare Estimator — feat: add version-safe Postgres semantic cache
- `b4211a6` — Fare Estimator — test: define atomic ingestion pipeline order
- `fc567c7` — Fare Estimator — feat: add idempotent staged ingestion pipeline
- `cb817d4` — Fare Estimator — test: define corpus documents and immutable snapshots
- `ede43c7` — Fare Estimator — feat: add versioned corpus builders and GCS snapshots
- `6ae70a2` — Fare Estimator — test: define concrete Postgres corpus staging
- `2fc9181` — Fare Estimator — feat: add concrete Postgres corpus staging
- `5c4108a` — Fare Estimator — test: define ask quota cache and failure ordering
- `39441f7` — Fare Estimator — feat: orchestrate ask cache retrieval quota and history
- `96775f7` — Fare Estimator — test: define atomic answer and deletion persistence
- `2e40d84` — Fare Estimator — feat: atomically persist answers feedback and deletion
- `51df338` — Fare Estimator — test: define active corpus context and embedding reuse
- `1fdbf92` — Fare Estimator — feat: bind cache context to active corpus versions
- `6412a82` — Fare Estimator — test: define production service graph and route boundary
- `7e29999` — Fare Estimator — feat: wire production API service graph
- `38f7f52` — Fare Estimator — test: define ingestion job source contracts
- `65a5751` — Fare Estimator — feat: add scheduled corpus ingestion job
- `1f11505` — Fare Estimator — test: define API resilience boundaries
- `4fbce54` — Fare Estimator — test: pin OpenAI runtime observability contract
- `eb454e1` — Fare Estimator — feat: harden API runtime boundaries
- `79588d3` — Fare Estimator — test: define content-free answer telemetry
- `df2d4f8` — Fare Estimator — feat: log content-free answer telemetry
- `27b6ee3` — Fare Estimator — chore: pass backend quality gates
- `2e487b6` — Fare Estimator — test: define frontend product contracts
- `cb3be7c` — Fare Estimator — feat: build authenticated rules desk PWA
- `2ae3726` — Fare Estimator — test: define browser acceptance contracts
- `e714abe` — Fare Estimator — test: verify PWA in real browser
- `b42e9ef` — Fare Estimator — feat: complete production delivery plan
- `b576936` — Fare Estimator — test: add public route and legal page coverage
- `1bee164` — Fare Estimator — feat: add public ux and legal pages
- `2addab0` — Fare Estimator — fix: show login progress state
- `927f844` — Fare Estimator — test: require luna generation model default
- `cb92681` — Fare Estimator — fix: switch generation model to luna

### 2026-08-13

- `9a0c28c` — Fare Estimator — fix: grant API Firebase account deletion permission
- `afe6bcc` — Fare Estimator — docs: record Firebase IAM integration evidence
- `08bcf1a` — Fare Estimator — test: require pinned production secret versions
- `deac7ed` — Fare Estimator — fix: pin production secret versions
- `7a29177` — Fare Estimator — test: cover Firebase Hosting proxy delivery
- `d7a70b2` — Fare Estimator — fix: add Firebase Hosting proxy delivery
- `188173c` — Fare Estimator — test: capture Cloud SQL edition requirement
- `63f12e3` — Fare Estimator — fix: select supported Cloud SQL edition
- `6eb6428` — Fare Estimator — fix: restrict Cloud Build upload scope
- `9f7eb6e` — Fare Estimator — test: cover Cloud Build script upload boundary
- `86e8eab` — Fare Estimator — fix: retain frontend build scripts in Cloud Build
- `42d0c61` — Fare Estimator — test: require uploadable Cloud Build policy
- `19e823d` — Fare Estimator — test: prevent nested Cloud Build ignore includes
- `5f4e8bb` — Fare Estimator — fix: make Cloud Build upload policy CI-verifiable
- `d2c5d6c` — Fare Estimator — fix: scope Cloud Build policy test to uploaded source
- `0732836` — Fare Estimator — test: add Linux visual regression baselines
- `4662847` — Fare Estimator — test: require migration frontend origin
- `3f74b53` — Fare Estimator — fix: configure migration job frontend origin
- `9f617e6` — Fare Estimator — test: reproduce ingestion retry failures
- `82f6d7b` — Fare Estimator — fix: make corpus ingestion retries safe
- `6177571` — Fare Estimator — test: require batched ingestion embeddings
- `a45e6a6` — Fare Estimator — fix: batch corpus embedding requests
- `5b17199` — Fare Estimator — docs: record ingestion recovery TDD evidence
- `7d56c12` — Fare Estimator — test: reproduce blank Scryfall ruling comments
- `32e0f52` — Fare Estimator — fix: ignore blank Scryfall rulings
- `2b61f50` — Fare Estimator — docs: record rulings import TDD evidence
- `d7bc64f` — Fare Estimator — test: require bounded ingestion staging
- `5005e52` — Fare Estimator — fix: bound ingestion staging memory
- `d2ee03a` — Fare Estimator — docs: record bounded staging TDD evidence
- `7316285` — Fare Estimator — test: require safe Firebase auth template
- `7be96ae` — Fare Estimator — feat: add safe Firebase auth deployment config
- `3676dad` — Fare Estimator — test: require deployed support contact
- `7b91f5a` — Fare Estimator — fix: publish verified support contact
- `b3288c5` — Fare Estimator — test: require Firebase cache exclusion
- `4aea7c3` — Fare Estimator — chore: ignore Firebase deploy cache
- `0854c6c` — Fare Estimator — test: require automatic PWA release activation
- `16fb230` — Fare Estimator — fix: activate PWA releases automatically
- `bd44b3a` — Fare Estimator — docs: record live Firebase integration evidence
- `d2fe2d1` — Fare Estimator — test: require Cloud Build manifest dependencies
- `3dfe7c2` — Fare Estimator — fix: upload manifest policy to Cloud Build
- `91dbe73` — Fare Estimator — docs: normalize integration evidence formatting
- `9f85d68` — Fare Estimator — test: require actionable client request errors
- `e1da69d` — Fare Estimator — fix: surface safe client request failures
- `76f6189` — Fare Estimator — test: require Firebase revocation-read permission
- `d685eaf` — Fare Estimator — fix: allow Firebase revocation checks
- `4599028` — Fare Estimator — test: require null-safe dev budget validation
- `675511a` — Fare Estimator — fix: validate optional dev budget safely
- `61d9c47` — Fare Estimator — test: require inactive corpus restaging
- `2142cb0` — Fare Estimator — fix: restage inactive corpus snapshots
- `449f6f3` — Fare Estimator — test: require canonical ruling deduplication
- `a9b9420` — Fare Estimator — fix: deduplicate canonical rulings

### 2026-08-14

- `1c90094` — Fare Estimator — test: require supported ruling filtering
- `c934480` — Fare Estimator — fix: filter unsupported rulings before embedding
- `ee80157` — Fare Estimator — test: exclude local terraform plans from builds
- `8c26802` — Fare Estimator — fix: exclude local terraform plans from builds
- `499b236` — Fare Estimator — test: reject localhost production API origins
- `f35fcd0` — Fare Estimator — fix: use same-origin API in production
- `23e3e42` — Fare Estimator — test: require exact glossary term retrieval
- `ba9165e` — Fare Estimator — fix: retrieve mentioned glossary terms exactly
- `f59f2ac` — Fare Estimator — test: require hosted health proxy
- `bc92528` — Fare Estimator — fix: proxy hosted health checks
- `264ba24` — Fare Estimator — test: require base-path Firebase health glob
- `6877a7e` — Fare Estimator — fix: match hosted health base path
- `f25415c` — Fare Estimator — test: require explicit health route regex
- `d3f6615` — Fare Estimator — fix: proxy exact hosted health path
- `2baa874` — Fare Estimator — docs: clarify health probe boundary
- `b8d96f0` — Fare Estimator — docs: record integration lessons and live evidence
- `d7b6b7b` — Fare Estimator — docs: normalize integration evidence encoding
- `182f3ae` — Fare Estimator — test: define navigation and SEO contracts
- `44290dc` — Fare Estimator — feat: refine responsive desk navigation
- `ac45891` — Fare Estimator — docs: record frontend integration lessons
- `06a0f9d` — Fare Estimator — docs: move plans under docs
- `f94e8c2` — Fare Estimator — test: reproduce Firebase sign-in loop
- `24cefcc` — Fare Estimator — fix: keep Firebase sign-in callbacks same-origin
- `6e5f5c0` — Fare Estimator — test: reproduce auth and logout route outcomes
- `85987d6` — Fare Estimator — fix: route auth and logout to intended screens
- `1951679` — Fare Estimator — test: require direct auth from the first screen
- `7c39f2a` — Fare Estimator — refactor: invoke Firebase auth from public screens
- `247157d` — Fare Estimator — docs: record direct auth deployment evidence
- `c9f3490` — Fare Estimator — test: capture live OAuth redirect mismatch
- `0361efb` — Fare Estimator — docs: distinguish OAuth callback allowlists
- `6f590c7` — Fare Estimator — fix: complete OAuth redirect recovery

### 2026-08-15

- `8b00bfe` — Fare Estimator — docs: consolidate product and architecture guides

### 2026-08-17

- `b025225` — Fare Estimator — test: add privacy policy content expectations
- `c92a40d` — Fare Estimator — feat: publish implementation-aligned privacy policy
- `e94d678` — Fare Estimator — docs: record privacy policy verification
- `0c45a02` — Fare Estimator — test: define SEO metadata and crawler contracts
- `cf33213` — Fare Estimator — feat: generate production-safe SEO metadata
- `b843c37` — Fare Estimator — docs: record SEO verification

### 2026-08-19

- `89cafe6` — Fare Estimator — test(ui): define command desk interaction contract
- `db368a2` — Fare Estimator — feat(ui): build single-screen rules command desk
- `e69861a` — Fare Estimator — test(ui): verify responsive command desk preview
- `92208b2` — Fare Estimator — test: add warm sign-in and install dismissal reproducers
- `ac9dbae` — Fare Estimator — feat: implement warm sign-in and dismissible install prompt
- `70d637d` — Fare Estimator — test: enforce warm PWA brand assets
- `39dc022` — Fare Estimator — feat: align favicon and PWA assets with warm brand
- `604dfb2` — Fare Estimator — test: finalize warm sign-in verification
- `7c612c8` — Fare Estimator — docs: record warm preview deployment
- `af73877` — Zylush — Merge pull request #1 from zylush/preview/single-screen-rag-desk

### 2026-08-25

- `f36522d` — Fare Estimator — feat: qualify development rules desk release
- `2b67108` — Fare Estimator — test: add chat history continuation journeys
- `e2494e3` — Fare Estimator — feat: add resumable chat history desk
- `2faa893` — Fare Estimator — refactor: refine responsive chat history layout
- `3e50395` — Fare Estimator — docs: record chat history verification checkpoints
- `131f036` — Fare Estimator — docs: add complete patch history
- `4b1479c` — Fare Estimator — test: define website patch history journey
- `76ae629` — Fare Estimator — feat: publish concise website patch history
- `f3f28b7` — Fare Estimator — test: define patch history compaction controls
- `8251f6e` — Fare Estimator — feat: compact and sort patch history dates
- `1052170` — Fare Estimator — test: define versioned patch notes pagination
- `49873ff` — Fare Estimator — feat: add versioned patch notes
