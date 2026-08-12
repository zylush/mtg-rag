import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Archive,
  BookOpenText,
  Check,
  Download,
  LogOut,
  Menu,
  MessageSquareQuote,
  Settings,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  WifiOff,
  X,
} from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"

import { AboutPage, LegalDocumentPage, WelcomePage } from "./PublicPages"
import { AppLink, RouterProvider, useRouter } from "./routing"
import type {
  ApiPort,
  AskResponse,
  AuthPort,
  ConversationDetail,
  InstallPort,
  User,
} from "./types"

type Panel = "chat" | "history" | "settings"

function safeCitationUrl(url: string): string | undefined {
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

function MarkdownAnswer({ answer }: { answer: string }) {
  return (
    <ReactMarkdown
      rehypePlugins={[rehypeSanitize]}
      skipHtml
      allowedElements={[
        "p",
        "strong",
        "em",
        "ul",
        "ol",
        "li",
        "blockquote",
        "code",
        "pre",
      ]}
      unwrapDisallowed
    >
      {answer}
    </ReactMarkdown>
  )
}

function SourceList({ answer }: { answer: AskResponse }) {
  if (!answer.citations.length) return null
  return (
    <section className="sources" aria-labelledby="sources-heading">
      <div className="section-label" id="sources-heading">
        <BookOpenText aria-hidden="true" size={15} />
        Sources checked
      </div>
      <ol>
        {answer.citations.map((citation) => {
          const href = safeCitationUrl(citation.url)
          return (
            <li key={citation.passage_id}>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer">
                  {citation.label}
                </a>
              ) : (
                <span>{citation.label}</span>
              )}
              <p>{citation.claim}</p>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function ConversationView({
  detail,
  loading,
  onBack,
  onDelete,
}: {
  detail: ConversationDetail | undefined
  loading: boolean
  onBack: () => void
  onDelete: () => void
}) {
  if (loading || !detail) return <p className="quiet">Loading conversation…</p>
  return (
    <div className="conversation-view">
      <button className="text-button" onClick={onBack}>
        Back to history
      </button>
      <h3>{detail.title}</h3>
      <div className="saved-messages">
        {detail.messages.map((message) => (
          <article key={message.id} className={"saved-message " + message.role}>
            <span>{message.role === "user" ? "Question" : "Answer"}</span>
            <p>{message.content}</p>
          </article>
        ))}
      </div>
      <button className="danger-button" onClick={onDelete}>
        <Trash2 aria-hidden="true" size={17} />
        Delete conversation
      </button>
    </div>
  )
}

function HistoryPanel({ api, onClose }: { api: ApiPort; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string>()
  const summaries = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.conversations(),
  })
  const detail = useQuery({
    queryKey: ["conversation", selectedId],
    queryFn: () => api.conversation(selectedId!),
    enabled: Boolean(selectedId),
  })
  const deletion = useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: async () => {
      setSelectedId(undefined)
      await queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const remove = () => {
    if (selectedId && window.confirm("Permanently delete this conversation?")) {
      deletion.mutate(selectedId)
    }
  }

  return (
    <aside className="drawer history-drawer" aria-labelledby="history-heading">
      <header>
        <div>
          <span className="eyebrow">Saved rulings</span>
          <h2 id="history-heading">History</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close history">
          <X aria-hidden="true" />
        </button>
      </header>
      {selectedId ? (
        <ConversationView
          detail={detail.data}
          loading={detail.isPending}
          onBack={() => setSelectedId(undefined)}
          onDelete={remove}
        />
      ) : (
        <div className="history-list">
          {summaries.isPending && <p className="quiet">Loading history…</p>}
          {!summaries.isPending && summaries.data?.length === 0 && (
            <div className="empty-state">
              <Archive aria-hidden="true" />
              <p>Your answered questions will appear here.</p>
            </div>
          )}
          {summaries.data?.map((conversation) => (
            <button
              className="history-item"
              key={conversation.id}
              onClick={() => setSelectedId(conversation.id)}
            >
              <span>{conversation.title}</span>
              <time dateTime={conversation.updated_at}>
                {new Intl.DateTimeFormat("en", {
                  month: "short",
                  day: "numeric",
                }).format(new Date(conversation.updated_at))}
              </time>
            </button>
          ))}
        </div>
      )}
    </aside>
  )
}

function SettingsPanel({
  api,
  auth,
  onClose,
}: {
  api: ApiPort
  auth: AuthPort
  onClose: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [confirmation, setConfirmation] = useState("")
  const deletion = useMutation({
    mutationFn: () => api.deleteAccount(),
    onSuccess: () => auth.signOut(),
  })

  return (
    <aside className="drawer settings-drawer" aria-labelledby="settings-heading">
      <header>
        <div>
          <span className="eyebrow">Account controls</span>
          <h2 id="settings-heading">Settings</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close settings">
          <X aria-hidden="true" />
        </button>
      </header>
      <section className="settings-section">
        <h3>Language</h3>
        <p>English</p>
        <span>The v1 rules corpus and answers are English-only.</span>
      </section>
      <section className="settings-section">
        <h3>Offline use</h3>
        <p>Static app shell only</p>
        <span>Rules answers always require a live connection.</span>
      </section>
      <section className="settings-section">
        <h3>Sources and attribution</h3>
        <p>WotC rules + Scryfall data</p>
        <span>
          MTG Rules Desk is unofficial fan content. Wizards of the Coast neither
          approves nor endorses it. Card data and rulings are provided by Scryfall;
          Scryfall does not endorse this app.
        </span>
      </section>
      <section className="danger-zone">
        <h3>Delete account</h3>
        <p>
          This permanently deletes your conversations, feedback, usage data, and sign-in
          account.
        </p>
        {!confirming ? (
          <button className="danger-button" onClick={() => setConfirming(true)}>
            Delete account
          </button>
        ) : (
          <div className="confirmation">
            <label htmlFor="delete-confirmation">Type DELETE to confirm</label>
            <input
              id="delete-confirmation"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
            />
            <button
              className="danger-button"
              disabled={confirmation !== "DELETE" || deletion.isPending}
              onClick={() => deletion.mutate()}
            >
              Permanently delete account
            </button>
          </div>
        )}
      </section>
    </aside>
  )
}

function Login({ auth }: { auth: AuthPort }) {
  const signIn = useMutation({ mutationFn: () => auth.signIn() })
  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="wordmark-mark" aria-hidden="true">
          R
        </div>
        <span className="eyebrow">MTG Rules Desk</span>
        <h1>Settle the rules question. Keep the game moving.</h1>
        <p>
          Ask against the Comprehensive Rules, current Oracle text, and attributed card
          rulings. Every material claim comes with a source.
        </p>
        <button className="primary-button" onClick={() => signIn.mutate()}>
          <ShieldCheck aria-hidden="true" />
          Sign in with Google
        </button>
        {signIn.isError && (
          <div className="status-message error" role="alert">
            Sign-in did not complete. Check popup permissions and try again.
          </div>
        )}
        <small>Available in Taiwan, Japan, South Korea, and Singapore.</small>
        <div className="login-links" aria-label="Legal links">
          <span>By continuing, you acknowledge the</span>
          <AppLink to="/terms">Terms of Service</AppLink>
          <span>and</span>
          <AppLink to="/privacy">Privacy Policy</AppLink>
          <span>.</span>
        </div>
        <small className="legal-notice">
          MTG Rules Desk is unofficial fan content. Wizards of the Coast neither
          approves nor endorses it. Card data and rulings are provided by Scryfall;
          Scryfall does not endorse this app.
        </small>
      </section>
    </main>
  )
}

type AppProps = {
  auth: AuthPort
  api: ApiPort
  install: InstallPort
}

export function App(props: AppProps) {
  return (
    <RouterProvider>
      <AppContent {...props} />
    </RouterProvider>
  )
}

function AppContent({ auth, api, install }: AppProps) {
  const { route, navigate } = useRouter()
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [panel, setPanel] = useState<Panel>("chat")
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState<AskResponse>()
  const [offlineMessage, setOfflineMessage] = useState("")
  const [conversationId, setConversationId] = useState<string>()
  const [installReady, setInstallReady] = useState(install.available)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => auth.subscribe(setUser), [auth])
  useEffect(() => {
    if (user === null && route === "/desk") navigate("/login")
    if (user && (route === "/" || route === "/login")) navigate("/desk")
  }, [navigate, route, user])
  useEffect(() => {
    const ready = () => setInstallReady(true)
    window.addEventListener("mtg-install-ready", ready)
    return () => window.removeEventListener("mtg-install-ready", ready)
  }, [])

  const ask = useMutation({
    mutationFn: ({ text, id }: { text: string; id?: string }) => api.ask(text, id),
    onSuccess: (result) => {
      setAnswer(result)
      setConversationId(result.conversation_id)
      setQuestion("")
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const text = question.trim()
    if (!text || ask.isPending) return
    if (!navigator.onLine) {
      setOfflineMessage("Answers require an internet connection.")
      return
    }
    setOfflineMessage("")
    ask.mutate({ text, id: conversationId })
  }

  if (user === undefined) {
    return <div className="loading-screen">Opening the rules desk…</div>
  }
  if (route === "/about") return <AboutPage />
  if (route === "/terms") return <LegalDocumentPage kind="terms" />
  if (route === "/privacy") return <LegalDocumentPage kind="privacy" />
  if (route === "/login") return <Login auth={auth} />
  if (route === "/" && user === null) return <WelcomePage />
  if (user === null) return <Login auth={auth} />

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="mobile-menu icon-button"
          aria-label="Open navigation"
          onClick={() => setPanel(panel === "chat" ? "history" : "chat")}
        >
          <Menu aria-hidden="true" />
        </button>
        <div className="wordmark">
          <span className="wordmark-mark" aria-hidden="true">
            R
          </span>
          <div>
            <strong>MTG Rules Desk</strong>
            <span>Grounded rules reference</span>
          </div>
        </div>
        <div className="topbar-actions">
          <nav className="topbar-links" aria-label="Desk links">
            <AppLink to="/about">About</AppLink>
            <AppLink to="/terms">Legal</AppLink>
          </nav>
          {installReady && (
            <button
              className="utility-button"
              onClick={async () => {
                await install.install()
                setInstallReady(false)
              }}
            >
              <Download aria-hidden="true" size={16} />
              Install app
            </button>
          )}
          <button className="icon-button" onClick={() => auth.signOut()} aria-label="Sign out">
            <LogOut aria-hidden="true" />
          </button>
        </div>
      </header>

      <nav className="side-nav" aria-label="Primary">
        <button
          className={panel === "chat" ? "active" : ""}
          onClick={() => setPanel("chat")}
          aria-label="Ask a rules question"
        >
          <MessageSquareQuote aria-hidden="true" />
          Ask
        </button>
        <button
          className={panel === "history" ? "active" : ""}
          onClick={() => setPanel("history")}
        >
          <Archive aria-hidden="true" />
          History
        </button>
        <button
          className={panel === "settings" ? "active" : ""}
          onClick={() => setPanel("settings")}
        >
          <Settings aria-hidden="true" />
          Settings
        </button>
      </nav>

      <main className="desk">
        <section className="desk-heading">
          <span className="eyebrow">Rules inquiry</span>
          <h1>What happened at the table?</h1>
          <p>
            Include card names, zones, timing, controllers, and the action that caused the
            question.
          </p>
        </section>

        <form className="question-form" onSubmit={submit}>
          <label htmlFor="rules-question">Rules question</label>
          <textarea
            id="rules-question"
            ref={inputRef}
            maxLength={2000}
            rows={4}
            placeholder="Example: If I cast Lightning Bolt and its target becomes illegal, does the whole spell fail?"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <div className="form-footer">
            <span>{question.length} / 2,000</span>
            <button className="primary-button" disabled={ask.isPending}>
              {ask.isPending ? "Checking sources…" : "Ask"}
              <Sparkles aria-hidden="true" size={17} />
            </button>
          </div>
        </form>

        {offlineMessage && (
          <div className="status-message warning" role="alert">
            <WifiOff aria-hidden="true" />
            {offlineMessage}
          </div>
        )}
        {ask.isError && (
          <div className="status-message error" role="alert">
            The rules desk could not complete this answer. Try again.
          </div>
        )}

        {answer ? (
          <article className="answer-stack" aria-live="polite">
            <div className="stack-rail" aria-hidden="true">
              <span>Q</span>
              <span>A</span>
              <span>S</span>
            </div>
            <div className="answer-content">
              <div className="answer-meta">
                <span className={"confidence " + answer.confidence}>
                  <Check aria-hidden="true" size={14} />
                  {answer.confidence} confidence
                </span>
                <span>{answer.quota_remaining} answers left today</span>
              </div>
              <section className="ruling">
                <span className="section-label">Ruling</span>
                <MarkdownAnswer answer={answer.answer} />
              </section>
              {answer.assumptions.length > 0 && (
                <section className="assumptions">
                  <span className="section-label">Assumptions</span>
                  <ul>
                    {answer.assumptions.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}
              <SourceList answer={answer} />
              <div className="answer-actions">
                <span>Was this useful?</span>
                <button
                  className="icon-button"
                  aria-label="Helpful answer"
                  onClick={() => api.feedback(answer.message_id, 1)}
                >
                  <ThumbsUp aria-hidden="true" />
                </button>
                <button
                  className="icon-button"
                  aria-label="Unhelpful answer"
                  onClick={() => api.feedback(answer.message_id, -1)}
                >
                  <ThumbsDown aria-hidden="true" />
                </button>
              </div>
            </div>
          </article>
        ) : (
          <section className="empty-desk">
            <div className="empty-rule">704.5</div>
            <h2>State the game state precisely.</h2>
            <p>The desk will retrieve exact card text and rules before drafting an answer.</p>
          </section>
        )}
      </main>

      {panel === "history" && <HistoryPanel api={api} onClose={() => setPanel("chat")} />}
      {panel === "settings" && (
        <SettingsPanel api={api} auth={auth} onClose={() => setPanel("chat")} />
      )}
    </div>
  )
}
