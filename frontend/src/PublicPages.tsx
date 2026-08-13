import { ArrowRight, BookOpenCheck, ExternalLink, FileText, ShieldCheck } from "lucide-react"
import type { ReactNode } from "react"

import { AppLink } from "./routing"

function PublicHeader() {
  return (
    <header className="public-header">
      <AppLink className="public-brand" to="/" aria-label="MTG Rules Desk home">
        <span className="wordmark-mark" aria-hidden="true">
          R
        </span>
        <span>
          <strong>MTG Rules Desk</strong>
          <small>Grounded rules reference</small>
        </span>
      </AppLink>
      <nav aria-label="Public">
        <AppLink to="/about">About</AppLink>
        <a href="#how-it-works">How it works</a>
        <AppLink className="public-nav-cta" to="/login">
          Sign in
        </AppLink>
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
        Wizards of the Coast neither approves nor endorses this app. Card data and rulings are
        provided by Scryfall; Scryfall does not endorse this app.
      </p>
    </footer>
  )
}

function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="public-site">
      <PublicHeader />
      {children}
      <PublicFooter />
    </div>
  )
}

function SourceSpinePreview() {
  return (
    <section className="source-preview" aria-labelledby="preview-heading">
      <div className="preview-heading">
        <span className="eyebrow">A sample from the desk</span>
        <h2 id="preview-heading">A ruling you can trace.</h2>
        <p className="preview-path">Question → Answer → Sources</p>
      </div>
      <div className="preview-card">
        <div className="preview-rail" aria-hidden="true">
          <span>Q</span>
          <span>A</span>
          <span>S</span>
        </div>
        <div className="preview-content">
          <span className="section-label">Example question</span>
          <p className="preview-question">
            If a spell loses its only target, does the spell still resolve?
          </p>
          <div className="preview-divider" />
          <span className="section-label">Example answer</span>
          <p>
            The spell is countered by the game rules when all of its targets are illegal as it
            tries to resolve.
          </p>
          <div className="preview-source">
            <BookOpenCheck aria-hidden="true" size={16} />
            Comprehensive Rules 608.2b
          </div>
        </div>
      </div>
    </section>
  )
}

export function WelcomePage() {
  return (
    <PublicLayout>
      <main className="public-page welcome-page">
        <section className="welcome-hero">
          <div className="hero-copy">
            <span className="eyebrow">Citation-first rules reference</span>
            <h1>Settle the rules question. Keep the game moving.</h1>
            <p className="hero-lede">
              Ask about a game state and get a concise ruling grounded in the Comprehensive Rules,
              current Oracle text, and attributed card rulings.
            </p>
            <div className="hero-actions">
              <AppLink className="primary-button" to="/login">
                Sign in with Google
                <ArrowRight aria-hidden="true" size={17} />
              </AppLink>
              <AppLink className="text-button hero-secondary" to="/about">
                See how it works
              </AppLink>
            </div>
            <p className="hero-note">
              Live questions require an account and an internet connection. The preview on this
              page is static.
            </p>
          </div>
          <SourceSpinePreview />
        </section>

        <section className="trust-strip" id="how-it-works" aria-label="How it works">
          <article>
            <BookOpenCheck aria-hidden="true" />
            <h2>Trace the source</h2>
            <p>Every material claim points back to a rules or card passage.</p>
          </article>
          <article>
            <ShieldCheck aria-hidden="true" />
            <h2>See the assumptions</h2>
            <p>Missing game-state details are called out instead of hidden.</p>
          </article>
          <article>
            <FileText aria-hidden="true" />
            <h2>Keep the ruling</h2>
            <p>Signed-in players can revisit conversations and delete them later.</p>
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

export function AboutPage() {
  return (
    <PublicLayout>
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
  body: string
}

const TERMS_SECTIONS: LegalSection[] = [
  { id: "service", title: "1. Service", body: "Describe the MTG Rules Desk service and its supported scope here." },
  { id: "accounts", title: "2. Accounts and eligibility", body: "Provide operator-approved account, age, and eligibility terms here." },
  { id: "use", title: "3. Acceptable use", body: "Provide operator-approved rules for using the service here." },
  { id: "sources", title: "4. Sources and attribution", body: "Describe third-party sources, links, attribution, and non-endorsement language here." },
  { id: "answers", title: "5. AI-generated answers", body: "Describe limitations, disclaimers, and the non-official nature of answers here." },
  { id: "account-controls", title: "6. Deletion and termination", body: "Describe conversation deletion, account deletion, and termination conditions here." },
  { id: "changes", title: "7. Changes and contact", body: "Provide change-notice, governing-law, dispute, and support-contact language here." },
]

const PRIVACY_SECTIONS: LegalSection[] = [
  { id: "data", title: "1. Data we process", body: "Describe Firebase identity, questions, answers, conversations, feedback, and quota data here." },
  { id: "providers", title: "2. Service providers", body: "Describe OpenAI, PostgreSQL, Cloud Storage, Firebase, and monitoring providers here." },
  { id: "use", title: "3. How data is used", body: "Describe authentication, answer generation, retrieval, support, security, and operations here." },
  { id: "retention", title: "4. Retention and deletion", body: "Provide operator-approved retention periods and account/conversation deletion behavior here." },
  { id: "cookies", title: "5. Cookies, storage, and the PWA", body: "Describe Firebase auth storage, service-worker behavior, and any optional analytics here." },
  { id: "rights", title: "6. Rights and regional processing", body: "Provide applicable rights, regional processing, minors, and contact language here." },
  { id: "updates", title: "7. Updates and contact", body: "Provide policy-update and privacy-contact language here." },
]

export function LegalDocumentPage({ kind }: { kind: LegalKind }) {
  const isTerms = kind === "terms"
  const title = isTerms ? "Terms of Service" : "Privacy Policy"
  const sections = isTerms ? TERMS_SECTIONS : PRIVACY_SECTIONS

  return (
    <PublicLayout>
      <main className="public-page document-page legal-page">
        <div className="document-intro">
          <span className="eyebrow">MTG Rules Desk legal document</span>
          <h1>{title}</h1>
          <p>Effective date: operator review required · Last updated: operator review required</p>
        </div>

        <div className="legal-review-banner" role="note">
          <strong>Pending legal review</strong>
          <span>
            This page is a structured content outline. Replace the marked sections with
            operator-approved policy text before public launch.
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
                <p>{section.body}</p>
              </section>
            ))}
          </article>
        </div>

        <p className="legal-source-note">
          This outline is not legal advice. Contact the operator listed in the final reviewed
          document with questions.
          <ExternalLink aria-hidden="true" size={14} />
        </p>
      </main>
    </PublicLayout>
  )
}
