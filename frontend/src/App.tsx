import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Archive,
  BookOpenText,
  Check,
  ChevronDown,
  Clipboard,
  Download,
  LogOut,
  Search,
  Settings,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  WifiOff,
  X,
} from "lucide-react"
import { type FormEvent, type RefObject, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"

import { BrandMark } from "./BrandMark"
import { InstallPromptBanner } from "./InstallPrompt"
import { AboutPage, LegalDocumentPage, WelcomePage } from "./PublicPages"
import { userMessageFor } from "./api-client"
import { applyRouteMetadata, getRouteMetadata } from "./route-meta"
import { AppLink, RouterProvider, useRouter } from "./routing"
import { useInstallPrompt } from "./useInstallPrompt"
import type {
  ApiPort,
  AskResponse,
  AuthPort,
  ConversationDetail,
  InstallPort,
  User,
} from "./types"

type Panel = "chat" | "history" | "settings"

const QUICK_QUERIES = [
  {
    label: "Blood Moon + Urza's Saga",
    question: "How does Blood Moon interact with Urza's Saga?",
  },
  {
    label: "Teferi's Protection on Stack",
    question: "What happens if Teferi's Protection is on the stack?",
  },
  {
    label: "Humility + Opalescence Layers",
    question: "How do Humility and Opalescence interact in the layer system?",
  },
  {
    label: "Replacement Effect Priority",
    question: "Who chooses the order when multiple replacement effects apply?",
  },
] as const

function useModalDrawer(
  onClose: () => void,
  returnFocusRef?: RefObject<HTMLButtonElement | null>,
) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : undefined
    const returnFocusElement = returnFocusRef?.current
    closeButtonRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current()
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      if (returnFocusElement?.isConnected) returnFocusElement.focus()
      else if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [returnFocusRef])

  return closeButtonRef
}

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
  error,
  onBack,
  onDelete,
  deleting,
}: {
  detail: ConversationDetail | undefined
  loading: boolean
  error: unknown
  onBack: () => void
  onDelete: () => void
  deleting: boolean
}) {
  if (error) {
    return (
      <div className="status-message error" role="alert">
        {userMessageFor(error)}
      </div>
    )
  }
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
      <button className="danger-button" disabled={deleting} onClick={onDelete}>
        <Trash2 aria-hidden="true" size={17} />
        Delete conversation
      </button>
    </div>
  )
}

function HistoryPanel({
  api,
  onClose,
  returnFocusRef,
}: {
  api: ApiPort
  onClose: () => void
  returnFocusRef: RefObject<HTMLButtonElement | null>
}) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string>()
  const closeButtonRef = useModalDrawer(onClose, returnFocusRef)
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
    <aside
      className="drawer history-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="history-heading"
    >
      <header>
        <div>
          <span className="eyebrow">Saved rulings</span>
          <h2 id="history-heading">History</h2>
        </div>
        <button
          ref={closeButtonRef}
          className="icon-button"
          onClick={onClose}
          aria-label="Close history"
        >
          <X aria-hidden="true" />
        </button>
      </header>
      {selectedId ? (
        <ConversationView
          detail={detail.data}
          loading={detail.isPending}
          error={detail.error}
          onBack={() => setSelectedId(undefined)}
          onDelete={remove}
          deleting={deletion.isPending}
        />
      ) : (
        <div className="history-list">
          {summaries.isError && (
            <div className="status-message error" role="alert">
              {userMessageFor(summaries.error)}
            </div>
          )}
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
      {deletion.isError && (
        <div className="status-message error" role="alert">
          {userMessageFor(deletion.error)}
        </div>
      )}
    </aside>
  )
}

function SettingsPanel({
  api,
  onSignOut,
  installReady,
  onInstall,
  onClose,
  returnFocusRef,
}: {
  api: ApiPort
  onSignOut: () => Promise<void>
  installReady: boolean
  onInstall: () => Promise<void>
  onClose: () => void
  returnFocusRef: RefObject<HTMLButtonElement | null>
}) {
  const [confirming, setConfirming] = useState(false)
  const [confirmation, setConfirmation] = useState("")
  const closeButtonRef = useModalDrawer(onClose, returnFocusRef)
  const deletion = useMutation({
    mutationFn: () => api.deleteAccount(),
    onSuccess: onSignOut,
  })

  return (
    <aside
      className="drawer settings-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-heading"
    >
      <header>
        <div>
          <span className="eyebrow">Account controls</span>
          <h2 id="settings-heading">Settings</h2>
        </div>
        <button
          ref={closeButtonRef}
          className="icon-button"
          onClick={onClose}
          aria-label="Close settings"
        >
          <X aria-hidden="true" />
        </button>
      </header>
      <section className="settings-section">
        <h3>Product and legal</h3>
        <nav className="settings-links" aria-label="Product and legal">
          <AppLink to="/about">About</AppLink>
          <AppLink to="/terms">Terms of Service</AppLink>
          <AppLink to="/privacy">Privacy Policy</AppLink>
        </nav>
        {installReady && (
          <button className="utility-button settings-install" onClick={onInstall}>
            <Download aria-hidden="true" size={16} />
            Install app
          </button>
        )}
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
        {deletion.isError && (
          <div className="status-message error" role="alert">
            {userMessageFor(deletion.error)}
          </div>
        )}
      </section>
    </aside>
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
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState<AskResponse>()
  const [feedbackRating, setFeedbackRating] = useState<1 | -1>()
  const [offlineMessage, setOfflineMessage] = useState("")
  const [conversationId, setConversationId] = useState<string>()
  const { dismissBanner, installApp, installReady, showBanner } = useInstallPrompt(install)
  const [signInStatus, setSignInStatus] = useState<"idle" | "pending" | "error">("idle")
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle")
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const hasFocusedCommand = useRef(false)
  const historyTriggerRef = useRef<HTMLButtonElement>(null)
  const settingsTriggerRef = useRef<HTMLButtonElement>(null)
  const intentionalSignOut = useRef(false)
  const panel: Panel =
    route === "/desk/history" ? "history" : route === "/desk/settings" ? "settings" : "chat"

  useEffect(
    () =>
      auth.subscribe((nextUser) => {
        setUser(nextUser)
        if (nextUser === null && intentionalSignOut.current) {
          intentionalSignOut.current = false
          navigate("/", { replace: true })
        }
      }),
    [auth, navigate],
  )
  useEffect(() => {
    if (user === null && route.startsWith("/desk")) {
      navigate("/", { replace: true })
    }
    if (user && route === "/" && !intentionalSignOut.current) {
      navigate("/desk", { replace: true })
    }
  }, [navigate, route, user])
  useEffect(() => {
    applyRouteMetadata(
      getRouteMetadata(route, {
        origin: import.meta.env.VITE_PUBLIC_SITE_URL || window.location.origin,
        allowIndexing: import.meta.env.VITE_ALLOW_INDEXING === "true",
      }),
    )
  }, [route])
  useEffect(() => {
    const markOnline = () => setIsOnline(true)
    const markOffline = () => setIsOnline(false)
    window.addEventListener("online", markOnline)
    window.addEventListener("offline", markOffline)
    return () => {
      window.removeEventListener("online", markOnline)
      window.removeEventListener("offline", markOffline)
    }
  }, [])

  useEffect(() => {
    if (!user || panel !== "chat") return
    if (!hasFocusedCommand.current) {
      inputRef.current?.focus()
      hasFocusedCommand.current = true
    }
    const focusCommand = (event: KeyboardEvent) => {
      const target = event.target
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      const usesCommandShortcut =
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k"
      if (usesCommandShortcut || (event.key === "/" && !isTyping)) {
        event.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener("keydown", focusCommand)
    return () => window.removeEventListener("keydown", focusCommand)
  }, [panel, user])

  const feedback = useMutation({
    mutationFn: ({ messageId, rating }: { messageId: string; rating: 1 | -1 }) =>
      api.feedback(messageId, rating),
    onSuccess: (_result, variables) => setFeedbackRating(variables.rating),
  })

  const ask = useMutation({
    mutationFn: ({ text, id }: { text: string; id?: string }) => api.ask(text, id),
    onSuccess: (result) => {
      setAnswer(result)
      setConversationId(result.conversation_id)
      setQuestion("")
      setFeedbackRating(undefined)
      setCopyStatus("idle")
      feedback.reset()
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

  const handleSignOut = async () => {
    intentionalSignOut.current = true
    try {
      await auth.signOut()
      navigate("/", { replace: true })
    } catch {
      intentionalSignOut.current = false
    }
  }

  const handleSignIn = async () => {
    if (signInStatus === "pending") return
    setSignInStatus("pending")
    try {
      await auth.signIn()
      setSignInStatus("idle")
    } catch {
      setSignInStatus("error")
    }
  }

  const handleInstall = async () => {
    await installApp()
  }

  const chooseQuickQuery = (text: string) => {
    setQuestion(text)
    inputRef.current?.focus()
  }

  const copyRuling = async () => {
    if (!answer) return
    const citations = answer.citations
      .map((citation) => `${citation.label}: ${citation.url}`)
      .join("\n")
    const copy = [answer.answer, citations && `Sources:\n${citations}`]
      .filter(Boolean)
      .join("\n\n")
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(copy)
      setCopyStatus("copied")
    } catch {
      setCopyStatus("error")
    }
  }

  const publicAuthActions = user
    ? {}
    : {
        onSignIn: () => void handleSignIn(),
        signingIn: signInStatus === "pending",
        signInError: signInStatus === "error",
      }

  if (user === undefined) {
    return <div className="loading-screen">Opening the rules desk…</div>
  }
  if (route === "/about") {
    return <AboutPage authenticated={Boolean(user)} {...publicAuthActions} />
  }
  if (route === "/terms") {
    return (
      <LegalDocumentPage authenticated={Boolean(user)} kind="terms" {...publicAuthActions} />
    )
  }
  if (route === "/privacy") {
    return (
      <LegalDocumentPage authenticated={Boolean(user)} kind="privacy" {...publicAuthActions} />
    )
  }
  if (user === null) return <WelcomePage {...publicAuthActions} />

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="wordmark">
          <BrandMark className="wordmark-mark" />
          <div className="wordmark-copy">
            <strong>MTG Rules Desk</strong>
            <span className="engine-version">v1.0 <b>RAG Engine</b></span>
          </div>
        </div>

        <div className="topbar-actions">
          <span className={"engine-status " + (isOnline ? "online" : "offline")}>
            <span className="status-dot" aria-hidden="true" />
            {isOnline ? "Retrieval online" : "Offline app shell"}
          </span>
          {installReady && (
            <button
              className="install-button header-install"
              onClick={() => void handleInstall()}
              aria-label="Install PWA"
            >
              <Download aria-hidden="true" size={16} />
              <span>Install PWA</span>
            </button>
          )}
          <nav className="topbar-nav" aria-label="Primary">
            <button
              ref={historyTriggerRef}
              className={panel === "history" ? "active" : ""}
              onClick={() => navigate("/desk/history")}
              aria-current={panel === "history" ? "page" : undefined}
              aria-label="History"
            >
              <Archive aria-hidden="true" />
              <span>History</span>
            </button>
            <button
              ref={settingsTriggerRef}
              className={panel === "settings" ? "active" : ""}
              onClick={() => navigate("/desk/settings")}
              aria-current={panel === "settings" ? "page" : undefined}
              aria-label="Settings"
            >
              <Settings aria-hidden="true" />
              <span>Settings</span>
            </button>
          </nav>
          <button
            className="icon-button sign-out-button"
            onClick={() => void handleSignOut()}
            aria-label="Sign out"
          >
            <LogOut aria-hidden="true" />
          </button>
        </div>
      </header>

      <main className="desk">
        <section className="command-hero" aria-labelledby="command-heading">
          <div className="command-intro">
            <span className="eyebrow">Official sources, one clear ruling</span>
            <h1 id="command-heading">Resolve the board state.</h1>
            <p>
              Describe the cards, zones, timing, and controllers. The desk retrieves the
              relevant rules before it answers.
            </p>
          </div>

          <form className="question-form" onSubmit={submit}>
            <div className="command-field">
              <Search aria-hidden="true" className="command-search-icon" />
              <label className="sr-only" htmlFor="rules-question">Rules question</label>
              <textarea
                id="rules-question"
                ref={inputRef}
                maxLength={2000}
                rows={2}
                placeholder="Ask a complex Magic rules question..."
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <div className="shortcut-hints" aria-hidden="true">
                <kbd>/</kbd>
                <span>or</span>
                <kbd>Ctrl K</kbd>
              </div>
            </div>
            <div className="form-footer">
              <span>{question.length} / 2,000</span>
              <button className="primary-button" disabled={ask.isPending}>
                {ask.isPending ? "Checking..." : "Ask"}
                <Sparkles aria-hidden="true" size={17} />
              </button>
            </div>
          </form>

          <div className="quick-queries" role="group" aria-label="Quick rules questions">
            {QUICK_QUERIES.map((query) => (
              <button
                key={query.label}
                type="button"
                onClick={() => chooseQuickQuery(query.question)}
              >
                {query.label}
              </button>
            ))}
          </div>
        </section>

        {offlineMessage && (
          <div className="status-message warning" role="alert">
            <WifiOff aria-hidden="true" />
            {offlineMessage}
          </div>
        )}
        {ask.isError && (
          <div className="status-message error" role="alert">
            {userMessageFor(
              ask.error,
              "The rules desk could not complete this answer. Try again.",
            )}
          </div>
        )}

        {ask.isPending && (
          <section
            className="loading-answer"
            role="status"
            aria-label="Checking official sources"
          >
            <div className="loading-topline">
              <span className="shimmer short" />
              <span className="shimmer tiny" />
            </div>
            <span className="shimmer wide" />
            <span className="shimmer medium" />
            <div className="loading-citations">
              <span className="shimmer citation" />
              <span className="shimmer citation" />
            </div>
          </section>
        )}

        {answer ? (
          <article className="answer-stack" aria-live="polite">
            <header className="answer-trust-zone">
              <div className="trust-indicators">
                <span className="grounded-label">
                  <Check aria-hidden="true" size={15} />
                  Grounded in retrieved rules sources
                </span>
                <span className={"confidence " + answer.confidence}>
                  {answer.confidence} confidence
                </span>
              </div>
              <div className="answer-utilities">
                <span className="quota">{answer.quota_remaining} answers left today</span>
                <button className="copy-button" onClick={() => void copyRuling()}>
                  <Clipboard aria-hidden="true" size={15} />
                  Copy ruling
                </button>
              </div>
              {copyStatus === "copied" && (
                <span className="copy-status" role="status">Ruling copied</span>
              )}
              {copyStatus === "error" && (
                <span className="copy-status error" role="alert">
                  Copy failed. Select the answer text instead.
                </span>
              )}
            </header>

            <section className="ruling answer-summary-zone">
              <span className="section-label">Plain-English ruling</span>
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

            <section className="evidence-zone" aria-label="Citational evidence">
              <SourceList answer={answer} />
              <details className="citation-tree">
                <summary>
                  <ChevronDown aria-hidden="true" size={16} />
                  Expand full citation tree
                </summary>
                <ol>
                  {answer.citations.map((citation) => (
                    <li key={citation.passage_id}>
                      <code>{citation.passage_id}</code>
                      <span>{citation.claim}</span>
                    </li>
                  ))}
                </ol>
              </details>
            </section>

            <div className="answer-actions">
              <span>Was this useful?</span>
              <button
                className="icon-button"
                aria-label="Helpful answer"
                aria-pressed={feedbackRating === 1}
                disabled={feedback.isPending}
                onClick={() =>
                  feedback.mutate({ messageId: answer.message_id, rating: 1 })
                }
              >
                <ThumbsUp aria-hidden="true" />
              </button>
              <button
                className="icon-button"
                aria-label="Unhelpful answer"
                aria-pressed={feedbackRating === -1}
                disabled={feedback.isPending}
                onClick={() =>
                  feedback.mutate({ messageId: answer.message_id, rating: -1 })
                }
              >
                <ThumbsDown aria-hidden="true" />
              </button>
              {feedback.isSuccess && <span className="feedback-status">Feedback saved</span>}
              {feedback.isError && (
                <span className="feedback-status error" role="alert">
                  Feedback could not be saved. Try again.
                </span>
              )}
            </div>
          </article>
        ) : (
          !ask.isPending && (
            <section className="ready-state" aria-label="Rules desk ready">
              <div className="ready-orbit" aria-hidden="true">
                <span>CR</span>
              </div>
              <div>
                <span className="section-label">Ready for a board state</span>
                <p>
                  Start with a quick query or describe the exact sequence at your table.
                </p>
              </div>
            </section>
          )
        )}
      </main>

      {showBanner && (
        <InstallPromptBanner
          onDismiss={dismissBanner}
          onInstall={() => void handleInstall()}
        />
      )}

      {panel === "history" && (
        <HistoryPanel
          api={api}
          returnFocusRef={historyTriggerRef}
          onClose={() => navigate("/desk")}
        />
      )}
      {panel === "settings" && (
        <SettingsPanel
          api={api}
          onSignOut={handleSignOut}
          installReady={installReady}
          returnFocusRef={settingsTriggerRef}
          onInstall={handleInstall}
          onClose={() => navigate("/desk")}
        />
      )}
    </div>
  )
}
