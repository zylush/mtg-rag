# Warm Sign-In Redesign Plan

Status: implemented and locally verified; preview deployment awaits visual approval
Surface: unauthenticated welcome and sign-in screen, shared brand assets, install prompt
Working title: Ember Archive

## Outcome

Redesign the first screen so MTG Rules Desk feels like a focused tabletop rules reference rather than a generic AI product. The welcome page will use a warm, original visual language, explain the citation-first value quickly, and preserve the existing Google authentication flow. Shared brand assets and selected signed-in surfaces will use the same visual tokens so the transition after authentication feels intentional.

The Add to Home Screen banner will gain an accessible close control. Dismissing it will hide the passive banner for the current browser session without discarding the browser's install capability.

## Current-State Findings

- The welcome page already has a useful hierarchy: promise, sign-in action, example answer, trust points, limitations, and legal links.
- The current brand mark is a generic letter `R` in a blue circle. The HTML theme color and some PWA colors do not match the current application styling.
- The mobile install banner offers only the install action. Users cannot dismiss it.
- Authentication behavior, error recovery, legal routes, and backend calls are separate concerns and should remain unchanged.
- The shared visual language must work at mobile and desktop widths and must not rely on external artwork or official MTG symbols.

## Scope

### Included

- Redesign the unauthenticated `/` screen and its shared public header/footer styling.
- Create a reusable, original MTG Rules Desk brand mark.
- Replace blue, cyan, violet, and neon brand treatments with the warm palette below.
- Harmonize the most visible shared brand tokens in the signed-in shell without changing its information architecture.
- Regenerate favicon and PWA icon variants from one master SVG.
- Add a close button and session-scoped dismissal behavior to the mobile Add to Home Screen banner.
- Add responsive, accessibility, unit, and browser tests for the changed behavior.

### Excluded

- Changes to Firebase authentication, redirect handling, the RAG backend, or OpenAI integration.
- Rewriting Privacy, Terms, or About content.
- Official Magic logos, mana symbols, card art, or close copies of Wizards card frames.
- New analytics, accounts, onboarding steps, deployment, or publishing.

## Visual Direction

### Concept: Ember Archive

The screen should resemble a well-kept judge's reference desk at the end of a game night: dark wood, ink, parchment, brass tabs, and a small ember accent. It should feel knowledgeable and tactile without becoming fantasy-themed or decorative.

The distinctive visual element is a **ruling ledger**. It presents one sample rules question, a concise answer, and attached source tabs as slightly layered reference cards. Fine rule lines and card-edge depth can add texture, but the interface remains flat enough to read quickly.

### Color Tokens

| Role | Token | Hex | Use |
| --- | --- | --- | --- |
| Page background | Obsidian ink | `#17120F` | Main dark canvas and browser theme |
| Raised surface | Dark walnut | `#2A1B14` | Header, ledger, and elevated panels |
| Primary text | Parchment | `#F0E1BF` | Headlines and high-emphasis text |
| Secondary text | Warm vellum | `#CBB995` | Body copy and supporting labels |
| Primary action | Ember red | `#B84A2F` | Sign-in button, active state, focus accent |
| Citation accent | Old gold | `#C89B4B` | Rule references, source tabs, dividers |
| Success/status | Moss | `#667A58` | Online and successful states only |
| Border | Ash brown | `#5B4030` | Dividers, inputs, and quiet outlines |

Implementation must verify WCAG AA contrast for text and interactive states. Ember red and old gold are accents, not large background fills. Gradients are not part of this direction.

### Typography and Texture

- Use the existing system sans stack for body copy and controls to avoid a new network font dependency.
- Use a restrained local serif stack such as `Georgia, 'Times New Roman', serif` for the hero title and major editorial headings.
- Use the existing mono stack for rule numbers, card names in citations, and source metadata.
- Add texture only through CSS lines, borders, shadows, and subtle noise if it remains legible. Do not add downloadable background artwork.
- Keep motion limited to short state transitions and honor `prefers-reduced-motion`.

## Screen Structure

### Desktop

1. A compact header with the new mark, product name, About link, and secondary Sign in action.
2. A two-column hero:
   - Left: short eyebrow, direct headline, supporting sentence, primary Google sign-in button, and a small trust note.
   - Right: the ruling ledger showing Question, Answer, and Sources in one readable example.
3. A slim source-trust rail for Comprehensive Rules, Oracle text, and official rulings.
4. A concise limitations note and the existing legal/attribution footer.

The main sign-in action should be visible without scrolling at a 1366 by 768 viewport.

### Mobile

1. Compact brand row with no crowded duplicate navigation.
2. Single-column hero with the sign-in action visible near the top and at least 44 pixels high.
3. Ruling ledger below the primary action, with source tabs allowed to wrap.
4. Trust points stacked into short rows instead of equal-height cards.
5. Install banner fixed above the safe-area inset, with separate Install and Dismiss targets.

The page must have no horizontal overflow at 320, 375, and 430 pixel widths.

## Copy Direction

Keep the current citation-first promise but shorten the first viewport. Recommended draft:

- Eyebrow: `Rules answers with receipts`
- Heading: `Settle the ruling. Keep the game moving.`
- Supporting copy: `Ask an MTG rules question and get a concise answer grounded in the Comprehensive Rules, current Oracle text, and official rulings.`
- Primary action: `Sign in with Google`
- Trust note: `Your API key stays on the server. Answers show their sources.`

Copy must not claim zero hallucinations, perfect accuracy, or offline rules answers. It should distinguish an installable shell from questions that still require a network connection.

## Brand and PWA Asset Plan

Create one original SVG master based on a stacked rulebook tab forming a subtle `R`. It should remain recognizable at 16 pixels and have enough internal padding for maskable icons.

Generate and verify:

- `frontend/public/favicon.svg`
- `frontend/public/favicon.ico`
- `frontend/public/pwa-64x64.png`
- `frontend/public/pwa-192x192.png`
- `frontend/public/pwa-512x512.png`
- `frontend/public/apple-touch-icon-180x180.png`
- `frontend/public/maskable-icon-512x512.png`

Update `frontend/index.html` and the Vite manifest so `theme-color`, `background_color`, favicon links, and icon colors share the Obsidian Ink and Ember Archive palette. Keep important artwork inside the maskable safe zone and validate every exported dimension.

## Add to Home Screen Dismissal

### Behavior

- Show the banner only when the browser has supplied an install prompt, the app is not already running in standalone mode, and the user has not dismissed the banner in the current session.
- Add a button with the accessible name `Dismiss install prompt` and a visible `X` icon.
- Clicking the close button hides only the passive banner. It must not call the browser prompt or erase the stored `beforeinstallprompt` event.
- Store the dismissal flag in `sessionStorage`. The banner may return in a later browser session if installation is still available.
- Keep an explicit install action in the signed-in header or menu after the passive banner is dismissed.
- Clear the install UI after a successful `appinstalled` event.

### Interaction Requirements

- Install and Dismiss are separate keyboard-focusable buttons.
- Each mobile target is at least 44 by 44 pixels.
- Focus indication uses a high-contrast old-gold outline.
- The close control cannot overlap banner copy, the install action, or device safe areas.
- If storage access fails, dismissal still works in memory for the current page lifetime.

## Component and File Plan

| Area | Proposed change |
| --- | --- |
| `frontend/src/PublicPages.tsx` | Restructure the welcome hero, ruling ledger, trust rail, and public header presentation while preserving routes and auth callbacks. |
| `frontend/src/App.tsx` | Use the shared brand treatment and add install-banner dismissal state. Do not change signed-in navigation behavior. |
| `frontend/src/index.css` | Add Ember Archive tokens, responsive welcome layout, focus states, safe-area handling, and shared brand styles. |
| `frontend/src/BrandMark.tsx` | New reusable inline SVG mark so welcome and signed-in headers cannot drift. |
| `frontend/src/InstallPrompt.tsx` | Optional extraction for install visibility, dismissal, standalone detection, and accessible controls. |
| `frontend/index.html` | Align favicon declarations and browser theme color. |
| `frontend/vite.config.ts` | Align manifest colors and PWA icon metadata. |
| `frontend/public/*icon*` | Regenerate all icon formats from the approved master mark. |
| Frontend tests | Add sign-in preservation, dismissal persistence, installed-state suppression, accessibility, and responsive browser coverage. |

## Acceptance Criteria

1. Before authentication, `/` renders the Ember Archive welcome screen with no blue, cyan, violet, neon, or gradient brand treatment.
2. The primary `Sign in with Google` action retains its accessible name, pending state, successful redirect, and existing error recovery behavior.
3. The welcome screen and signed-in shell display the same original mark and core color tokens; no official Magic logo, mana symbol, art, or card frame is used.
4. The main sign-in action is visible without scrolling at 1366 by 768, and the page has no horizontal overflow at 320, 375, 430, 768, 1024, and 1440 pixel widths.
5. When install is available, activating `Dismiss install prompt` removes the mobile banner immediately and it stays hidden across re-renders and navigation for the current browser session.
6. Dismissing the passive banner does not consume the native prompt. The explicit install control remains usable, and no install UI appears in standalone mode or after `appinstalled`.
7. Favicon, Apple touch icon, PWA icons, manifest colors, and browser theme color visibly belong to the same palette and pass the existing PWA asset checks.
8. All interactive elements are keyboard reachable, use visible focus states, have accurate accessible names, and pass automated accessibility checks with no serious violations.
9. Text/background combinations meet WCAG AA, reduced-motion preferences are respected, and the design remains readable at 200 percent zoom.
10. Public copy accurately describes citation grounding and server-held secrets without claiming perfect correctness or fully offline answers.

## Test-Driven Implementation Order

1. Add failing component tests for the dismiss button, session persistence, storage failure fallback, successful installation cleanup, and standalone suppression.
2. Add failing tests that preserve the sign-in action's name, disabled/pending state, and auth error behavior after the layout change.
3. Implement the install-prompt state model and make those tests pass.
4. Add the shared brand component and warm tokens, then restructure the welcome screen.
5. Regenerate favicon/PWA assets and update metadata.
6. Add Playwright coverage for mobile and desktop welcome flows, keyboard navigation, install dismissal, overflow, and sign-in navigation.
7. Capture review screenshots at 375 by 812, 768 by 1024, 1366 by 768, and 1440 by 900 before deployment approval.

## Verification Gate

Run from `frontend/`:

```powershell
npm test
npm run lint
npm run test:coverage
npm run check:pwa
npm run e2e
```

Also verify:

- Auth redirect and logout return paths in a real Firebase preview environment.
- Browser tab favicon, Android install preview, Apple touch icon, and standalone launch background.
- Keyboard-only sign in and install dismissal.
- Light/dark browser chrome does not make the warm theme unreadable.
- No accidental changes to API endpoints, authentication configuration, or legal-page content.

## Delivery and Rollback

- Implement on a dedicated preview branch, beginning with tests.
- Keep visual changes separate from authentication or backend commits.
- Do not push or deploy until mobile and desktop screenshots are approved.
- If the redesign causes regressions, revert the isolated visual/install commits while retaining the current authentication behavior.
- Record any intentional deviations from this plan in the implementation notes before merge.

## Implementation Evidence

Date verified: 2026-08-19
Branch: `preview/single-screen-rag-desk`

### Delivered

- Rebuilt the unauthenticated welcome screen around the Ember Archive direction, including the warm palette, compact public header, citation-first copy, ruling ledger, source rail, limitations, and legal footer.
- Added one shared, original `BrandMark` for public and authenticated screens. No official Magic logo, mana symbol, card art, or card frame is used.
- Extracted install-prompt state into `useInstallPrompt.ts` and kept `InstallPrompt.tsx` presentational.
- Added a 44 by 44 pixel dismiss control with the accessible name `Dismiss install prompt`.
- Made banner dismissal session-scoped while preserving the explicit install action and the native install prompt.
- Suppressed install UI in standalone mode and after `appinstalled`.
- Regenerated favicon, Apple touch, PWA, and maskable assets from one warm SVG master and added a reproducible asset-generation command.
- Kept authentication callbacks, API endpoints, legal content, and backend behavior unchanged.

### TDD Checkpoints

| Checkpoint | Evidence | Result |
| --- | --- | --- |
| Install and welcome RED | `npm test -- InstallPrompt.test.tsx PublicPages.warm.test.tsx` before implementation | Failed for the missing install component and old welcome copy, as intended. |
| Install and welcome GREEN | Same focused suite after implementation | 8 tests passed. |
| PWA asset RED | `npm run check:pwa` after strengthening the verifier | Failed because the prior theme was `#0B0F17`, not the planned `#17120F`. |
| PWA asset GREEN | Same command after asset and metadata regeneration | Production build and PWA checks passed. |
| Full unit suite | `npm test -- --run` | 11 files and 58 tests passed. |
| Coverage | `npm run test:coverage` | 92.25% statements, 90.19% branches, 90.24% functions, and 95.15% lines. |
| Static checks | `npm run lint` | Passed with no warnings. |
| Dependency audit | `npm audit --audit-level=high` | Zero vulnerabilities. |
| PWA production gate | `npm run check:pwa` | Build and all icon, manifest, service-worker, API-cache, and theme checks passed. |
| Browser matrix | `npm run e2e` | 105 tests passed across Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari. |

### Acceptance Audit

1. The public screen computes to Obsidian Ink with no background image; the primary action computes to Ember Red. The active public brand does not use blue, cyan, violet, or neon colors.
2. Existing and added unit/browser tests preserve the Google sign-in accessible name, redirect behavior, pending state, error recovery, and logout return to `/`.
3. Public and authenticated surfaces render the same original SVG mark and shared warm tokens.
4. Browser tests cover 320, 375, 430, 768, 1024, 1366, and 1440 pixel widths, report no horizontal overflow, and verify the primary action is above the fold at 1366 by 768.
5. Component and browser tests verify immediate dismissal and session persistence.
6. Tests verify that dismissal does not consume installation, the explicit action remains, and installed or standalone states suppress install UI.
7. The production PWA verifier checks favicon links, exported dimensions, palette consistency, manifest colors, service-worker output, API cache, and maskable metadata.
8. Axe checks pass on public and authenticated pages in every configured browser profile. Keyboard navigation, visible focus, accurate names, and mobile target sizing are covered.
9. Responsive coverage at 320 and 768 CSS pixels exercises the equivalent reflow pressure of enlarged browser content; reduced-motion rules remain enabled. Automated contrast checks report no serious violations.
10. The public copy describes grounding and server-held secrets without promising zero hallucinations, perfect correctness, or offline answers.

### Review Screenshots

The browser suite captured the welcome page at 375 by 812, 768 by 1024, 1366 by 768, and 1440 by 900 during the final run. The signed-in responsive snapshots were refreshed at 375, 768, and 1440 pixels. Visual review found no overlap, clipping, or horizontal overflow.

### Intentional Deviations and Remaining External Checks

- Install behavior lives in `useInstallPrompt.ts` instead of the optional single-file extraction proposed above. This keeps stateful browser behavior separate from presentation and removed a hot-reload lint warning.
- A neutral loading shimmer still uses a functional CSS gradient. The public welcome screen and primary brand treatment use no gradients.
- Firebase redirect/logout behavior is covered locally and was not changed. A real Firebase preview auth pass, browser-tab favicon inspection, and operating-system install preview remain post-deployment checks because deployment and publishing are excluded until the screenshots receive explicit approval.
