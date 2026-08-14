# OAuth Redirect Allowlist — TDD Evidence

**Status:** GREEN — OAuth callback, authenticated chat, logout, and route protection verified
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

## Applied fix

With explicit operator approval, the existing Google OAuth web client was updated to retain its
fallback and add exactly this callback:

```text
https://mtg-rules-desk-dev.web.app/__/auth/handler
```

The saved client was reopened and showed both project-owned callbacks. No wildcard, client-secret
rotation, provider replacement, backend change, or OpenAI configuration change was made.

## GREEN evidence

- A fresh live sign-in opens Google's account chooser instead of
  `Error 400: redirect_uri_mismatch`.
- The callback list persisted after reopening the Google OAuth client.
- A real Google account completed the provider flow and reached `/desk` without a loop.
- One authenticated rules question returned a rendered answer with two cited sources. The answer
  correctly exposed low confidence because the retrieved passages did not contain the decisive rule;
  this is a retrieval-corpus gap, not an authentication or rendering failure.
- `Sign out` returned to `/`, and a subsequent signed-out visit to `/desk` redirected to `/`.
- `npm run test:coverage`: **7 files and 41/41 tests passed**; coverage remained
  **91.00% statements, 89.20% branches, 88.88% functions, and 94.04% lines**.
- `npm run lint`: passed.
- `npm run check:pwa`: TypeScript, Vite production build, and PWA checks passed.
- `npm audit --audit-level=high`: **0 vulnerabilities**.
- `$env:E2E_PORT='4275'; npm run e2e`: **85/85 passed** across desktop Chromium,
  Firefox, WebKit, mobile Chrome, and mobile Safari.

No account identifier, token, cookie, API key, or client secret was captured in the evidence.

## Acceptance criteria

| ID | Guarantee | Verification | Status |
| --- | --- | --- | --- |
| AC-001 | Google no longer returns `redirect_uri_mismatch` | Clean live popup flow | PASS |
| AC-002 | A real Google account reaches `/desk` once without a loop | Live browser journey | PASS |
| AC-003 | An authenticated chatbot request succeeds | Live `/v1/ask` journey | PASS |
| AC-004 | Logout returns to `/` and `/desk` is protected | Live browser journey + existing E2E | PASS |
| AC-005 | Only the two project-owned callback domains are authorized | Google Auth Platform review | PASS |
| AC-006 | Operations documentation distinguishes both allowlist layers | Documentation review | PASS |

## Rollback

If the added callback causes an unexpected provider regression, remove only the newly added exact
URI. This change does not migrate or delete users and does not alter application secrets.
