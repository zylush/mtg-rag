# MTG Rules Desk — Public UX and Legal Pages

**Status:** Implemented and locally verified  
**Revision:** 1

## Goal

Add a coherent public-to-authenticated experience with Welcome, Login, Chat, About, Terms of Service, and Privacy Policy pages while preserving the existing RAG chat behavior.

## Routes

```text
/          Welcome page
/login     Firebase/Google sign-in
/desk      Authenticated MTG rules chat
/about     Product, methodology, and attribution
/terms     Terms of Service
/privacy   Privacy Policy
```

Signed-out visitors can view static public pages and a non-interactive cited-answer preview. Live questions remain sign-in gated. Signed-out `/desk` access redirects to `/login`; signed-in visitors at `/` or `/login` go to `/desk`.

## Design direction

Use the existing annotated rules-desk system:

- paper `#f4f5f1`, ink `#10263a`, rules blue `#1b5a7a`, copper `#a6532b`, surface `#fffdfa`;
- Georgia/system serif for headings and rulings, system sans for controls, monospace for rule/source metadata;
- source spine signature: `Q — Question`, `A — Answer`, `S — Sources`;
- responsive layouts from 320px upward, visible focus, WCAG AA contrast, semantic landmarks, and reduced-motion support.

Avoid generic SaaS gradients, card-store imagery, or claims of official Wizards of the Coast endorsement.

## Page requirements

### Welcome

- Product thesis: “Settle the rules question. Keep the game moving.”
- Static cited-answer preview with Question → Answer → Sources.
- Sign-in CTA, About link, limitations, attribution, support, Terms, and Privacy links.
- Explain source citations, assumptions/confidence, saved conversations, and deletion controls.
- Do not call the API, OpenAI, Firebase Auth, or consume quota.

### Login

- Existing Google sign-in action and regional availability notice.
- Loading, sign-in failure, popup/network recovery, Terms, and Privacy states/links.
- Explicitly state that the product is unofficial fan content.
- Do not add server-side consent persistence until legal review requires it.

### Authenticated desk

- Preserve question submission, citations, assumptions, confidence, quota, feedback, History, Settings, account deletion, and PWA installation.
- Add About and Legal access to the authenticated header.
- Keep desktop side navigation and mobile bottom navigation behavior.

### About

Explain the product purpose, retrieval/generation/citation workflow, source attribution, non-endorsement, limitations, supported scope, history/deletion controls, and support contact.

### Terms and Privacy

Use accessible long-form document layouts with effective-date/owner placeholders, table of contents, section anchors, and a visible `Pending legal review` banner. Provide structured outlines only; do not invent final legal language.

Terms must cover service, accounts/eligibility, acceptable use, sources/attribution, AI-answer limitations, deletion/termination, changes, dispute/contact language.

Privacy must accurately cover Firebase identity, questions/answers/history/feedback/quota, OpenAI, PostgreSQL, Cloud Storage, Firebase, monitoring, retention/deletion, browser storage/PWA behavior, regional processing, rights, minors, updates, and contact.

## Interfaces

- Add a client-side route context with `AppRoute`, `normalizeRoute`, `RouterProvider`, `useRouter`, and `AppLink`.
- Keep existing `AuthPort`, `ApiPort`, and backend endpoint contracts unchanged.
- Extend the E2E harness with an optional `?route=/...` route selector.

## Acceptance criteria

- **AC-001:** Public routes render without auth; `/desk` redirects signed-out users to Login. Verify with unit and Playwright deep-link tests.
- **AC-002:** Welcome renders product purpose, static cited preview, attribution, limitations, and sign-in CTA without API calls. Verify with unit/E2E tests.
- **AC-003:** Login exposes Terms/Privacy and sign-in failure feedback. Verify with component assertions and manual review.
- **AC-004:** Authenticated chat behavior and existing API contracts remain unchanged. Verify existing unit/E2E coverage.
- **AC-005:** Terms/Privacy expose structured reviewed-content outlines and do not present placeholders as final legal advice. Verify content assertions and operator/legal review.
- **AC-006:** Public and authenticated routes pass accessibility, keyboard, responsive, and no-overflow checks. Verify axe, Playwright, and visual snapshots.
- **AC-007:** Attribution is visible and never implies WotC or Scryfall endorsement. Verify automated text assertions and human/legal review.

## Verification commands

```text
cd frontend
npm run lint
npm run test:coverage -- --maxWorkers=1
npm run e2e
npm run build
npm run check:pwa
```

Evidence is recorded in [`docs/testing/public-ux-legal-pages.tdd.md`](docs/testing/public-ux-legal-pages.tdd.md).

## Boundaries and launch decisions

- English-only remains in scope.
- No anonymous live questions, analytics redesign, card-image gallery, multilingual support, or backend consent schema.
- The operator must supply final legal entity, support contact, effective dates, jurisdiction, retention periods, and reviewed policy copy.
- The existing WotC registration/access-policy conflict remains a human/legal launch blocker.
