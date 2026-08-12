# Attribution and launch decisions

This is an engineering release record, not legal advice. Policies are external,
changeable dependencies and must be rechecked by a named reviewer before public launch.
The evidence below was checked on 2026-08-12.

## Required notices

The login and settings screens identify MTG Rules Desk as unofficial fan content,
attribute Magic: The Gathering and related marks to Wizards of the Coast, and attribute
card data and rulings to Scryfall. Do not imply sponsorship, endorsement, or an official
rules-judge service in product copy, metadata, domains, or marketing.

## Decision register

| Dependency | Evidence | Current decision | Release action |
| --- | --- | --- | --- |
| Wizards fan content | [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy) and [Terms](https://company.wizards.com/en/legal/terms) | **Blocked** | A qualified reviewer must decide whether mandatory account registration and the proposed rules excerpts comply, or obtain written permission/change the product. |
| Scryfall data and rulings | [Scryfall API documentation](https://scryfall.com/docs/api) | **Provisional** | Confirm the deployed service remains free to access, adds material rules value, uses an identifying user agent, does not proxy/repackage the API, respects rate guidance, and displays attribution. |
| OpenAI regional availability | [Supported countries and territories](https://help.openai.com/en/articles/5347006-openai-api-supported-countries-and-territories/) | **Verified on review date** | Recheck that Japan, Singapore, South Korea, and Taiwan remain supported before launch and on material regional changes. |
| Comprehensive Rules | [Official rules page](https://magic.wizards.com/en/rules) | **Source verified** | Ingestion must record upstream version/checksum and the release must use the independently reviewed eval suite. |
| Rules accuracy | `backend/evals/mtg_rules_v1.json` | **Blocked** | An independent MTG rules expert must approve all expected answers/references and a staging run must pass every gate. |
| Privacy and consumer terms | Operator-owned documents | **Blocked** | Publish reviewed privacy, terms, retention, support, and deletion language appropriate to deployed regions and processors. |

## Wizards policy conflict

The current fan-content policy says qualifying fan content must be freely accessible
and describes registration requirements as a form of payment/access condition. This
application currently requires sign-in for every rules query to support ownership,
quotas, history, and deletion. That is a plausible conflict, so engineering cannot mark
the public launch ready. Acceptable resolutions are a documented legal determination,
written permission, or a product change that preserves abuse controls without requiring
registration for access.

The policy also restricts copying Wizards material. The product retrieves short,
cited excerpts needed to answer a question and provides additional explanatory value;
the reviewer must confirm that the final presentation and corpus use are acceptable.

## Scryfall operational requirements

The ingestion client supplies an identifying user agent and obtains bulk/versioned
sources rather than turning user traffic into an API proxy. The public product must
remain free, must not suggest Scryfall endorsement, and must not put Scryfall data behind
a paid access gate. Recheck API and image-use requirements if card images, monetization,
or a public data export are added.

## Go/no-go record

Before production, record reviewer name, date, evidence URL/version, conclusion, and any
conditions for every blocked or provisional row. A policy link, code attribution, or
passing automated test is not itself approval. Any later addition of payment,
advertising, card images, data export, new regions, or anonymous access triggers a fresh
review.
