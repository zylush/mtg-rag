# MTG Rules Desk — Public UX and Legal Pages

**Status:** Revision 4 implemented and development verified; legal approval remains pending
**Revision:** 4
**Last reconciled:** 2026-08-14

This is a scoped implementation record, not the project-wide launch plan. The canonical
architecture and active production gates are in [`MTG-PLAN.md`](MTG-PLAN.md). Detailed test
evidence is in
[`testing/public-ux-legal-pages.tdd.md`](testing/public-ux-legal-pages.tdd.md), and
live integration evidence is in [`INTEGRATION-LESSONS.md`](INTEGRATION-LESSONS.md).

## Revision history

| Revision | Date | Change |
| --- | --- | --- |
| 1 | 2026-08-12 | Defined the public, authenticated, and legal-page implementation scope. |
| 2 | 2026-08-14 | Reconciled engineering completion and development evidence while preserving legal launch blockers. |
| 3 | 2026-08-14 | Added the navigation, responsive-browser, accessible-feedback, and development-safe SEO deployment plan. |
| 4 | 2026-08-14 | Removed the intermediate sign-in page; public sign-in controls now invoke Firebase directly, and logout returns home. |

## Goal

Add a coherent public-to-authenticated experience with Welcome, direct Google authentication,
Chat, About, Terms of Service, and Privacy Policy pages while preserving the existing RAG chat
behavior.

## Reconciled outcome

- The public routes, protected desk, navigation, responsive behavior, and PWA build are
  implemented and covered by unit and Playwright checks.
- Firebase Hosting serves the pages in the development environment, and a real Google sign-in
  completed the chat, citations, quota, and History flow.
- Terms and Privacy intentionally remain structured outlines with a visible pending-review
  state. They are not final legal copy and do not authorize public launch.
- This feature plan is complete as an engineering implementation record. Remaining legal,
  evaluation, and production-readiness work is governed by the launch criteria in
  [`MTG-PLAN.md`](MTG-PLAN.md#10-active-public-launch-gates).

## Routes

```text
/          Welcome page
/desk      Authenticated MTG rules chat
/about     Product, methodology, and attribution
/terms     Terms of Service
/privacy   Privacy Policy
```

Revision 3 adds refreshable authenticated subroutes:

```text
/desk/history    Authenticated conversation-history drawer
/desk/settings   Authenticated settings and product-link drawer
```

Signed-out visitors can view static public pages and a non-interactive cited-answer preview. Public
sign-in controls invoke Firebase/Google authentication directly without an intermediate app page.
Live questions remain sign-in gated. Signed-out `/desk` access, logout, and legacy `/login` or
`/auth` URLs return to `/`; successful authentication routes to `/desk`.

## Revision 4 implementation plan

This slice improves the existing frontend without changing the backend, RAG pipeline, quotas,
authentication provider, or legal/public-launch decisions.

1. **Make navigation state durable.** Represent History and Settings in the URL, use history
   replacement for authentication redirects and unknown routes, give authenticated public pages
   a clear route back to the desk, invoke authentication from public screens, and return logout
   to the Welcome page.
2. **Remove competing controls.** Remove the duplicate mobile menu, authenticated header links,
   and decorative empty-desk panel. Keep one primary navigation system and move About, Terms,
   Privacy, and install controls into Settings.
3. **Make transient UI accountable.** Treat History and Settings as labelled modal drawers,
   move focus into them, close on Escape, restore focus on close, and expose feedback/deletion
   pending, success, and error states.
4. **Harden responsive behavior.** Switch the desk to its compact navigation before tablet widths
   become cramped, support dynamic viewport height and safe-area insets, preserve at least 44px
   touch targets, and verify no horizontal overflow at release widths.
5. **Add development-safe SEO.** Set route-specific titles, descriptions, canonicals, and robots
   directives. Keep authenticated and draft legal pages out of search. The development deployment
   remains globally blocked in `robots.txt` until the production domain and legal copy are approved;
   a real XML sitemap documents the intended public Home/About surface for later launch review.
6. **Verify and deploy.** Run unit coverage, lint, multi-viewport Playwright checks, production
   build/PWA validation, dependency audit, deploy only Firebase Hosting to
   `mtg-rules-desk-dev`, and perform read-only browser smoke checks on the live result.

### Revision 3 acceptance criteria

#### AC-UX-001: Predictable route and history behavior

- **Scenario:** A signed-in or signed-out visitor opens a public, protected, subpanel, or unknown URL.
- **Expected:** Public pages remain public; protected desk routes require authentication; History and
  Settings survive refresh and Back/Forward; authentication redirects and unknown-route recovery use
  replacement navigation; authenticated About/Legal pages offer **Back to desk**.
- **Must not:** Leave a soft-404 URL visible, add redirect entries to browser history, or hide the only
  path back to the signed-in desk.
- **Verification:** Routing unit tests and Playwright deep-link/Back/Forward tests.

#### AC-UX-002: One coherent responsive navigation

- **Scenario:** The authenticated desk is used at 320, 375, 390, 768, 820, 1024, and 1440 CSS pixels.
- **Expected:** One primary navigation is visible, the compact layout activates at tablet widths,
  controls have usable touch targets, safe areas are respected, and no horizontal scroll appears.
- **Must not:** Show both a mobile hamburger and bottom navigation or devote the empty state to a
  duplicate decorative rules panel.
- **Verification:** Responsive Playwright checks and targeted DOM/CSS contract tests.

#### AC-UX-003: Accessible, observable drawers and mutations

- **Scenario:** A keyboard or assistive-technology user opens History/Settings, deletes data, or rates
  an answer.
- **Expected:** The drawer is a labelled modal dialog, receives focus, closes with Escape, and returns
  focus to its trigger. Feedback exposes pressed/pending/saved/error state; conversation and account
  deletion failures are visible.
- **Must not:** Fail silently, fire repeat mutations while pending, or strand focus behind a drawer.
- **Verification:** Component tests, axe checks, and keyboard E2E tests.

#### AC-SEO-001: Correct route metadata without premature indexing

- **Scenario:** A crawler or visitor opens each frontend route in the development deployment.
- **Expected:** Every route has a unique useful title/description, a normalized canonical, and an
  appropriate robots directive. `/robots.txt` is plain text and `/sitemap.xml` is XML rather than the
  SPA shell. Desk, login, draft legal pages, and all pages on the development host remain non-indexable.
- **Must not:** Expose authenticated content to indexing, advertise draft legal copy, or use an
  unapproved production domain.
- **Verification:** Metadata unit tests, built-artifact tests, HTTP content-type checks, and rendered
  browser inspection after deployment.

#### AC-DEPLOY-001: Development hosting update only

- **Scenario:** Revision 3 passes its local quality gates.
- **Expected:** Firebase Hosting for `mtg-rules-desk-dev` serves the new frontend and retains the
  existing same-origin `/v1/**` backend rewrite.
- **Must not:** Modify production infrastructure, credentials, Cloud Run services, databases, or
  public-launch status.
- **Verification:** Firebase deploy output plus live public-route, crawler-asset, and API-rewrite smoke
  checks.

### Revision 3 outcome ? 2026-08-14

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC-UX-001 | Development verified | Route unit tests plus Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari Back/Forward/deep-link checks. |
| AC-UX-002 | Development verified | No overflow at 320, 375, 390, 768, 820, 1024, or 1440px; reviewed visual baselines at 375, 768, and 1440px. |
| AC-UX-003 | Development verified | Dialog, focus, Escape, visible mutation-state, axe, and engine-specific WebKit tests pass. |
| AC-SEO-001 | Development verified | Unique rendered metadata; plain-text crawler block; XML sitemap; live content-type and canonical checks pass. |
| AC-DEPLOY-001 | Development verified | Firebase Hosting release completed at `https://mtg-rules-desk-dev.web.app`; unsigned `/v1/conversations` still returns backend JSON `401`. |

The final evidence and issue-by-issue lessons are in
[`testing/navigation-responsive-seo.tdd.md`](testing/navigation-responsive-seo.tdd.md) and
[`INTEGRATION-LESSONS.md`](INTEGRATION-LESSONS.md). This outcome does not change the legal or
production launch gates.

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

## Acceptance criteria status

| Criterion | Engineering status | Remaining evidence |
| --- | --- | --- |
| **AC-001:** Public routes render without auth; `/desk` redirects signed-out users to Login. | Verified by unit and Playwright deep-link tests. | None for this feature. |
| **AC-002:** Welcome renders purpose, a static cited preview, attribution, limitations, and sign-in CTA without API calls. | Verified by unit and E2E tests. | None for this feature. |
| **AC-003:** Login exposes Terms/Privacy and recoverable sign-in failure feedback. | Verified by component and browser checks. | None for this feature. |
| **AC-004:** Authenticated chat behavior and API contracts remain unchanged. | Verified locally and through a real development sign-in/chat/history flow. | Production smoke test belongs to the release plan. |
| **AC-005:** Terms/Privacy expose structured outlines and do not present placeholders as final legal advice. | Implementation verified. | Qualified legal/operator approval and final copy remain pending. |
| **AC-006:** Public and authenticated routes pass accessibility, keyboard, responsive, and no-overflow checks. | Verified by axe and Playwright across desktop/mobile paths. | Final human accessibility review is recommended before launch. |
| **AC-007:** Attribution is visible and does not imply WotC or Scryfall endorsement. | Automated text checks pass. | Human policy/legal approval remains pending. |

## Verification commands

```text
cd frontend
npm run lint
npm run test:coverage -- --maxWorkers=1
npm run e2e
npm run build
npm run check:pwa
```

Evidence is recorded in [`testing/public-ux-legal-pages.tdd.md`](testing/public-ux-legal-pages.tdd.md).

The broader release pipeline additionally passed the backend suite, frontend unit and 13
Playwright E2E tests, PWA artifact validation, dependency audits, container checks, and a live
authenticated multi-source answer. Those results are development evidence, not substitutes
for the pending approvals in the canonical plan.

## Boundaries and launch decisions

- English-only remains in scope.
- No anonymous live questions, analytics redesign, card-image gallery, multilingual support, or backend consent schema.
- The operator must supply final legal entity, support contact, effective dates, jurisdiction, retention periods, and reviewed policy copy.
- The existing WotC registration/access-policy conflict remains a human/legal launch blocker.
- This plan does not authorize production deployment or public access; use
  [`MTG-PLAN.md`](MTG-PLAN.md#10-active-public-launch-gates) for the release decision.
