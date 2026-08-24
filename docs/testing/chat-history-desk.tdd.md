# Resumable chat history desk — TDD evidence

**Date:** 2026-08-25  
**Scope:** Authenticated `/desk` history, conversation continuation, New chat, responsive layout

## Source and user journeys

The journeys were derived directly from the request to make `/desk` behave like a modern chat
workspace while preserving the MTG Rules Desk identity.

- As a signed-in user, I can see saved chats without leaving the desk.
- As a returning user, I can load a saved transcript into the main conversation view.
- As a returning user, I can ask a follow-up that keeps the saved conversation ID and context.
- As a user, I can start a New chat that clears the loaded transcript and sends the next question
  without a conversation ID.
- As a mobile user, I can perform the same actions through a route-backed History sheet.
- As a keyboard user, I can close the History sheet with Escape and recover trigger focus.

## RED and GREEN evidence

| Stage | Command | Result | Evidence |
|---|---|---|---|
| RED | `npm test -- --run src/App.test.tsx` | Expected failure | 2 new journeys failed and 26 existing tests passed. Saved summaries were unavailable until opening the old modal and no New chat control existed. |
| Focused GREEN | `npm test -- --run src/App.test.tsx` | PASS | 28/28 tests passed after saved-chat loading, continuation, and reset behavior were implemented. |
| Full unit/integration | `npm test` | PASS | 12 files and 68 tests passed. |
| Coverage | `npm run test:coverage` | PASS | 92.03% statements, 89.71% branches, 90.57% functions, and 94.68% lines. |
| Chromium browser QA | `npx playwright test tests/e2e/rules-desk.spec.ts --project=chromium` | PASS | 14/14 journeys passed, including the new history-to-new-chat path, axe scans, and release-width screenshots. |
| Cross-browser QA | `npx playwright test tests/e2e/rules-desk.spec.ts` | PASS | 70/70 passed in Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari. |
| Build and PWA | `npm run check:pwa` | PASS | TypeScript/Vite production build and PWA checks passed with 21 precache entries. |
| Static quality | `npm run lint`; `npm audit --audit-level=high` | PASS | ESLint passed and npm reported 0 vulnerabilities. |

## Test specification

| # | What is guaranteed | Test target | Type | Result |
|---|---|---|---|---|
| 1 | Saved summaries appear in the desk history rail | `App.test.tsx: loads a saved chat into the desk` | Integration | PASS |
| 2 | Opening a summary fetches and renders its full transcript | `App.test.tsx` and `rules-desk.spec.ts` | Integration/E2E | PASS |
| 3 | A follow-up sends the loaded conversation ID | `App.test.tsx: continues the same conversation` | Integration | PASS |
| 4 | New chat clears the transcript and omits the conversation ID | `App.test.tsx: starts a new chat` | Integration | PASS |
| 5 | The history rail is persistent on desktop and route-backed/collapsible on mobile | `rules-desk.spec.ts` release-width and drawer journeys | E2E | PASS |
| 6 | History loading, deletion, Back/Forward, Escape, and focus restoration remain functional | `rules-desk.spec.ts` | E2E | PASS |
| 7 | Release widths do not horizontally overflow and reviewed screenshots remain stable | `rules-desk.spec.ts` at 375, 768, and 1440 px | Visual E2E | PASS |
| 8 | Automated WCAG 2.1 A/AA checks find no violations at desktop and mobile widths | `rules-desk.spec.ts: has no detectable WCAG` | Accessibility E2E | PASS |

## Design and visual review

The interaction model follows the familiar two-pane chat pattern, but the visual language remains
specific to the product: dark lacquered surfaces, parchment text, brass rules, and a compact
“rulings ledger” rail. The active conversation is marked like a case-file rule rather than a
generic selected card.

Screenshots were generated and reviewed at 375, 768, and 1440 px. The first browser pass exposed a
sticky composer overlapping citations on mobile; the composer was returned to normal document flow,
the screenshots were regenerated, and the complete browser matrix then passed. Windows and Linux
snapshot files use the same reviewed layout baseline with a 1% pixel allowance for host rendering.

## Checkpoints and known gaps

- RED checkpoint: `2b67108`
- GREEN checkpoint: `e2494e3`
- Refactor and browser-QA checkpoint: `2faa893`
- Automated axe coverage is necessary but not a substitute for a manual screen-reader pass.
- The Linux-named screenshot baselines were normalized from the reviewed Windows captures; Linux CI
  should confirm that the 1% host-rendering allowance is sufficient.
- The production build retains the existing warning that the main JavaScript chunk is slightly over
  500 kB; this change did not add a dependency or materially expand that bundle.
