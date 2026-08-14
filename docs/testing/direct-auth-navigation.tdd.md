# Direct Authentication and Logout Navigation — TDD Evidence

**Status:** GREEN, deployed to the Firebase development site and live-verified
**Date:** 2026-08-14
**Scope:** `docs/plan.md` Revision 4

## User journeys

- As a signed-out visitor, I can start Google authentication from the first screen without being
  sent to a second app-owned sign-in screen.
- As a signed-out visitor who opens a protected desk URL, I return to the first screen and can
  authenticate there.
- As a signed-in user, I return to the first screen after intentional logout or account deletion.
- As a keyboard user, I can reach a public sign-in control in the visible tab order.

## RED

The refined regression target was:

```text
cd frontend
npm test -- --run src/App.test.tsx src/routing.test.tsx src/route-meta.test.ts src/pwa-navigation.test.ts
```

Observed result: **2 test files failed, 2 passed; 5 tests failed and 25 passed**. The failures
proved that sign-in was still a link to an intermediate `/auth` screen, protected access ended on
that screen, first-screen pending/error states did not exist, and legacy auth URLs did not return
home. RED checkpoint: `1951679`.

An earlier `/auth` route interpretation was checkpointed in `6e5f5c0` and `85987d6`, then
superseded before deployment when the click-path audit showed that the unwanted behavior was the
extra app-owned screen itself.

## GREEN

The same focused target passed **30/30 tests across 4 files** after the first-screen controls were
wired directly to the Firebase auth port and intentional sign-out was separated from the protected
route guard. GREEN/refactor checkpoint: `7c39f2a`.

Full verification:

```text
npm run test:coverage
npm run lint
npm run check:pwa
npm audit --audit-level=high
$env:E2E_PORT='4274'; npm run e2e
```

- Unit/integration: **41/41 passed**.
- Coverage: **91.00% statements, 89.20% branches, 88.88% functions, 94.04% lines**.
- Playwright: **85/85 passed** across desktop Chromium, Firefox, WebKit, mobile Chrome, and mobile
  Safari.
- Lint, TypeScript, Vite production build, PWA/secret checks: passed.
- Dependency audit: **0 vulnerabilities**.

The first browser run passed all direct-auth and logout assertions but exposed a stale keyboard
expectation that skipped the public About link. The test was corrected to verify the actual order:
brand, About, header Sign in. The complete 85-case rerun passed.

## Deployment and live verification

Firebase Hosting deployed 16 files successfully to
`https://mtg-rules-desk-dev.web.app` on 2026-08-14. Direct hosting checks confirmed the active
hashed application bundle and a `200` response from Firebase's reserved `/__/auth/handler` path.

Post-deployment browser QA, performed without entering a Google account, confirmed:

- the public header and hero sign-in controls render as buttons rather than `/login` links;
- legacy `/login` and `/auth` URLs normalize to `/`;
- signed-out `/desk` access returns to `/`; and
- the first screen remains available after each redirect.

The QA browser initially displayed its previously installed PWA shell. Clearing that isolated test
browser's old cache exposed the new release. The generated worker already uses `autoUpdate`,
`skipWaiting`, `clientsClaim`, and outdated-cache cleanup; an existing open tab may require one
refresh after deployment, but no manual site-data reset is part of normal operation.

## Test specification

| Guarantee | Evidence | Type | Result |
| --- | --- | --- | --- |
| First-screen sign-in calls the auth port and reaches `/desk` after success | `App.test.tsx`: direct Firebase auth | Integration | PASS |
| Pending and provider-failure states remain visible on the first screen | `App.test.tsx`: pending and failure cases | Integration | PASS |
| Signed-out protected access returns to `/` | `App.test.tsx` and `public-pages.spec.ts` | Integration/E2E | PASS |
| Intentional logout returns to `/`, not an auth screen | `App.test.tsx` and `rules-desk.spec.ts` | Integration/E2E | PASS |
| Legacy `/login` and `/auth` URLs normalize to `/` | `routing.test.tsx` | Unit | PASS |
| Direct sign-in and logout work across five desktop/mobile browser profiles | Playwright 85-case matrix | E2E | PASS |

## Known gap

Automated tests use the deterministic auth harness, and live QA deliberately did not select a real
Google account. The remaining operator check is to click the live first-screen control, complete
Google authentication, then log out and confirm the app returns to `/`. Do not capture account
cookies or ID tokens.
