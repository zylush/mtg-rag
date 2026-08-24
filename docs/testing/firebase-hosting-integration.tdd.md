# Firebase Hosting Integration - TDD Evidence

**Source architecture:** [Architecture.md](../architecture/Architecture.md#2-system-context)
**Environment:** `mtg-rules-desk-dev` / `asia-east1`
**Status:** Deployed; real authenticated answer/citations/history flow verified
**Date:** 2026-08-14

## User journeys

- As an operator, I want to enable Google sign-in without committing my public support email
  or any credential.
- As a visitor, I want the deployed PWA to show verified operator contact information and to
  reach the backend through the same Firebase Hosting origin.
- As a returning PWA user, I want a newly deployed release to take control without remaining
  indefinitely on an old cached bundle.
- As a signed-out visitor, I must receive an authentication failure from protected API routes
  even when the request crosses the Hosting-to-Cloud-Run rewrite.

## TDD checkpoints

| Stage | Evidence | Result |
|---|---|---|
| RED | `7316285` - safe Firebase Auth manifest test | Failed because `firebase.auth.json.example` did not exist |
| GREEN | `7be96ae` - placeholder-only Auth template and deployment procedure | 12 runtime-manifest tests passed |
| RED | `b3288c5` - Firebase deploy-cache exclusion test | Failed because `.firebase/` was not ignored |
| GREEN | `4aea7c3` - ignore Firebase CLI cache | Focused manifest test and Ruff passed |
| RED | `3676dad` - deployed support-contact browser contract | Failed against `mailto:support@example.com` |
| GREEN | `7b91f5a` - publish the verified support contact | Focused and full browser tests passed |
| RED | `0854c6c` - automatic PWA release-activation check | Failed because the service worker did not claim existing clients |
| GREEN | `16fb230` - `autoUpdate`, `skipWaiting`, and `clientsClaim` | PWA validation and returning-tab browser QA passed |
| RED | `499b236` - production artifact rejects the local API endpoint | Failed because the emitted bundle contained `http://localhost:8080` |
| GREEN | `f35fcd0` - production API selection is same-origin | Unit, lint, and emitted PWA artifact checks passed; live bundle no longer contains the development endpoint |
| RED | `23e3e42` - mentioned glossary terms require exact retrieval | Live mixed-corpus question missed `target`; Postgres integration test returned no exact glossary passage |
| GREEN | `ba9165e` - exact active glossary retrieval | Database integration test passed; live retest cited the Target glossary entry and Lightning Bolt Oracle text |

## Deployment evidence

- Firebase Auth deployment enabled `google.com`; verification reported the provider enabled,
  a configured OAuth client, and only the two project Hosting domains authorized.
- The short-lived auth deployment file was ignored, used locally, and deleted. The repository
  contains only placeholder values.
- Firebase Hosting deployment serves `/about` successfully and rewrites a signed-out
  `/v1/conversations` request to the Cloud Run API, which returns `401`.
- The live bundle contains the verified support contact and no `OPENAI_API_KEY` or OpenAI
  secret-key pattern.
- The live service worker includes immediate activation and client-claim behavior. A tab that
  had loaded the old release moved to the new hashed bundle after reload.
- Browser console inspection on the public page reported no errors.
- A real signed-in browser request produced a high-confidence answer using OpenAI through
  Cloud Run and cited both `Comprehensive Rules Glossary: Target` and
  `Oracle text: Lightning Bolt`; the saved conversation was visible and openable in History.
- The release bundle is `index-e5hBUfUc.js`, uses the Firebase origin for API calls, and
  contains no `http://localhost:8080`.
- Cloud Run revision `mtg-rag-dev-api-00008-589` serves tested image `api:ba9165e` at 100%
  traffic; Terraform reports no drift across the API and both jobs.

## Acceptance boundary

Automated Firebase-provider configuration, local authenticated E2E coverage, live signed-out
edge behavior, caching behavior, secret boundaries, and the real signed-in
question/citation/history flow are verified. The detailed issue analysis and lessons are in
`docs/operations/INTEGRATION-LESSONS.md`.

Public production launch remains separately blocked by the legal/policy, final-copy,
independent rules-review, and production-drill requirements documented in
`docs/operations/PRODUCTION-AUDIT.md`.
