# Attribution and launch decisions

**Decision date:** 2026-08-24

This is an engineering release record, not legal advice or permission from Wizards of the
Coast or Scryfall. External policies can change and must be reviewed by a named operator and
qualified counsel before production publication.

Use [SOURCE-USE-REVIEW-PACKET.md](SOURCE-USE-REVIEW-PACKET.md) to record the implementation-specific
corpus, excerpt, mark, storage, processor, and publication decisions. A public development-preview
label does not waive that review.

## Product decision for the fan-content conflict

The original product required Google sign-in before every rules question. The Wizards Fan
Content Policy says fan content must be freely accessible and must not require email
registration. We therefore changed the product boundary:

- `/v1/public/ask` and the public question panel answer questions without an account or email
  registration.
- Public answers receive ephemeral response identifiers and are not written to account history.
- Sign-in is optional and is reserved for saved conversations, feedback, quotas, and account
  deletion controls.
- Public questions may populate the existing shared semantic cache for up to seven days when
  they meet the same confidence and ambiguity safeguards as authenticated questions.
- A per-process burst limiter protects development and staging. Production still requires a
  distributed edge/application rate limit before launch.

This product change addresses the mandatory-registration conflict at the engineering layer. It
does not constitute a legal determination, written permission, or a claim that the final source
presentation is covered by the policy.

## Required notices

The public footer, About page, and Terms page state that MTG Rules Desk is unofficial Fan Content,
is not approved or endorsed by Wizards of the Coast, and contains the required Wizards property
notice. They also state that Scryfall supplies card data and rulings and does not endorse the app.
The app does not use Wizards logos, official card frames, card art, or language suggesting an
official judge or support service.

The public support contact is **paoloinigo30@gmail.com**. Support copy asks people not to send
passwords, tokens, or sensitive personal information.

## Decision register

| Dependency | Evidence | Engineering decision | Release condition |
| --- | --- | --- | --- |
| Wizards fan content | [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy) and [Terms](https://company.wizards.com/en/legal/terms) | **Product conflict addressed** by removing mandatory account/email registration from public questions. | A qualified reviewer must confirm that the final source excerpts, links, marks, and corpus use are acceptable, or obtain written permission/change the product. |
| Scryfall data and rulings | [Scryfall API documentation](https://scryfall.com/docs/api) | **Attribution implemented; operational review pending.** The client uses versioned ingestion rather than a user-facing API proxy. | Confirm current terms, rate guidance, identifying user agent, source links, and any future image/data-export use. |
| Comprehensive Rules | [Official rules page](https://magic.wizards.com/en/rules) | **Source identified and linked.** The app presents short cited evidence plus its own explanation. | Confirm the deployed corpus version/checksum and the independently reviewed evaluation suite. |
| Privacy and consumer terms | `frontend/src/PublicPages.tsx` and the public development routes | **Implementation-aligned copy published to development.** Exactly one Hosting-only deploy of tested artifact `2c23d3d48194327cec675e2b9cf70fc7dc9afda3777b20384c92453f94e80fae` completed; read-only live QA verified Terms, Privacy, About, preview labeling, attribution, and support with no inspected console errors. | Qualified legal review, operator approval of its decision, and any reviewer-required revision. The Termly preview still contains template blanks and has not been externally edited. |

## Public-copy checklist

- Public questions do not require an account or email registration.
- Authenticated history remains clearly optional.
- The product is described as an unofficial fan reference, not official support or a tournament
  ruling.
- Wizards and Scryfall are named with non-endorsement language.
- Terms describe public questions, cache retention, account deletion, acceptable use, AI limits,
  source handling, and support contact.
- Privacy describes public-question processing, authenticated data, OpenAI, Firebase, Cloud SQL,
  logging, cache retention, browser storage, deletion, and privacy requests.
- Support is available by email for source corrections, privacy, accessibility, account deletion,
  and attribution concerns.

## Go/no-go record

Before production, record reviewer name, date, evidence URL/version, conclusion, and conditions
for each policy row. A policy link, code attribution, or passing automated test is not itself
approval. Any later addition of payment, advertising, card images, data export, mandatory
registration, new regions, or anonymous persistence triggers a fresh review.
