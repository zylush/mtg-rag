# Privacy Policy Content: TDD Evidence

## Source and user journey

No implementation plan file was supplied. The journey was derived from the request:

> As a visitor, I want a readable privacy policy that describes MTG Rules Desk's actual data flow, so I can understand what the application processes, where it goes, how long it remains, and how to exercise my choices.

## RED

Command:

`npm test -- App.test.tsx`

Result: **FAIL**, with 1 failed and 23 passed tests. The privacy route still showed the placeholder effective date and could not find `Effective date: August 17, 2026`. The new test also required implementation-specific Firebase, OpenAI, semantic-cache, browser-storage, and contact disclosures.

Checkpoint: `b025225 test: add privacy policy content expectations`

## GREEN

The placeholder privacy outline was replaced by structured React paragraphs and lists. The content now reflects the implemented Firebase Authentication, Google Cloud, Cloud SQL, OpenAI, RAG, semantic-cache, PWA, logging, retention, and deletion behavior. At this historical checkpoint, the Terms of Service placeholder remained unchanged; the 2026-08-24 follow-up replaced it with operational copy pending qualified legal review.

Focused command:

`npm test -- App.test.tsx`

Result: **PASS**, 24 tests passed.

Checkpoint: `c92a40d feat: publish implementation-aligned privacy policy`

## Guarantees

| # | What is guaranteed | Evidence | Type | Result |
|---|---|---|---|---|
| 1 | The privacy route renders the effective date and no longer shows the Firebase placeholder | `src/App.test.tsx` | Integration | PASS |
| 2 | Firebase identity, OpenAI processing, seven-day semantic caching, and the absence of advertising cookies or analytics are disclosed | `src/App.test.tsx` | Integration | PASS |
| 3 | The privacy contact is a functional email link | `src/App.test.tsx` | Integration | PASS |
| 4 | Public legal routes remain reachable without authentication | `tests/e2e/public-pages.spec.ts` | E2E | PASS |
| 5 | Public pages have no detectable WCAG 2.0/2.1 A or AA violations in the configured browsers | `tests/e2e/public-pages.spec.ts` | E2E | PASS |

## Final verification

- `npm test`: 41 passed.
- `npm run lint`: passed.
- `npm run build`: passed.
- `npm run test:coverage`: 91.1% statements, 89.59% branches, 89.13% functions, and 94.11% lines.
- `npm run e2e -- tests/e2e/public-pages.spec.ts`: 25 passed across Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari.

## Known boundaries

- The page remains marked **Pending legal review** because implementation accuracy is not a substitute for qualified legal review.
- The policy states that account deletion requests Firebase identity deletion after removing application rows. The two-system deletion path can still fail partially and is documented as an operational risk elsewhere in the repository.
- Semantic-cache entries are not linked to account IDs and expire separately within seven days, so account deletion cannot immediately target an existing cache entry.
- At the time of this checkpoint, Terms of Service content remained a placeholder and was outside
  that task. The 2026-08-24 public-launch follow-up replaced it with implementation-aligned
  operational terms; qualified legal review is still required.

## Follow-up — 2026-08-24

The public question path now accepts one free question without an account or email registration.
Privacy copy discloses that public questions are not written to account history but may enter the
shared semantic cache for up to seven days. Focused frontend and backend tests cover the new path.
