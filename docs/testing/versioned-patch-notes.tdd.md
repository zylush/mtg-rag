# Versioned patch notes TDD evidence

**Source:** User-directed redesign of the public patch-history page.
**Status:** GREEN locally; no deployment performed for this change.

## User journeys

- As a release reviewer, I can distinguish each documented Firebase deployment checkpoint from
  the current local preview.
- As a reviewer, I can scan concise hyphen-prefixed notes for each release without Git-specific
  proof links in the public UI.
- As a reviewer, I see related changes merged into grouped notes, with every visible note using at
  least two sentences.
- As a reviewer, I can page through concise patch notes within one version without paginating the
  whole patch-history page.
- As a reviewer, I can page through deployment releases, keep the oldest/newest filter, and see
  release cards reorder without a chronological ledger in the public UI.

## RED and GREEN evidence

| Stage | Command | Result |
| --- | --- | --- |
| RED | `npm test -- --run src/PublicPages.warm.test.tsx` | 1 of 8 failed because the versioned patch-notes heading did not exist. |
| GREEN | `npm test -- --run src/PublicPages.warm.test.tsx` | 9 of 9 passed, including grouped multi-sentence notes, deployment-release pagination, and per-release note pagination. |
| Full unit suite | `npm test` | 12 files and 72 tests passed. |
| Static quality | `npm run lint` | Passed with no warnings. |
| Production build | `npm run build` | TypeScript and Vite build passed. |
| Browser QA | `npx playwright test tests/e2e/public-pages.spec.ts --project=chromium` | 8 of 8 passed, including axe checks. |

## Release data policy

The page uses a checked-in snapshot from `frontend/src/patch-history.ts`. The release cards are
explicit evidence checkpoints rather than a live Git API feed:

- `v0.1.0` — first Firebase development preview, recorded on 2026-08-13 (`bd44b3a`).
- `v0.1.1` — navigation and direct-auth development release, recorded on 2026-08-14
  (`247157d`).
- `v0.2.0` — warm Firebase development preview, recorded on 2026-08-19 (`604dfb2`).
- `v0.3.0` — current local chat-history preview, not deployed (`49873ff`).

The public release cards intentionally keep their notes grouped and concise, merging related
changes into multi-sentence bullets while omitting Git proof links. The
repository-only chronological ledger is not rendered on the public page. New deployments should
add an explicit release record when the owner requests the next versioned patch post.

## Known gaps

- The current release metadata is still maintained as an explicit, reviewed snapshot; it does not
  infer deployment events from Firebase automatically.
- The browser check covers Chromium and axe. A manual screen-reader pass remains a separate QA
  follow-up.
