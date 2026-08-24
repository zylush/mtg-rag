# WotC and Scryfall source-use review packet

**Prepared:** 2026-08-24
**Release target:** Public development preview
**Status:** Operator attests that the qualified reviewer approved all ten questions without conditions; reviewer identity and qualification evidence are not retained here
**Important:** This is an implementation record and review aid, not legal advice, permission, or
an assertion that the use is lawful.

## 1. Decision requested

A qualified reviewer should decide whether the implementation described below may be publicly
deployed under the current Wizards Fan Content Policy, Wizards Terms, Scryfall requirements, and
applicable law. If any use is not clearly permitted, obtain written permission or require a
specific product/source change before publication.

The highest-risk question is not the disclaimer or account flow. It is whether automated download,
private storage, embedding, retrieval, and short public excerpts from the full Comprehensive Rules,
Oracle card text, and rulings are permitted. The Wizards Fan Content Policy says fan content must
be free and unofficial, but also distinguishes original fan work from verbatim copying or reposting
Wizards material. The current Wizards Terms separately restrict automated data mining and copying
except where expressly authorized. Those provisions require qualified interpretation for this
specific RAG architecture.

## 2. Current authoritative policy links

- [Wizards Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy), shown as
  last updated November 15, 2017 when checked on 2026-08-24.
- [Wizards Terms](https://company.wizards.com/en/legal/terms), shown as last updated December 10,
  2025 when checked on 2026-08-24.
- [Official Comprehensive Rules page](https://magic.wizards.com/en/rules).
- [Scryfall API documentation](https://scryfall.com/docs/api) and
  [bulk-data documentation](https://scryfall.com/docs/api/bulk-data). The documentation endpoint
  denied the automated review client, so a human reviewer must open the current pages directly.

Policies can change. Record the URLs, review date, reviewer, and any written permission rather than
relying on this packet's check date.

## 3. What the ingestion system does

### Wizards Comprehensive Rules

- Discovers the current TXT download from the official rules page and permits only the
  `media.wizards.com` source host.
- Downloads the complete rules text on a schedule, hashes it, and stores an immutable raw snapshot
  in an operator-owned private GCS bucket.
- Parses individual numbered rules and glossary entries, stores them in private PostgreSQL tables,
  and creates embeddings through the OpenAI API.
- Retains version identifiers, source URL, fetch time, effective date, checksum, and active/inactive
  state for rollback and citation auditability.

### Scryfall cards and rulings

- Discovers `default_cards` and `rulings` through Scryfall's bulk-data catalog at
  `api.scryfall.com/bulk-data`; bulk payloads are accepted only from `data.scryfall.io`.
- Sends the identifying user agent `MTG-RAG/0.1 (scheduled corpus refresh)`.
- Stores Oracle identity, names, face text, layout, dated ruling text, ruling source, and
  attribution. It does not ingest card images, prices, deck data, or user data from Scryfall.
- Stores immutable private snapshots, versioned private PostgreSQL records, and OpenAI embeddings.
- Does not expose a Scryfall-compatible proxy, bulk export, corpus listing endpoint, SQL endpoint,
  or model/tool endpoint.

Relevant implementation anchors include `backend/app/ingestion/cli.py`,
`backend/app/ingestion/pipeline.py`, `backend/app/ingestion/rules.py`,
`backend/app/ingestion/scryfall.py`, and `backend/app/retrieval/embeddings.py`.

## 4. What a user can see

- Anyone can ask a free question through `/v1/public/ask` without payment, download, subscription,
  survey, account, or email registration.
- An account is optional and adds saved history, feedback, quota display, and account controls.
- The answer is original model-generated explanatory text, not a corpus export.
- Each citation shows the source label and canonical link. Authenticated answers currently also show
  a model-generated citation claim; public answers show source labels/links without claim text.
- The operator approved the normalized exact-excerpt design on 2026-08-24. The local
  `mtg-answer-v12` candidate requires an excerpt copied contiguously from the normalized cited
  passage and capped at 320 characters. Substantive answers require a citation; invalid output
  receives one repair and then abstains. Citation-only repair receives the prior structured
  candidate plus bounded exact options for only the cited or failing passages; the validator and
  one-repair limit are unchanged.
- That engineering approval is not qualified source-use or legal clearance. Read-only deployment
  reconciliation on 2026-08-24 confirmed all four development runtime leaves still use the retained
  `v11` digest `sha256:df0644eb31a4fafccd4e55deeccabd2dfe5dc3d1ca40d29fccde70ca0f6d7b66`.
  Its retained 121-case packet failed required-reference citation coverage, expected behavior, and
  cached-latency evidence. No `v12` build or qualification has occurred. The frozen 197-file `v12`
  manifest is `bd151f9ce5574473913a4866c6da4dba8202e3e5a32a85dc27509579f728e0ea`.
- The UI does not show Wizards logos, card frames, card art, or Scryfall card images.
- Rate limits, bounded response size, and the absence of list/export endpoints prevent the app from
  serving as a practical source-database mirror.

## 5. Names, notices, and presentation

The local public footer, About page, Terms, Privacy page, and authenticated settings identify the
product as unofficial, state non-endorsement, attribute Wizards and Scryfall, and link to source
policies. Local public and authenticated headers separately label the service as a development
preview, and the local Terms state that it is not production-ready and offers no service-level
commitment. This preview label does not replace the Wizards notice.

Read-only browser QA initially found that the development About and Privacy routes were published
while `/terms` still served the older placeholder outline. The operator then authorized exactly one
Firebase Hosting-only deployment of the tested 19-file artifact, aggregate SHA-256
`2c23d3d48194327cec675e2b9cf70fc7dc9afda3777b20384c92453f94e80fae`, to
`mtg-rules-desk-dev`. The deploy completed once without retry. Post-deploy read-only browser QA
confirmed the operational Terms, August 24, 2026 date, preview label, support contact, and source
notices are live; the old placeholder is absent and the inspected public routes emitted no console
errors. The pages continue to identify the copy as pending qualified legal review.
The title **MTG Rules Desk** and text references to **Magic: The Gathering**, **Wizards of the
Coast**, card names, rules numbers, and source labels remain visible. A qualified reviewer must
decide whether these are acceptable descriptive/nominative references or require naming changes or
written permission under the current policy language concerning marks.

Current copy is in `frontend/src/PublicPages.tsx` and `frontend/src/App.tsx`. The implementation
record is `docs/operations/ATTRIBUTION-AND-LAUNCH.md`.

## 6. Third-party processing that must be included in the decision

- Complete changed source documents are sent to OpenAI to create embeddings during ingestion.
- A selected set of at most eight retrieved source passages is sent to OpenAI with a user question
  during an uncached answer request. The Responses API call requests `store=false`.
- Raw source snapshots and parsed source text are stored in private Google Cloud services.
- User questions are not sent to Wizards or Scryfall during the ask flow.

Review must cover both public display and these private storage/processor disclosures. Approval of
short excerpts alone is not approval of full-corpus download, storage, or processor transmission.

## 7. Required reviewer answers

Record an explicit answer and rationale for every item:

1. May the service automatically download and privately retain the complete current Comprehensive
   Rules TXT plus versioned rollback snapshots?
2. May it parse, embed through OpenAI, and search that complete rules corpus to create original
   explanatory answers?
3. May it display linked exact rules excerpts of no more than 320 characters per citation?
4. May it use **MTG Rules Desk**, **Magic: The Gathering**, card names, rule numbers, and source
   labels in the current non-logo presentation?
5. Is the current Wizards notice sufficient and placed frequently enough?
6. Is the free public question path sufficient for the policy's no-registration access condition
   while optional accounts retain saved history?
7. May the service download, privately retain, embed, and search Scryfall `default_cards` and
   `rulings` bulk data under current Scryfall requirements?
8. Is `MTG-RAG/0.1 (scheduled corpus refresh)` an adequate identifying user agent, and are any
   contact details, delays, refresh ceilings, or attribution changes required?
9. Does sending source text to OpenAI for embeddings/generation require permission, contract
   changes, or a different processor configuration?
10. Are the local Terms, Privacy, support copy, takedown path, and source-correction path adequate
    for a public development preview?

Any **no**, **unclear**, or conditional answer remains a release gate. Silence is not permission.

## 8. Operator confirmation and retained evidence

Complete this only after qualified review:

```text
Reviewer name and qualification:
Review date and policy-version dates:
Decision: APPROVED / APPROVED WITH CONDITIONS / NOT APPROVED
Approved excerpt maximum and presentation:
Approved corpus/storage/processor uses:
Required product or copy changes:
Written permission reference, if any:
Operator acceptance name/date:
Published Terms/Privacy version and URL:
```

Operator attestation received on 2026-08-24: **the operator states that the qualified reviewer
approved every question 1 through 10 without conditions and authorizes the v12 development
qualification**. This records the operator-supplied decision; it does not independently verify or
invent the reviewer's name, license, jurisdiction, policy-version dates, rationale, or private
written evidence. Those metadata should still be retained outside the public repository before a
production claim relies on the review.

Retain the completed review, policy snapshots or checksums where permitted, written permission,
and the exact deployed source/copy commit with the release evidence. Do not place private legal
communications or credentials in the public repository.
