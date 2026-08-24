# Qualified legal review handoff

**Prepared:** 2026-08-24
**Release target:** Public development preview
**Purpose:** Supply a qualified reviewer with enough product, source-use, and data-processing facts
to make an explicit decision. This checklist is not legal advice or permission.

## 1. Choose the reviewer

Use a licensed lawyer or another reviewer whose qualification can be documented for the relevant
jurisdictions. The review spans intellectual property, copyright/trademark and fan-content policy,
online service terms, and privacy/consumer disclosures. One reviewer may cover all areas, or the
review may need separate IP and privacy/consumer specialists.

## 2. Supply this package

Give the reviewer:

1. The operator's legal name or entity, operating jurisdiction, intended user countries, whether
   minors are expected, and the support/takedown contact. Private identity details may be supplied
   directly to counsel and need not be committed to the repository.
2. The public development URLs:
   - `https://mtg-rules-desk-dev.web.app/`
   - `https://mtg-rules-desk-dev.web.app/about`
   - `https://mtg-rules-desk-dev.web.app/terms`
   - `https://mtg-rules-desk-dev.web.app/privacy`
3. [SOURCE-USE-REVIEW-PACKET.md](SOURCE-USE-REVIEW-PACKET.md), including its ten required reviewer
   questions, plus [ATTRIBUTION-AND-LAUNCH.md](ATTRIBUTION-AND-LAUNCH.md).
4. The current official Wizards Fan Content Policy, Wizards Terms, official Comprehensive Rules
   page, Scryfall API/bulk-data guidance, and a record of the URL and version/check date reviewed.
5. The technical source-use facts: scheduled full-rules download; private immutable snapshots;
   parsed private PostgreSQL corpus; OpenAI embeddings; Scryfall `default_cards` and `rulings` bulk
   data; no card images, price data, public corpus export, source-compatible proxy, or database/API
   mirror.
6. The public-display contract: original explanatory answers, linked citations, normalized exact
   excerpts copied contiguously from the cited passage and capped at 320 characters, one repair then
   abstention, rate limits, bounded responses, and no mandatory account/email registration for a
   public question.
7. The processor and retention facts: Firebase Authentication/Hosting, Google Cloud Run/SQL/GCS,
   OpenAI embeddings/generation with Responses API `store=false`, optional saved account history,
   shared eligible-question cache up to seven days, operational logs, deletion behavior, and backup
   or provider retention boundaries described by the live Privacy Policy.
8. The product/business facts: free public questions, no paid plan or purchase flow, no current ads,
   unofficial development-preview labeling, optional accounts for saved history, and no claimed SLA
   or official-judge function.
9. Representative screenshots or outputs showing the exact notice, source links, citation excerpt
   presentation, Terms, Privacy, About, and support path. Do not send credentials or real user data.
10. Relevant Google Cloud/Firebase and OpenAI contractual or data-processing terms available to the
    operator, including any DPA or regional-processing configuration that counsel asks to review.

Current engineering identifiers for the review package are:

- deployed Hosting artifact SHA-256:
  `2c23d3d48194327cec675e2b9cf70fc7dc9afda3777b20384c92453f94e80fae`;
- local backend v12 source-manifest SHA-256:
  `bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`; and
- deployed backend: retained v11 digest
  `sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`,
  which has not qualified for release quality.

## 3. Require this returned record

Do not accept a verbal `looks fine`. Ask the reviewer to return:

```text
Reviewer name and qualification/licensing jurisdiction:
Review date and policy/terms version dates:
Jurisdictions and release scope reviewed:
Decision: APPROVED / APPROVED WITH CONDITIONS / NOT APPROVED
Answers and rationale for source-use questions 1 through 10:
Approved exact-excerpt maximum and presentation:
Approved corpus download, snapshot, storage, embedding, retrieval, and processor uses:
Approved names, marks, notices, source links, and attribution placement:
Scryfall user-agent, rate, refresh, contact, and attribution requirements:
Required Terms, Privacy, support, product, data-flow, or retention changes:
Written-permission reference, if required:
Effective date, signature, or other evidence of the decision:
```

Any `no`, `unclear`, unanswered, or conditional item remains a gate until its condition is satisfied
and rechecked. Silence is not permission.

## 4. Operator acceptance and retention

After review, record the operator's acceptance date, the exact deployed artifact/source identifiers,
the published Terms/Privacy URLs and revision dates, and every completed condition. Retain the full
legal advice and any written permission privately. Commit only a sanitized decision summary that
does not expose privileged communications, credentials, personal identifiers, or provider secrets.
