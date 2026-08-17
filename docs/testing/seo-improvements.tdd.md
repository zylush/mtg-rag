# SEO Improvements: TDD Evidence

## Source and journeys

No implementation plan file was supplied. The journeys were derived from the request:

- As a search crawler, I receive consistent robots, sitemap, canonical, title, description, Open Graph, and structured-data signals.
- As the operator, I can keep development and preview deployments blocked while enabling indexing only for an approved public origin.
- As a visitor or link recipient, I receive route-specific metadata for the home, about, terms, and privacy pages.

The implementation follows Google Search Central guidance to keep canonical URLs consistent, include only canonical indexable URLs in the sitemap, and use complete, visible-content-aligned JSON-LD without invented ratings.

## RED

Focused command:

`npm test -- seo-config.test.ts src/route-meta.test.ts`

Result: **FAIL**. The SEO configuration module did not exist, route metadata had no social image or structured data, and the DOM updater did not create Open Graph, Twitter, or JSON-LD elements.

Artifact command:

`npm run check:pwa`

Result: **FAIL**. The existing build had no route-specific `about.html`, canonical or social artifact guarantees, and the new metadata contract did not compile against the old implementation.

Checkpoint: `0c45a02 test: define SEO metadata and crawler contracts`

## GREEN

The implementation now:

- validates one HTTPS public origin, with HTTP allowed only for local development;
- generates `robots.txt` and `sitemap.xml` from the same origin and explicit indexing flag;
- creates distinct HTML shells for home, about, terms, and privacy routes;
- emits unique titles, descriptions, canonical URLs, Open Graph, and Twitter metadata;
- emits accurate `WebSite`, `SoftwareApplication`, and `WebPage` JSON-LD;
- keeps authenticated routes and unreviewed legal routes out of the sitemap;
- keeps the development build blocked unless `VITE_ALLOW_INDEXING=true`.

Focused results:

- `npm test -- seo-config.test.ts src/route-meta.test.ts`: 7 passed.
- `npm run check:pwa`: passed, including generated metadata and crawler files.

Checkpoint: `cf33213 feat: generate production-safe SEO metadata`

## Guarantees

| # | What is guaranteed | Evidence | Type | Result |
|---|---|---|---|---|
| 1 | Invalid, non-HTTPS, or path-bearing public origins are rejected | `seo-config.test.ts` | Unit | PASS |
| 2 | Development robots block crawling and production robots advertise the canonical sitemap | `seo-config.test.ts` | Unit | PASS |
| 3 | The sitemap contains only home and about canonical URLs | `seo-config.test.ts`, `scripts/check-pwa.mjs` | Unit/artifact | PASS |
| 4 | Structured data describes a free reference app and does not invent ratings | `seo-config.test.ts` | Unit | PASS |
| 5 | Client navigation updates canonical, Open Graph, Twitter, and JSON-LD metadata and removes stale schema | `src/route-meta.test.ts` | Integration | PASS |
| 6 | Built home and about HTML contain static canonical and social metadata | `scripts/check-pwa.mjs` | Artifact | PASS |
| 7 | Public pages remain accessible across desktop and mobile browser engines | `tests/e2e/public-pages.spec.ts` | E2E | PASS |

## Final verification

- `npm run test:coverage`: 46 passed; 92.37% statements, 90.9% branches, 89.89% functions, and 94.9% lines.
- `npm run lint`: passed.
- `npm audit --audit-level=high`: zero vulnerabilities.
- `npm run e2e -- tests/e2e/public-pages.spec.ts`: 25 passed across Chromium, Firefox, WebKit, mobile Chrome, and mobile Safari.
- Production-mode example build: home and about were `index, follow`; terms and privacy remained `noindex, nofollow`; robots and sitemap used the configured example origin.
- The default development artifact was rebuilt afterward and `npm run check:pwa` passed with site-wide crawling blocked.

## Known boundaries

- The current development deployment stays intentionally blocked. An approved release must set `VITE_PUBLIC_SITE_URL` to the final origin and `VITE_ALLOW_INDEXING=true` before building.
- Search Console ownership, sitemap submission, and indexing requests require operator approval and were not performed.
- The social preview currently uses the existing 512-pixel application icon with a summary card. A dedicated 1200 by 630 social image is a future enhancement.
- Static route shells improve source metadata, while the main visible React content remains client-rendered. Full prerendering or server-side rendering is outside this change.
