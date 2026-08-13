import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import { ApiClientError } from "./api-client"
import "./index.css"
import type {
  ApiPort,
  AskResponse,
  AuthPort,
  ConversationDetail,
  ConversationSummary,
  InstallPort,
  User,
} from "./types"

if (!import.meta.env.DEV) {
  throw new Error("The E2E harness is available only in the Vite development server")
}

const requestedRoute = new URLSearchParams(window.location.search).get("route")
const requestedFailure = new URLSearchParams(window.location.search).get("failure")
if (requestedRoute?.startsWith("/")) {
  window.history.replaceState({}, "", requestedRoute)
}

const answer: AskResponse = {
  conversation_id: "conversation-1",
  message_id: "message-2",
  answer: "Flying creatures can only be blocked by creatures with flying or reach.",
  citations: [
    {
      passage_id: "rule-702.9",
      claim: "Flying restricts blockers.",
      label: "Comprehensive Rules 702.9",
      url: "https://magic.wizards.com/en/rules#702.9",
    },
  ],
  assumptions: ["The creature is on the battlefield."],
  confidence: "high",
  needs_clarification: false,
  quota_remaining: 19,
  cache_status: "miss",
}

let currentUser: User | null = null
let authListener: ((user: User | null) => void) | undefined
const auth: AuthPort = {
  subscribe(listener) {
    authListener = listener
    listener(currentUser)
    return () => {
      authListener = undefined
    }
  },
  async signIn() {
    currentUser = { uid: "e2e-user", email: "judge@example.com" }
    authListener?.(currentUser)
  },
  async signOut() {
    currentUser = null
    authListener?.(null)
  },
  async token() {
    return "e2e-token"
  },
}

let summaries: ConversationSummary[] = [
  {
    id: "conversation-1",
    title: "Flying blockers",
    updated_at: "2026-08-12T00:00:00Z",
  },
]
const conversation: ConversationDetail = {
  id: "conversation-1",
  title: "Flying blockers",
  messages: [
    {
      id: "message-1",
      role: "user",
      content: "What blocks flying?",
      created_at: "2026-08-12T00:00:00Z",
      citations: [],
    },
    {
      id: "message-2",
      role: "assistant",
      content: answer.answer,
      created_at: "2026-08-12T00:00:01Z",
      citations: answer.citations,
    },
  ],
}

const api: ApiPort = {
  async ask(question) {
    if (requestedFailure === "auth") throw new ApiClientError("AUTH_SESSION")
    if (question.toLowerCase() === "quota") throw new Error("daily answer limit reached")
    return answer
  },
  async conversations() {
    if (requestedFailure === "network") throw new ApiClientError("NETWORK")
    return summaries
  },
  async conversation() {
    return conversation
  },
  async deleteConversation() {
    summaries = []
  },
  async feedback() {},
  async deleteAccount() {},
}

const install: InstallPort = {
  available: true,
  async install() {
    return true
  },
}
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App auth={auth} api={api} install={install} />
    </QueryClientProvider>
  </StrictMode>,
)
