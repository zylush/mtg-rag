# Rules-grid surfaces TDD evidence

## Source

The journeys were derived from the approved UI plan: add a restrained MTG rules-grid backdrop to Welcome and Desk, clarify the question console, strengthen the citation/evidence rail, and preserve responsive and reduced-motion behavior.

## User journeys

- As a visitor, I see a decorative rules-grid texture that never captures focus or pointer input.
- As a signed-in user, I can identify the rules query console and its retrieval-ready state before asking a question.
- As a user reviewing an answer, I can find a clear source trail without losing existing citations, feedback, copy, or Markdown behavior.
- As a mobile or reduced-motion user, the new surfaces remain usable, readable, and free of horizontal overflow.

## RED and GREEN evidence

| Guarantee | Test or command | Result | Evidence |
|---|---|---|---|
| Backdrop accessibility and public/desk variants | `npm test -- --run src/RulesGridBackdrop.test.tsx src/PublicPages.warm.test.tsx src/App.test.tsx` | RED then PASS | RED run failed because the component and integration hooks were absent; final focused run passed 47 tests. |
| Existing application behavior remains intact | `npm test` | PASS | 13 test files and 84 tests passed. |
| Static quality and production build | `npm run lint`; `npm run build` | PASS | ESLint passed; Vite build completed with the existing bundle-size warning only. |
| Coverage gate | `npm run test:coverage` | PASS | 90.34% statements, 88.66% branches, 88.08% functions, 93.15% lines. |
| Responsive desk/public flows, axe scans, keyboard behavior, and visual baselines | `npx playwright test tests/e2e/public-pages.spec.ts tests/e2e/single-screen-preview.spec.ts tests/e2e/rules-desk.spec.ts --project=chromium` | PASS | 29 Chromium tests passed; updated 375/768/1440 desk baselines reflect the intentional console header. |
| Cross-browser public accessibility and narrow-width BETA label | `npx playwright test tests/e2e/public-pages.spec.ts --project=firefox --project=mobile-chrome --project=mobile-safari --grep "shows a public welcome|public pages have no detectable"` | PASS | 6 focused tests passed across Firefox, mobile Chromium, and mobile Safari with reduced-motion axe stabilization. |

## Implementation checkpoint

- RED checkpoint: `09c4b7f` (`test: add red coverage for rules grid surfaces`)
- GREEN implementation checkpoint: `4073b7f` (`feat: add rules grid surfaces to welcome and desk`)
- Validation/baseline checkpoint: `d2966cd` (`test: stabilize responsive rules grid validation`)

## Known gaps

- Automated axe checks do not replace a manual screen-reader pass.
- Visual baselines are normalized from the current Chromium environment; Linux CI should rerun the same snapshot suite as part of delivery.
