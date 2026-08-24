import {
  ArrowRight,
  BookOpenCheck,
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  ShieldCheck,
} from "lucide-react"
import { useMemo, useState, type FormEvent, type ReactNode } from "react"

import { BrandMark } from "./BrandMark"
import {
  PATCH_HISTORY,
  PATCH_HISTORY_CAPTURE,
  PATCH_RELEASES,
  type PatchHistoryEntry,
  type PatchRelease,
} from "./patch-history"
import { AppLink } from "./routing"
import type { AskResponse } from "./types"

interface PublicAuthActions {
  authenticated?: boolean
  onSignIn?: () => void
  signingIn?: boolean
  signInError?: boolean
  onPublicAsk?: (question: string) => Promise<AskResponse>
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
          <small>Public development preview</small>
        </span>
      </AppLink>
      <nav aria-label="Public">
        <AppLink to="/about">About</AppLink>
        <AppLink to="/patch-history">Patch history</AppLink>
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
        <p>Unofficial development preview for English-language rules questions.</p>
      </div>
      <nav aria-label="Footer">
        <AppLink to="/about">About</AppLink>
        <AppLink to="/patch-history">Patch history</AppLink>
        <AppLink to="/terms">Terms of Service</AppLink>
        <AppLink to="/privacy">Privacy Policy</AppLink>
        <a href="mailto:paoloinigo30@gmail.com">Support</a>
      </nav>
      <p className="attribution-copy">
        MTG Rules Desk is unofficial Fan Content permitted under the Fan Content Policy. Not
        approved or endorsed by Wizards of the Coast. Portions of the materials used are property
        of Wizards of the Coast LLC. Card data and rulings are provided through Scryfall; Scryfall
        does not endorse this app.
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

function publicCitationUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    if (
      parsed.protocol === "https:" &&
      ["magic.wizards.com", "scryfall.com"].includes(parsed.hostname)
    ) {
      return parsed.toString()
    }
  } catch {
    return undefined
  }
  return undefined
}

function PublicAskPanel({ onAsk }: { onAsk?: PublicAuthActions["onPublicAsk"] }) {
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState<AskResponse>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)

  if (!onAsk) return null

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const text = question.trim()
    if (!text || pending) return
    setPending(true)
    setError(false)
    try {
      setAnswer(await onAsk(text))
      setQuestion("")
    } catch {
      setError(true)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="public-ask-panel" aria-labelledby="public-ask-heading">
      <div>
        <span className="eyebrow">Open table</span>
        <h2 id="public-ask-heading">Try one rules question without an account.</h2>
        <p>
          Public questions are free and are not added to account history. Sign in only when you
          want saved conversations, feedback, and account controls.
        </p>
      </div>
      <form className="public-ask-form" onSubmit={submit}>
        <label htmlFor="public-rules-question">Your rules question</label>
        <textarea
          id="public-rules-question"
          maxLength={2000}
          rows={3}
          placeholder="Example: How does Blood Moon interact with Urza's Saga?"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <div className="public-ask-actions">
          <button className="primary-button" type="submit" disabled={pending || !question.trim()}>
            {pending ? "Checking the rules..." : "Ask for free"}
            <ArrowRight aria-hidden="true" size={17} />
          </button>
          <span>One question at a time · no email required</span>
        </div>
      </form>
      {error && (
        <p className="public-ask-error" role="alert">
          The public desk could not complete that question. Try again later or sign in to use your
          saved desk.
        </p>
      )}
      {answer && (
        <article className="public-ask-result" aria-live="polite">
          <span className="section-label">Desk answer</span>
          <p>{answer.answer}</p>
          {answer.citations.length > 0 && (
            <ul aria-label="Answer sources">
              {answer.citations.map((citation) => {
                const href = publicCitationUrl(citation.url)
                return (
                  <li key={`${citation.passage_id}-${citation.label}`}>
                    {href ? (
                      <a href={href} target="_blank" rel="noreferrer">
                        {citation.label}
                      </a>
                    ) : (
                      citation.label
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          <small>Public answers are informational and are not official tournament rulings.</small>
        </article>
      )}
    </section>
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

export function WelcomePage({ onSignIn, signingIn, signInError, onPublicAsk }: PublicAuthActions) {
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
              Public questions need an internet connection. Sign in when you want to save the
              conversation to your account.
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

        <PublicAskPanel onAsk={onPublicAsk} />
      </main>
    </PublicLayout>
  )
}

function patchDateLabel(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(`${date}T00:00:00Z`))
}

function groupPatchHistory(entries: readonly PatchHistoryEntry[]) {
  const groups = new Map<string, PatchHistoryEntry[]>()
  for (const entry of entries) {
    const group = groups.get(entry.date) ?? []
    group.push(entry)
    groups.set(entry.date, group)
  }
  return Array.from(groups, ([date, groupedEntries]) => ({ date, entries: groupedEntries }))
}

const PATCH_KIND_LABELS: Record<string, string> = {
  chore: "Maintenance",
  ci: "Build",
  docs: "Documentation",
  feat: "Feature",
  fix: "Fix",
  perf: "Performance",
  refactor: "Refactor",
  revert: "Revert",
  test: "Test",
}

function concisePatchMessage(subject: string): { kind: string; message: string } {
  const conventional = subject.match(/^([a-z]+)(?:\([^)]*\))?:\s*(.+)$/i)
  if (!conventional) {
    return { kind: "Merge", message: subject.replace(/\.$/, "") }
  }
  const kind = PATCH_KIND_LABELS[conventional[1].toLowerCase()] ?? conventional[1]
  const rawMessage = conventional[2].trim().replace(/\.$/, "")
  return {
    kind,
    message: rawMessage.charAt(0).toUpperCase() + rawMessage.slice(1),
  }
}

function patchDateLongLabel(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(`${date}T00:00:00Z`))
}

function patchKindSummary(entries: readonly PatchHistoryEntry[]): string {
  const counts = new Map<string, number>()
  for (const entry of entries) {
    const { kind } = concisePatchMessage(entry.subject)
    counts.set(kind, (counts.get(kind) ?? 0) + 1)
  }
  return Array.from(counts.entries())
    .sort(([leftKind, leftCount], [rightKind, rightCount]) => rightCount - leftCount || leftKind.localeCompare(rightKind))
    .map(([kind, count]) => `${count} ${kind}`)
    .join(" · ")
}

const PATCH_NOTES_PAGE_SIZE = 8

function entriesForPatchRelease(release: PatchRelease): readonly PatchHistoryEntry[] {
  const endIndex = PATCH_HISTORY.findIndex((entry) => entry.hash === release.endAt)
  if (endIndex < 0) return []

  const startIndex = release.startAfter
    ? PATCH_HISTORY.findIndex((entry) => entry.hash === release.startAfter)
    : -1
  if (release.startAfter && startIndex < 0) return []
  return PATCH_HISTORY.slice(startIndex + 1, endIndex + 1)
}

function PatchEntryItem({ entry }: { entry: PatchHistoryEntry }) {
  const patch = concisePatchMessage(entry.subject)
  return (
    <li className="patch-entry" key={entry.hash}>
      <code>{entry.hash}</code>
      <div>
        <span className="patch-entry-kind">{patch.kind}</span>
        <p className="patch-entry-subject">{patch.message}</p>
        <span className="patch-entry-author">{entry.author}</span>
      </div>
    </li>
  )
}

type PatchHistoryOrder = "oldest" | "newest"

export function PatchHistoryPage({
  authenticated = false,
  onSignIn,
  signingIn,
  signInError,
}: PublicAuthActions) {
  const [order, setOrder] = useState<PatchHistoryOrder>("oldest")
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(() => new Set())
  const [patchNotePages, setPatchNotePages] = useState<Record<string, number>>({})
  const groups = useMemo(() => {
    const grouped = groupPatchHistory(PATCH_HISTORY)
    return order === "newest" ? grouped.reverse() : grouped
  }, [order])
  const releaseGroups = useMemo(() => {
    const grouped = PATCH_RELEASES.map((release) => ({
      release,
      entries: entriesForPatchRelease(release),
    }))
    if (order === "newest") {
      return grouped.reverse().map(({ release, entries }) => ({
        release,
        entries: [...entries].reverse(),
      }))
    }
    return grouped
  }, [order])

  const toggleDate = (date: string) => {
    setCollapsedDates((current) => {
      const next = new Set(current)
      if (next.has(date)) next.delete(date)
      else next.add(date)
      return next
    })
  }

  const setPatchNotePage = (releaseId: string, page: number) => {
    setPatchNotePages((current) => ({ ...current, [releaseId]: page }))
  }

  return (
    <PublicLayout
      authenticated={authenticated}
      onSignIn={onSignIn}
      signingIn={signingIn}
      signInError={signInError}
    >
      <main className="public-page document-page patch-history-page">
        <div className="document-intro patch-history-intro">
          <span className="eyebrow">Change ledger</span>
          <h1>Every patch, with a paper trail.</h1>
          <p>
            A chronological record of the Rules Desk preview: product work, tests, refactors,
            documentation, and release checkpoints in the order they landed.
          </p>
        </div>

        <section className="patch-history-summary" aria-label="Patch history summary">
          <div>
            <strong>{PATCH_HISTORY_CAPTURE.commitCount} commits recorded</strong>
            <span>Complete snapshot</span>
          </div>
          <div>
            <strong>{PATCH_HISTORY_CAPTURE.firstDate}</strong>
            <span>First patch</span>
          </div>
          <div>
            <strong>{PATCH_HISTORY_CAPTURE.lastDate}</strong>
            <span>Latest release checkpoint</span>
          </div>
        </section>

        <section className="patch-release-notes" aria-labelledby="patch-notes-heading">
          <div className="patch-release-notes-intro">
            <div>
              <span className="section-label">Deployment releases</span>
              <h2 id="patch-notes-heading">Patch notes by version</h2>
              <p>
                Each hosted checkpoint gets its own concise notes. Git hashes link back to the
                exact evidence commit; the current local preview is marked separately.
              </p>
            </div>
            <span className="patch-release-order">
              Releases: {order === "oldest" ? "Oldest first" : "Newest first"}
            </span>
          </div>

          <div className="patch-release-list">
            {releaseGroups.map(({ release, entries }) => {
              const pageCount = Math.max(1, Math.ceil(entries.length / PATCH_NOTES_PAGE_SIZE))
              const page = Math.min(patchNotePages[release.id] ?? 1, pageCount)
              const pageStart = (page - 1) * PATCH_NOTES_PAGE_SIZE
              const pageEntries = entries.slice(pageStart, pageStart + PATCH_NOTES_PAGE_SIZE)
              const releaseHeadingId = `patch-release-heading-${release.id}`
              const notesListId = `patch-notes-${release.id}`
              const checkpointHref = `${PATCH_HISTORY_CAPTURE.repository}/commit/${release.checkpoint}`

              return (
                <article
                  className="patch-release-card"
                  data-release-version={release.version}
                  key={release.id}
                >
                  <header className="patch-release-card-header">
                    <div className="patch-release-card-title">
                      <span className="patch-release-version">{release.version}</span>
                      <h3 id={releaseHeadingId}>{release.name}</h3>
                      <p>{release.summary}</p>
                    </div>
                    <dl className="patch-release-meta">
                      <div>
                        <dt>Status</dt>
                        <dd
                          className={`patch-release-status${release.status === "deployed" ? " is-deployed" : ""}`}
                        >
                          {release.status === "deployed" ? "Deployed" : "Local preview"}
                        </dd>
                      </div>
                      <div>
                        <dt>Environment</dt>
                        <dd>{release.environment}</dd>
                      </div>
                      <div>
                        <dt>Release date</dt>
                        <dd>{release.deployedAt ? `Deployed ${release.deployedAt}` : "Not deployed"}</dd>
                      </div>
                      <div>
                        <dt>Git proof</dt>
                        <dd>
                          <a
                            className="patch-release-checkpoint"
                            href={checkpointHref}
                            rel="noreferrer"
                            target="_blank"
                            aria-label={`${release.version} checkpoint ${release.checkpoint}`}
                          >
                            <code>{release.checkpoint}</code>
                            <ExternalLink aria-hidden="true" size={13} />
                          </a>
                        </dd>
                      </div>
                    </dl>
                  </header>

                  <section className="patch-notes-panel" aria-labelledby={releaseHeadingId}>
                    <div className="patch-notes-heading">
                      <div>
                        <span className="section-label">Patch notes</span>
                        <span>{entries.length} changes</span>
                      </div>
                      <span>
                        Page {page} of {pageCount}
                      </span>
                    </div>
                    <ol
                      className="patch-list patch-notes-list"
                      id={notesListId}
                      aria-label={`${release.version} patch notes`}
                    >
                      {pageEntries.map((entry) => (
                        <PatchEntryItem entry={entry} key={entry.hash} />
                      ))}
                    </ol>
                    <nav
                      className="patch-notes-pagination"
                      aria-label={`${release.version} patch notes pagination`}
                    >
                      <button
                        className="patch-notes-nav"
                        type="button"
                        disabled={page === 1}
                        aria-label={`Previous ${release.version} patch notes page`}
                        onClick={() => setPatchNotePage(release.id, page - 1)}
                      >
                        <ChevronLeft aria-hidden="true" size={14} />
                        Previous
                      </button>
                      <div className="patch-notes-pages">
                        {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
                          <button
                            className="patch-notes-page"
                            type="button"
                            key={pageNumber}
                            aria-current={pageNumber === page ? "page" : undefined}
                            aria-label={`Go to ${release.version} patch notes page ${pageNumber}`}
                            onClick={() => setPatchNotePage(release.id, pageNumber)}
                          >
                            {pageNumber}
                          </button>
                        ))}
                      </div>
                      <button
                        className="patch-notes-nav"
                        type="button"
                        disabled={page === pageCount}
                        aria-label={`Next ${release.version} patch notes page`}
                        onClick={() => setPatchNotePage(release.id, page + 1)}
                      >
                        Next
                        <ChevronRight aria-hidden="true" size={14} />
                      </button>
                    </nav>
                  </section>
                </article>
              )
            })}
          </div>
        </section>

        <div className="patch-history-layout">
          <aside className="patch-history-index" aria-label="Patch history capture details">
            <span className="section-label">Snapshot details</span>
            <dl>
              <div>
                <dt>Branch</dt>
                <dd>
                  <code>{PATCH_HISTORY_CAPTURE.branch}</code>
                </dd>
              </div>
              <div>
                <dt>Captured at</dt>
                <dd>
                  <code>{PATCH_HISTORY_CAPTURE.head}</code>
                </dd>
              </div>
            </dl>
            <p>
              The ledger is intentionally inclusive: test and documentation patches stay beside
              feature work so each release decision has context.
            </p>
          </aside>

          <div className="patch-history-ledger">
            <div className="patch-history-ledger-heading">
              <div className="patch-history-ledger-title">
                <span className="section-label">Chronological ledger</span>
                <span>{order === "oldest" ? "Oldest first" : "Newest first"}</span>
              </div>
              <label className="patch-order-filter">
                <span>Order</span>
                <select
                  aria-label="Patch history order"
                  value={order}
                  onChange={(event) => setOrder(event.target.value as PatchHistoryOrder)}
                >
                  <option value="oldest">Oldest first</option>
                  <option value="newest">Newest first</option>
                </select>
              </label>
            </div>
            {groups.map(({ date, entries }) => {
              const label = patchDateLabel(date)
              const longLabel = patchDateLongLabel(date)
              const collapsed = collapsedDates.has(date)
              const listId = `patch-list-${date}`
              return (
                <section
                  className={`patch-day${collapsed ? " is-collapsed" : ""}`}
                  key={date}
                  aria-labelledby={`patch-day-${date}`}
                >
                  <div className="patch-day-rail">
                    <div className="patch-day-heading">
                      <h2 id={`patch-day-${date}`}>{label}</h2>
                      <span>
                        {entries.length} {entries.length === 1 ? "patch" : "patches"}
                      </span>
                    </div>
                    <p className="patch-day-info">{patchKindSummary(entries)}</p>
                    <button
                      className="patch-day-toggle"
                      type="button"
                      aria-controls={listId}
                      aria-expanded={!collapsed}
                      aria-label={`${collapsed ? "Expand" : "Collapse"} ${longLabel} patches`}
                      onClick={() => toggleDate(date)}
                    >
                      <ChevronDown aria-hidden="true" size={15} />
                      {collapsed ? "Expand" : "Collapse"}
                    </button>
                  </div>
                  <ol
                    className="patch-list"
                    id={listId}
                    aria-label={`${longLabel} patches`}
                    hidden={collapsed}
                  >
                    {entries.map((entry) => {
                      const patch = concisePatchMessage(entry.subject)
                      return (
                        <li className="patch-entry" key={entry.hash}>
                          <code>{entry.hash}</code>
                          <div>
                            <span className="patch-entry-kind">{patch.kind}</span>
                            <p className="patch-entry-subject">{patch.message}</p>
                            <span className="patch-entry-author">{entry.author}</span>
                          </div>
                        </li>
                      )
                    })}
                  </ol>
                </section>
              )
            })}
          </div>
        </div>
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
            ruling data provided through Scryfall. MTG Rules Desk is unofficial Fan Content
            permitted under the Fan Content Policy. It is not approved or endorsed by Wizards of
            the Coast, and Scryfall does not endorse this app. Magic: The Gathering and related
            marks are property of Wizards of the Coast LLC.
          </p>
          <p>
            Read the{" "}
            <a href="https://company.wizards.com/en/legal/fancontentpolicy">
              Wizards Fan Content Policy
            </a>
            , the{" "}
            <a href="https://magic.wizards.com/en/rules">official Comprehensive Rules</a>, and{" "}
            <a href="https://scryfall.com/docs/api">Scryfall API documentation</a> for source
            and usage context.
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

        <section className="about-section about-support">
          <span className="section-label">Support and corrections</span>
          <h2>Find a source problem? Tell us.</h2>
          <p>
            Email{" "}
            <a href="mailto:paoloinigo30@gmail.com">paoloinigo30@gmail.com</a> for privacy
            requests, account deletion help, accessibility issues, source corrections, or
            copyright and attribution concerns. Please do not include passwords, tokens, or
            sensitive personal information in a support message.
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
  {
    id: "service",
    title: "1. The service",
    paragraphs: [
      "MTG Rules Desk is an English-language, unofficial reference that helps players research Magic: The Gathering rules questions. It retrieves public rules, Oracle card information, and dated rulings, then presents an AI-generated explanation with citations.",
      "This is a public development preview, not a production-ready service. Availability, correctness, and continued access are not guaranteed, and no service-level commitment is offered.",
      "The service is informational only. It is not Wizards of the Coast customer support, an official judge, a tournament ruling, a rules replacement, or a promise that a game, event, or card interaction will be decided a particular way.",
      "You may submit one or more free public questions without creating an account. Public answers are ephemeral and are not added to account history. A Google account is optional and is used for saved conversations, feedback, quotas, and account controls.",
    ],
  },
  {
    id: "accounts",
    title: "2. Accounts and eligibility",
    paragraphs: [
      "You may use the public question path without email registration. To save history or use account features, you must sign in through Google and provide information that is accurate for that sign-in provider.",
      "You are responsible for activity under your account and for keeping access to your Google account secure. Do not use another person's account or try to bypass authentication, quotas, or safety controls. If local law requires consent or supervision for your use of an online service, you must obtain it.",
    ],
  },
  {
    id: "use",
    title: "3. Acceptable use",
    paragraphs: [
      "Use MTG Rules Desk for lawful rules research and good-faith play discussions. Do not use it to overload, scrape, probe, reverse engineer, or interfere with the service; evade rate limits; submit malware or automated attack traffic; impersonate Wizards of the Coast, Scryfall, the operator, or a judge; or attempt to access another user's data.",
      "Do not submit passwords, API keys, payment details, government identifiers, health information, or other sensitive personal information. Do not submit content that infringes another person's rights or that you are not permitted to share.",
    ],
  },
  {
    id: "sources",
    title: "4. Sources and attribution",
    paragraphs: [
      "The service is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It is not approved, sponsored, or endorsed by Wizards of the Coast. Magic: The Gathering and related marks belong to Wizards of the Coast LLC.",
      "MTG Rules Desk is unofficial Fan Content permitted under the Fan Content Policy. Not approved or endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast LLC. © Wizards of the Coast LLC.",
      <>
        Card data and rulings are provided through{" "}
        <a href="https://scryfall.com/">Scryfall</a>. Scryfall does not endorse MTG Rules Desk.
        The service links to source material and adds its own explanatory answer; it is not a
        replacement for a source site or a re-packaged source database.
      </>,
    ],
  },
  {
    id: "answers",
    title: "5. AI-generated answers and limitations",
    paragraphs: [
      "Answers are generated from the active rules corpus and may be incomplete, stale, ambiguous, or wrong. Citations and confidence labels are safeguards, not guarantees. Check the linked source material and ask a qualified judge for a binding event ruling.",
      "The service does not provide legal, financial, medical, or professional advice. Do not rely on an answer as the sole basis for a consequential decision. The operator may correct, remove, or decline to answer a question without notice.",
    ],
  },
  {
    id: "content",
    title: "6. Your questions and service license",
    paragraphs: [
      "You keep your rights in questions, feedback, and other material you submit, subject to rights that already belong to someone else. You give the operator a limited, non-exclusive license to host, process, transmit, cache, display, and use that material only as reasonably necessary to provide, secure, troubleshoot, and improve the service.",
      "Do not submit unsolicited game designs, unpublished product ideas, or confidential material. Public questions that qualify for semantic caching may be retained without an account identifier for up to seven days, as described in the Privacy Policy.",
    ],
  },
  {
    id: "account-controls",
    title: "7. Deletion, suspension, and availability",
    paragraphs: [
      "You can delete saved conversations and request account deletion from the authenticated desk. Public questions do not create account history, but eligible shared-cache records expire separately. Sign-out ends a browser session; it does not by itself delete saved data.",
      "The operator may limit, suspend, or end access when necessary to protect users, source rights, service reliability, or security, including when these Terms are violated. The service may change or be unavailable, and no uptime or preservation guarantee is made.",
    ],
  },
  {
    id: "changes",
    title: "8. Changes and contact",
    paragraphs: [
      "These Terms describe the current operational product. The operator may update them when the product, providers, source policies, or legal requirements change. The date at the top of this page identifies the current revision; material changes may also be announced in the app.",
      <>
        Questions, privacy requests, source corrections, accessibility issues, and copyright or
        attribution concerns can be sent to{" "}
        <a href="mailto:paoloinigo30@gmail.com">paoloinigo30@gmail.com</a>. No paid plan or
        purchase flow is currently offered.
      </>,
    ],
  },
]

const PRIVACY_SECTIONS: LegalSection[] = [
  {
    id: "scope",
    title: "1. Scope and summary",
    paragraphs: [
      "This Privacy Policy explains how MTG Rules Desk processes information when you sign in, ask a rules question, save or delete a conversation, submit feedback, install the progressive web app, or contact support.",
      "You can ask a free public question without an account or email registration. Public questions are not added to account history, but the question and answer may be processed in a shared semantic cache for up to seven days when they meet the cache rules described below. Please do not include personal, confidential, or sensitive information in a rules question or feedback comment.",
      "MTG Rules Desk is an unofficial, English-language Magic: The Gathering rules reference. It is not affiliated with, approved by, or endorsed by Wizards of the Coast or Scryfall.",
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
      "A cache record is not linked to a user account. Public and authenticated questions can use the same cache, and the normalized question text is retained until the entry expires. Deleting an account does not immediately target that separate cache entry; it expires automatically within the cache period. Avoid placing identifying or sensitive details in questions.",
    ],
  },
  {
    id: "retention",
    title: "7. Retention and deletion",
    paragraphs: [
      "Saved conversations, messages, citations, feedback, account identifiers, and usage records remain in Cloud SQL while your account is active unless you delete a conversation or your account. Public questions are not written to account history; eligible public question material may remain in the shared semantic cache for up to seven days.",
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
    ? "Operational terms · Effective date: August 24, 2026 · Last updated: August 24, 2026"
    : "Effective date: August 24, 2026 · Last updated: August 24, 2026"

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
              ? "The operational terms are complete for the current product. The operator must still obtain qualified legal review and publish the approved version before public launch."
              : "This implementation-aligned policy is complete for the current product. The operator must still obtain qualified legal review and publish the approved version before public launch."}
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
              This operational version is not legal advice and does not claim approval by Wizards
              of the Coast, Scryfall, or qualified counsel. Contact the operator listed above with
              questions.
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
