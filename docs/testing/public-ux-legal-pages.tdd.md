# Public UX and Legal Pages — TDD Evidence

**Source plan:** `plan.md` from the approved UX implementation discussion.
**Status:** Verified locally
**Date:** 2026-08-12

## User journeys

- As a visitor, I want to understand the citation-first MTG rules desk from a public Welcome page so that I can decide whether to sign in.
- As a visitor, I want to read About, Terms of Service, and Privacy Policy pages without authentication so that product and legal information is available before access.
- As a signed-out visitor, I want `/desk` to send me to Login and return me to the desk after sign-in.
- As an authenticated player, I want the existing chat, citations, quota, history, feedback, deletion, and installation flows to remain available.

## TDD checkpoints

| Stage | Evidence | Result |
|---|---|---|
| RED | `b576936` — `npm run test -- src/App.test.tsx` after adding route/public-page tests | 3 intended failures: Welcome preview, About/legal route, protected-route redirect |
| GREEN | `npm run test:coverage -- --maxWorkers=1` | 2 test files, 14 tests passed; 91.77% statements, 89.38% branches, 87.87% functions, 93.38% lines |
| Browser | `npm run e2e` | 11 Playwright tests passed |
| Static quality | `npm run lint` | Passed with no warnings or errors |
| Production build | `npm run build` | Vite production build passed; 17 PWA precache entries generated |
| PWA | `npm run check:pwa` | Passed |

## Test specification

| # | Guarantee | Test evidence | Type | Result |
|---|---|---|---|---|
| 1 | Signed-out visitors see the Welcome page and static source preview | `src/App.test.tsx` and `tests/e2e/public-pages.spec.ts` | unit/E2E | PASS |
| 2 | Welcome preview does not require live API access | `src/App.test.tsx` fake API assertions | unit | PASS |
| 3 | About, Terms, and Privacy are public routes | `src/App.test.tsx` and `tests/e2e/public-pages.spec.ts` | unit/E2E | PASS |
| 4 | Terms and Privacy show structured pending-review content instead of pretending to be final legal advice | `src/App.test.tsx`, public-page E2E assertions | unit/E2E | PASS |
| 5 | `/desk` redirects signed-out users to Login and sign-in returns to `/desk` | `tests/e2e/public-pages.spec.ts` | E2E | PASS |
| 6 | Existing question, citation, quota, history, account deletion, feedback, and install flows remain green | `tests/e2e/rules-desk.spec.ts` | E2E | PASS |
| 7 | Public and authenticated routes have no detected WCAG 2.1 AA violations | `tests/e2e/public-pages.spec.ts`, `tests/e2e/rules-desk.spec.ts` | accessibility/E2E | PASS |
| 8 | Public and authenticated layouts have no horizontal overflow at release breakpoints | `tests/e2e/rules-desk.spec.ts` | responsive/E2E | PASS |
| 9 | Router preserves modified clicks and normalizes supported/unknown paths | `src/routing.test.tsx` | unit | PASS |

## Intentional gaps

- Terms of Service and Privacy Policy remain structured outlines pending operator/legal review; final jurisdiction, retention, contact, effective dates, and contractual wording are not invented by this change.
- Firebase popup failure is represented in the Login component, but the browser harness does not simulate a popup-blocked provider response.
- No backend consent-recording schema was added. If legal review requires recorded consent, that is a separate authentication/data change.
- The repository’s existing WotC access-policy question remains a public-launch blocker.

## Visual evidence

The authenticated visual baselines at 768px and 1440px were intentionally regenerated after adding the About/Legal header links. The 375px baseline was unchanged.
