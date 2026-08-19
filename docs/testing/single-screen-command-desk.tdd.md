# Single-screen command desk TDD evidence

## Source

The user journey was derived from the pasted redesign brief supplied from the local Codex attachment on August 19, 2026.

The brief's claims about a fully offline answer engine, zero latency, zero hallucinations, and 100% certainty were normalized to match the implemented product. The preview says that retrieval is online, the PWA shell is offline-ready, and answers are grounded in retrieved sources with a server-provided confidence level.

## User journeys

- As a player or judge, I can start typing immediately and refocus the rules command with `/` or `Ctrl K`.
- As a user evaluating a complex interaction, I can choose a quick query and submit it through the real ask flow.
- As a user waiting for retrieval, I see an accessible loading state.
- As a user reviewing a ruling, I can distinguish the plain-language answer, assumptions, citations, confidence, and quota.
- As a user sharing a ruling, I can copy the answer with its source links and receive durable feedback.
- As a mobile user, I can use the desk without horizontal overflow and install the PWA shell when the browser supports it.
- As a keyboard user, closing History or Settings restores focus to the control that opened it.

## RED and GREEN evidence

| Guarantee | Test or command | Result | Evidence |
|---|---|---|---|
| Autofocus, keyboard shortcuts, quick-query fill, install control | `npm test -- src/single-screen-shell.test.tsx` | RED then PASS | Initial run: 2 tests failed on missing autofocus and loading status. Final focused run: 2 passed. |
| Loading, grounded answer hierarchy, citation tree, copy feedback | `npm test -- src/single-screen-shell.test.tsx` | PASS | 2 of 2 tests passed. |
| Existing auth, ask, offline, history, settings, deletion, feedback, and safety behavior | `npm test` | PASS | 9 files and 50 tests passed. |
| Drawer focus restoration remains correct | `npm test` | RED then PASS | First full run found the command autofocus stealing restored focus. A one-time autofocus guard fixed it; rerun passed all 50 tests. |
| Release widths do not overflow and retain primary controls | `npx playwright test tests/e2e/single-screen-preview.spec.ts --project=chromium` | PASS | Widths 320, 375, 768, 1024, and 1440 passed. |
| Authenticated flows and automated WCAG checks remain valid | `npx playwright test tests/e2e/rules-desk.spec.ts --project=chromium --grep-invert "stable layouts"` | PASS | 12 Chromium journeys passed, including desktop and mobile axe scans. |
| Installable PWA build remains valid | `npm run check:pwa` | PASS | TypeScript/Vite build completed and PWA checks passed with 21 precache entries. |
| Static quality and coverage gates | `npm run lint`; `npm run test:coverage` | PASS | ESLint passed. Coverage: 91.89% statements, 90.75% branches, 88.59% functions, 95.01% lines. |

## Checkpoints and rollback

- Rollback baseline: `b843c37` on `main`
- RED checkpoint: `89cafe6`
- GREEN checkpoint: `db368a2`
- Preview branch: `preview/single-screen-rag-desk`

The preview branch is local only. It has not been pushed or deployed.

## Known gaps

- There is no approved visual baseline for this redesign, so pixel-level visual regression is inconclusive.
- Desktop, tablet, and mobile screenshots were captured by Playwright, but the current Codex image viewer could not open them because the local Windows sandbox helper is unavailable.
- Automated axe checks cover only part of WCAG. Manual screen-reader review is still recommended before deployment.

