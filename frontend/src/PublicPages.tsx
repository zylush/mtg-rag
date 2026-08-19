import { ArrowRight, BookOpenCheck, ExternalLink, FileText, ShieldCheck } from "lucide-react"
import type { ReactNode } from "react"

import { BrandMark } from "./BrandMark"
import { AppLink } from "./routing"

interface PublicAuthActions {
  authenticated?: boolean
  onSignIn?: () => void
  signingIn?: boolean
  signInError?: boolean
}

function PublicHeader({ authenticated = false, onSignIn, signingIn }: PublicAuthActions) {
  return (
    <header className="public-header">
      <AppLink
        className="public-brand"
        to={authenticated ? "/desk" : "/"}
        aria-label={authenticated ? "Back to MTG Rules Desk" : "MTG Rules Desk home"}
      >
        <BrandMark className="wordmark-mark" />
        <span>
          <strong>MTG Rules Desk</strong>
          <small>Grounded rules reference</small>
        </span>
      </AppLink>
      <nav aria-label="Public">
        <AppLink to="/about">About</AppLink>
        {authenticated ? (
          <AppLink className="public-nav-cta" to="/desk">
            Back to desk
          </AppLink>
        ) : (
          <button
            className="public-nav-cta"
            type="button"
            disabled={signingIn}
            onClick={onSignIn}
          >
            {signingIn ? "Signing in..." : "Sign in"}
          </button>
        )}
      </nav>
    </header>
  )
}

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div>
        <span className="eyebrow">MTG Rules Desk</span>
        <p>Unofficial fan reference for English-language rules questions.</p>
      </div>
      <nav aria-label="Footer">
        <AppLink to="/about">About</AppLink>
        <AppLink to="/terms">Terms of Service</AppLink>
        <AppLink to="/privacy">Privacy Policy</AppLink>
        <a href="mailto:paoloinigo30@gmail.com">Support</a>
      </nav>
      <p className="attribution-copy">
        MTG Rules Desk is unofficial fan content. Wizards of the Coast neither approves nor
        endorses this app. Card data and rulings are provided by Scryfall; Scryfall does not
        endorse this app.
      </p>
    </footer>
  )
}

function PublicLayout({
  authenticated = false,
  onSignIn,
  signingIn = false,
  signInError = false,
  children,
}: {
  children: ReactNode
} & PublicAuthActions) {
  return (
    <div className="public-site">
      <PublicHeader authenticated={authenticated} onSignIn={onSignIn} signingIn={signingIn} />
      {signInError && (
        <div className="public-auth-error status-message error" role="alert">
          Sign-in did not complete. Check popup permissions and try again.
        </div>
      )}
      {children}
      <PublicFooter />
    </div>
  )
}

function RulingLedgerPreview() {
  return (
    <section className="ruling-ledger" aria-labelledby="preview-heading">
      <div className="ledger-heading">
        <div>
          <span className="eyebrow">Ruling ledger</span>
          <h2 id="preview-heading">A ruling you can trace.</h2>
        </div>
        <span className="ledger-stamp">Question / Answer / Sources</span>
      </div>
      <div className="ledger-stack">
        <span className="ledger-sheet-back" aria-hidden="true" />
        <div className="ledger-sheet">
          <div className="ledger-section">
            <span className="section-label">Table question</span>
            <p className="ledger-question">
              If a spell loses its only target, does the spell still resolve?
            </p>
          </div>
          <div className="ledger-rule" aria-hidden="true" />
          <div className="ledger-section">
            <span className="section-label">Desk ruling</span>
            <p>
              The spell does not resolve when all of its targets are illegal as it tries to
              resolve. The game rules put it into its owner's graveyard.
            </p>
          </div>
          <div className="ledger-source-tabs" aria-label="Example sources">
            <span>
              <BookOpenCheck aria-hidden="true" size={15} />
              CR 608.2b
            </span>
            <span>Targets checked on resolution</span>
          </div>
        </div>
      </div>
    </section>
  )
}

export function WelcomePage({ onSignIn, signingIn, signInError }: PublicAuthActions) {
  return (
    <PublicLayout onSignIn={onSignIn} signingIn={signingIn} signInError={signInError}>
      <main className="public-page welcome-page">
        <section className="welcome-hero">
          <div className="hero-copy">
            <span className="eyebrow">Rules answers with receipts</span>
            <h1>Settle the ruling. Keep the game moving.</h1>
            <p className="hero-lede">
              Ask an MTG rules question and get a concise answer grounded in the Comprehensive
              Rules, current Oracle text, and official rulings.
            </p>
            <div className="hero-actions">
              <button
                className="primary-button"
                type="button"
                disabled={signingIn}
                onClick={onSignIn}
              >
                {signingIn ? "Signing you in..." : "Sign in with Google"}
                <ArrowRight aria-hidden="true" size={17} />
              </button>
              <AppLink className="text-button hero-secondary" to="/about">
                See how it works
              </AppLink>
            </div>
            <p className="hero-trust-note">
              <ShieldCheck aria-hidden="true" size={16} />
              Your API key stays on the server. Answers show their sources.
            </p>
            <p className="hero-note">
              Live questions require an account and an internet connection. The preview on this
              page is static.
            </p>
          </div>
          <RulingLedgerPreview />
        </section>

        <section
          className="trust-strip source-trust-rail"
          id="how-it-works"
          aria-label="Reference sources"
        >
          <article>
            <BookOpenCheck aria-hidden="true" />
            <h2>Comprehensive Rules</h2>
            <p>General rules and corner cases, cited by rule number.</p>
          </article>
          <article>
            <FileText aria-hidden="true" />
            <h2>Oracle text</h2>
            <p>Current card wording, identified by the exact card record.</p>
          </article>
          <article>
            <ShieldCheck aria-hidden="true" />
            <h2>Official rulings</h2>
            <p>Dated card-specific clarification when the question needs it.</p>
          </article>
        </section>

        <section className="public-limitations">
          <span className="eyebrow">Know the boundary</span>
          <h2>Built for rules questions, not every MTG question.</h2>
          <p>
            MTG Rules Desk is English-only in v1. It is an unofficial fan reference, not Wizards
            of the Coast support, a tournament ruling, or a substitute for a judge.
          </p>
        </section>
      </main>
    </PublicLayout>
  )
}

export function AboutPage({
  authenticated = false,
  onSignIn,
  signingIn,
  signInError,
}: PublicAuthActions) {
  return (
    <PublicLayout
      authenticated={authenticated}
      onSignIn={onSignIn}
      signingIn={signingIn}
      signInError={signInError}
    >
      <main className="public-page document-page about-page">
        <div className="document-intro">
          <span className="eyebrow">About the desk</span>
          <h1>About MTG Rules Desk</h1>
          <p>
            A focused reference for players who want to settle a rules question without losing the
            thread of the game.
          </p>
        </div>

        <div className="about-grid">
          <section>
            <span className="section-label">The purpose</span>
            <h2>Make a precise game state easier to explain.</h2>
            <p>
              The desk helps turn card names, zones, timing, controllers, and actions into a
              question that can be checked against authoritative reference material.
            </p>
          </section>
          <section id="how-an-answer-is-produced">
            <span className="section-label">The method</span>
            <h2>How an answer is produced</h2>
            <ol className="method-list">
              <li>Normalize the question and identify explicit card names or rule references.</li>
              <li>Retrieve relevant rules, Oracle text, and ruling passages.</li>
              <li>Draft a grounded answer with assumptions and confidence.</li>
              <li>Validate every citation and ask for clarification when evidence is incomplete.</li>
            </ol>
          </section>
        </div>

        <section className="about-section">
          <span className="section-label">Sources and attribution</span>
          <h2>Reference material, clearly named.</h2>
          <p>
            The corpus combines the Wizards of the Coast Comprehensive Rules with Oracle card and
            ruling data provided through Scryfall. MTG Rules Desk is unofficial fan content.
            Wizards of the Coast neither approves nor endorses it, and Scryfall does not endorse
            this app.
          </p>
        </section>

        <section className="about-section about-boundary">
          <span className="section-label">The boundary</span>
          <h2>When the desk should not pretend to know.</h2>
          <p>
            Answers may ask for more context or abstain when a missing zone, timing detail, or
            card identity could change the result. Strategy, deck building, card prices, and
            tournament policy are outside the v1 scope.
          </p>
        </section>
      </main>
    </PublicLayout>
  )
}

type LegalKind = "terms" | "privacy"

interface LegalSection {
  id: string
  title: string
  paragraphs: readonly ReactNode[]
  items?: readonly ReactNode[]
}

const TERMS_SECTIONS: LegalSection[] = [
  { id: "service", title: "1. Service", paragraphs: ["Describe the MTG Rules Desk service and its supported scope here."] },
  { id: "accounts", title: "2. Accounts and eligibility", paragraphs: ["Provide operator-approved account, age, and eligibility terms here."] },
  { id: "use", title: "3. Acceptable use", paragraphs: ["Provide operator-approved rules for using the service here."] },
  { id: "sources", title: "4. Sources and attribution", paragraphs: ["Describe third-party sources, links, attribution, and non-endorsement language here."] },
  { id: "answers", title: "5. AI-generated answers", paragraphs: ["Describe limitations, disclaimers, and the non-official nature of answers here."] },
  { id: "account-controls", title: "6. Deletion and termination", paragraphs: ["Describe conversation deletion, account deletion, and termination conditions here."] },
  { id: "changes", title: "7. Changes and contact", paragraphs: ["Provide change-notice, governing-law, dispute, and support-contact language here."] },
]

const PRIVACY_SECTIONS: LegalSection[] = [
  {
    id: "scope",
    title: "1. Scope and summary",
    paragraphs: [
      "This Privacy Policy explains how MTG Rules Desk processes information when you sign in, ask a rules question, save or delete a conversation, submit feedback, install the progressive web app, or contact support.",
      "MTG Rules Desk is an unofficial, English-language Magic: The Gathering rules reference. Please do not include personal, confidential, or sensitive information in a rules question or feedback comment.",
    ],
  },
  {
    id: "data",
    title: "2. Information we process",
    paragraphs: [
      "We process the information needed to authenticate you, answer questions, operate usage limits, retain your history, and protect the service.",
    ],
    items: [
      "Account information: your Firebase user ID and email address received from Google sign-in.",
      "Rules-desk content: your questions, generated answers, assumptions, confidence, citations, conversation titles, and creation times.",
      "Feedback: a positive or negative rating, an optional comment, and the answer the feedback concerns.",
      "Usage and reliability data: ask-attempt timestamps, daily answer counts, model and cache status, request identifiers, token counts, latency, response size, route, status code, and error category.",
      "Support information: your email address and anything you choose to include when you contact us.",
      "Infrastructure metadata: Google and other infrastructure providers may process IP address, browser, device, and request metadata to deliver and secure the service.",
    ],
  },
  {
    id: "use",
    title: "3. How we use information",
    paragraphs: [
      "We use this information to verify your identity, retrieve relevant MTG rules and card passages, generate and save grounded answers, show conversation history, enforce usage limits, process feedback, investigate failures or abuse, secure the service, and respond to support or privacy requests.",
      "We do not use personal information for advertising, sell it, rent it, or use it to make decisions that produce legal or similarly significant effects.",
    ],
  },
  {
    id: "ai",
    title: "4. OpenAI and RAG processing",
    paragraphs: [
      "OpenAI receives your question when it creates a search embedding. When an answer is not served from cache, OpenAI receives your question, selected public MTG reference passages, and a one-way pseudonymous safety identifier to generate a structured answer. The backend requests that generated responses are not stored by the OpenAI Responses API.",
      "We do not intentionally send your email address or raw Firebase user ID to OpenAI. Do not place personal information in a question, because question text is part of the request. OpenAI processes API data under its own applicable terms and privacy commitments.",
      "The RAG system can reduce unsupported answers, but it cannot guarantee that every answer is correct. Retrieved citations, confidence labels, clarification requests, and abstention are product safeguards, not automated decisions about you.",
    ],
  },
  {
    id: "providers",
    title: "5. Service providers and sources",
    paragraphs: [
      "We disclose information only as needed to operate the service, comply with law, protect rights and safety, or complete a business transfer. The current service uses the following providers:",
    ],
    items: [
      "Google Firebase Authentication for Google sign-in and identity tokens.",
      "Firebase Hosting and Google Cloud Run to deliver the web app and API.",
      "Google Cloud SQL for PostgreSQL account, conversation, answer, citation, feedback, quota, and cache records.",
      "Google Cloud Logging and Monitoring for content-free application telemetry and infrastructure operations.",
      "Google Secret Manager for server credentials. Secret values are not sent to the browser.",
      "OpenAI for question embeddings and grounded answer generation.",
      "Wizards of the Coast and Scryfall as sources for public rules, Oracle card data, and rulings. User questions are not sent to those source sites by the ask flow.",
    ],
  },
  {
    id: "cache",
    title: "6. Semantic cache",
    paragraphs: [
      "Eligible high-confidence, non-ambiguous questions, their embeddings, generated answers, and citation identifiers may remain in a shared semantic cache for up to seven days. The cache is used to return a previously validated answer for a sufficiently similar question using the same active corpus and model configuration.",
      "A cache record is not linked to a user account, but its normalized question text is retained. This means deleting an account does not immediately target that separate cache entry; it expires automatically within the cache period. Avoid placing identifying or sensitive details in questions.",
    ],
  },
  {
    id: "retention",
    title: "7. Retention and deletion",
    paragraphs: [
      "Saved conversations, messages, citations, feedback, account identifiers, and usage records remain in Cloud SQL while your account is active unless you delete a conversation or your account. The current application does not apply a shorter automatic retention period to saved history.",
      "Deleting a conversation removes that conversation, its messages, citations, and associated feedback. Deleting your account removes application-owned records associated with your account and then requests deletion of the Firebase identity. Sign-out only ends the browser session and does not delete saved data.",
      "Backups, security records, provider records, and information required by law may persist for a limited period under provider or operational retention settings. Shared semantic-cache entries expire separately as described above.",
    ],
  },
  {
    id: "browser",
    title: "8. Browser storage and the PWA",
    paragraphs: [
      "Firebase Authentication uses browser storage to keep you signed in. The progressive web app service worker caches static files such as HTML, JavaScript, CSS, fonts, and icons so the interface can load reliably. Live questions and conversation history still require an internet connection.",
      "The application marks API requests as no-store and does not configure the service worker to cache API responses. We do not use advertising cookies or analytics in the current application. If this changes, this policy and any required consent controls will be updated first.",
    ],
  },
  {
    id: "security",
    title: "9. Security",
    paragraphs: [
      "We use HTTPS, Firebase token verification with revocation checks, account-ownership checks, bounded requests, server-side credentials, Google Secret Manager, and restricted service identities to protect information. Application telemetry is designed not to contain raw question or answer text.",
      "No security measure can guarantee absolute protection. If you believe your account or information has been compromised, contact us promptly.",
    ],
  },
  {
    id: "rights",
    title: "10. Your choices and privacy rights",
    paragraphs: [
      "You can review and delete individual conversations in the app, sign out, or request account deletion from Settings. Depending on where you live, you may also have rights to access, correct, delete, restrict, object to, or receive a portable copy of personal information, and to appeal a denied request.",
      <>
        To make a request,{" "}
        <a href="mailto:paoloinigo30@gmail.com">email the privacy contact</a>. We may need to
        verify your identity before completing a request. You will not be discriminated against
        for exercising an applicable privacy right.
      </>,
      "We do not sell personal information, share it for cross-context behavioral advertising, or use it for targeted advertising. Because the current service does not perform those activities, a Global Privacy Control signal does not change its behavior.",
    ],
  },
  {
    id: "international-minors",
    title: "11. International processing and minors",
    paragraphs: [
      "Our providers may process information in countries other than the one where you live. Those countries may have different data-protection laws. We use provider contracts and available safeguards where required.",
      "MTG Rules Desk is not designed to solicit personal information from children. The service does not currently perform age verification. If you believe a child submitted personal information, contact us so we can review and delete it as appropriate.",
    ],
  },
  {
    id: "updates",
    title: "12. Updates and contact",
    paragraphs: [
      "We may update this policy when the product, providers, or legal requirements change. The date at the top of this page will identify the latest revision. Material changes may also be announced in the application when appropriate.",
      <>
        Questions, requests, or complaints can be sent to{" "}
        <a href="mailto:paoloinigo30@gmail.com">paoloinigo30@gmail.com</a>. MTG Rules Desk
        currently provides online and email contact only; no public postal address is listed.
      </>,
    ],
  },
]

export function LegalDocumentPage({
  authenticated = false,
  onSignIn,
  signingIn,
  signInError,
  kind,
}: {
  kind: LegalKind
} & PublicAuthActions) {
  const isTerms = kind === "terms"
  const title = isTerms ? "Terms of Service" : "Privacy Policy"
  const sections = isTerms ? TERMS_SECTIONS : PRIVACY_SECTIONS
  const dateLine = isTerms
    ? "Effective date: operator review required · Last updated: operator review required"
    : "Effective date: August 17, 2026 · Last updated: August 17, 2026"

  return (
    <PublicLayout
      authenticated={authenticated}
      onSignIn={onSignIn}
      signingIn={signingIn}
      signInError={signInError}
    >
      <main className="public-page document-page legal-page">
        <div className="document-intro">
          <span className="eyebrow">MTG Rules Desk legal document</span>
          <h1>{title}</h1>
          <p>{dateLine}</p>
        </div>

        <div className="legal-review-banner" role="note">
          <strong>Pending legal review</strong>
          <span>
            {isTerms
              ? "This page is a structured content outline. Replace the marked sections with operator-approved policy text before public launch."
              : "This implementation-aligned draft must be reviewed and approved by the operator and qualified counsel before public launch."}
          </span>
        </div>

        <div className="legal-layout">
          <aside className="legal-contents" aria-label="On this page">
            <span className="section-label">On this page</span>
            <nav>
              {sections.map((section) => (
                <a key={section.id} href={`#${section.id}`}>
                  {section.title}
                </a>
              ))}
            </nav>
          </aside>
          <article className="legal-copy">
            {sections.map((section) => (
              <section key={section.id} id={section.id}>
                <h2>{section.title}</h2>
                {section.paragraphs.map((paragraph, index) => (
                  <p key={`${section.id}-paragraph-${index}`}>{paragraph}</p>
                ))}
                {section.items && (
                  <ul>
                    {section.items.map((item, index) => (
                      <li key={`${section.id}-item-${index}`}>{item}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </article>
        </div>

        <p className="legal-source-note">
          {isTerms ? (
            <>
              This outline is not legal advice. Contact the operator listed in the final reviewed
              document with questions.
              <ExternalLink aria-hidden="true" size={14} />
            </>
          ) : (
            "This policy describes the current implementation. It is not a substitute for legal review."
          )}
        </p>
      </main>
    </PublicLayout>
  )
}
