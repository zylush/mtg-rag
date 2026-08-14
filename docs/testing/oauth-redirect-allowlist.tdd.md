# OAuth Redirect Allowlist — TDD Evidence

**Status:** RED — live Google OAuth callback rejected; external fix awaiting approval
**Date:** 2026-08-14
**Source:** User-provided OAuth remediation plan and live failure report

## User journey

As a signed-out visitor, I can start Google authentication from the public first screen, complete
the provider flow, reach `/desk`, use the authenticated chatbot, and return to `/` after logout.

## Click-path trace

1. Public `Sign in with Google` calls the app's Firebase auth port.
2. The auth port calls Firebase `signInWithPopup` with the Google provider.
3. Firebase opens the same-origin helper at
   `https://mtg-rules-desk-dev.web.app/__/auth/handler`.
4. The helper sends the configured Google OAuth client and that exact callback to Google.
5. Google rejects the callback before account selection with `Error 400: redirect_uri_mismatch`.

The application route and Firebase helper are both reachable. The failure is in the Google OAuth
client's external authorized-redirect configuration, not in React navigation or the service-worker
fallback.

## RED evidence

- Firebase Authentication lists both project Hosting domains as authorized.
- The Google sign-in provider is enabled.
- The OAuth client configured in Firebase matches the client inspected in Google Auth Platform.
- That client currently authorizes only
  `https://mtg-rules-desk-dev.firebaseapp.com/__/auth/handler`.
- The live popup reports `Error 400: redirect_uri_mismatch` for
  `https://mtg-rules-desk-dev.web.app/__/auth/handler`.
- No tokens, cookies, API keys, or client secrets are recorded in this report.

Focused local baseline:

```text
cd frontend
npm test -- --run src/firebase-config.test.ts src/App.test.tsx
```

Result: **2 files passed; 26/26 tests passed**. This proves the local auth adapter and navigation
contracts are green while the live provider configuration remains RED.

## Minimal fix

Add exactly this callback to the existing Google OAuth web client and retain the existing fallback:

```text
https://mtg-rules-desk-dev.web.app/__/auth/handler
```

No wildcard, client-secret rotation, provider replacement, backend change, or OpenAI configuration
change is required.

## Acceptance criteria

| ID | Guarantee | Verification | Status |
| --- | --- | --- | --- |
| AC-001 | Google no longer returns `redirect_uri_mismatch` | Clean live popup flow | RED |
| AC-002 | A real Google account reaches `/desk` once without a loop | Live browser journey | Pending |
| AC-003 | An authenticated chatbot request succeeds | Live `/v1/ask` journey | Pending |
| AC-004 | Logout returns to `/` and `/desk` is protected | Live browser journey + existing E2E | Pending |
| AC-005 | Only the two project-owned callback domains are authorized | Google Auth Platform review | RED |
| AC-006 | Operations documentation distinguishes both allowlist layers | Documentation review | Pending |

## Rollback

If the added callback causes an unexpected provider regression, remove only the newly added exact
URI. This change does not migrate or delete users and does not alter application secrets.
