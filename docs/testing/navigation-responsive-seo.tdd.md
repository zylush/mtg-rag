# Navigation, Responsive UI, and SEO ? TDD Evidence

**Status:** GREEN, development deployed, and live verified
**Date:** 2026-08-14
**Scope:** [PRD.md](../PRD.md#8-user-experience-and-navigation), preserving the verified Revision 3 evidence.

This record will capture the failing tests, implementation changes, verification results,
deployment identifier, and live smoke evidence for AC-UX-001 through AC-DEPLOY-001.

## Boundaries

- Firebase Hosting development deployment only.
- No backend, database, Cloud Run, secret, quota, or RAG behavior changes.
- No claim of production launch readiness.
- No indexing of the development host.

## RED

Added contracts for:

- `/desk/history` and `/desk/settings`, unknown-route replacement, and auth-aware public links;
- modal drawer focus/Escape behavior and route persistence;
- visible feedback, conversation-deletion, and account-deletion outcomes;
- product/install links in Settings with duplicate navigation and decorative empty UI removed;
- unique route metadata, canonical URLs, and development-safe crawler directives;
- horizontal-overflow checks at 320, 375, 390, 768, 820, 1024, and 1440px.

Command:

```text
cd frontend
npm test -- --run src/route-meta.test.ts src/routing.test.tsx src/App.test.tsx
```

Observed result: **3 test files failed; 10 tests failed and 15 passed**. The failure set
confirmed the intended gaps: no route-metadata module, unsupported desk subroutes, unknown URLs
left visible, unauthenticated-only public header/login branding, local-only drawers without dialog
or focus behavior, silent feedback/deletion failures, and the duplicate mobile/decorative UI.

## GREEN

Local verification:

```text
Targeted unit: 27/27 passed
Full unit: 36/36 passed
Coverage: 90.94% statements, 88.55% branches, 87.50% functions, 93.30% lines
Playwright: 80/80 passed across desktop Chromium, Firefox, WebKit, mobile Chrome, mobile Safari
Responsive widths: 320, 375, 390, 768, 820, 1024, 1440px
Lint: 0 errors, 0 warnings
npm audit --audit-level=high: 0 vulnerabilities
TypeScript + Vite production build: passed
PWA/crawler/secret-artifact checks: passed
```

The reviewed Chromium baselines at 375, 768, and 1440px show the intended removal of the
hamburger and decorative empty panel, a single mobile bottom navigation, and the tablet layout
switching to compact navigation at 900px.

## Deployment and browser evidence

- Command: `firebase deploy --only hosting --project mtg-rules-desk-dev`.
- Result: hosting version finalized and released successfully.
- URL: `https://mtg-rules-desk-dev.web.app`.
- Home rendered title, description, canonical, and `noindex, nofollow` match the development
  metadata contract.
- About renders the unique title `How MTG Rules Desk Works`, its `/about` canonical, no overflow,
  and no dead global `#how-it-works` link.
- `/robots.txt`: HTTP 200, `text/plain`, `Disallow: /`.
- `/sitemap.xml`: HTTP 200, `application/xml`, valid Home/About entries.
- `/about`: HTTP 200 HTML through the SPA fallback.
- unsigned `/v1/conversations`: HTTP 401 `application/json`, proving the existing Cloud Run rewrite
  and authentication boundary remain in place.
- Live public QA was read-only; no real sign-in, chat request, feedback, or deletion was performed.

## Issues and lessons

1. Local panel state looked correct but made refresh and Back/Forward meaningless. User-visible
   navigation state belongs in the URL.
2. Moving Install into Settings exposed a broad mobile CSS selector that hid every
   `.utility-button`. Scope responsive selectors to the component that owns the behavior.
3. Browser clicks do not focus controls identically in WebKit. Return drawer focus to an explicit
   trigger reference rather than assuming `document.activeElement` is the trigger.
4. Running five browser projects with six workers caused Firefox teardown contention even though
   assertions passed. Two workers completed the same 80 scenarios deterministically.
5. A Firebase SPA fallback makes missing crawler files appear healthy because they return HTML 200.
   Assert both content type and body shape for `robots.txt` and `sitemap.xml`.
6. Development SEO and production SEO are different states. This release adds correct route
   metadata but deliberately blocks the development host until the legal/domain launch gates close.
