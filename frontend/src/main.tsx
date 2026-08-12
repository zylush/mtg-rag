import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { initializeApp } from "firebase/app"
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
} from "firebase/auth"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { registerSW } from "virtual:pwa-register"

import { App } from "./App"
import type { ApiPort, AuthPort, InstallPort } from "./types"
import "./index.css"

const firebaseApp = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
})
const firebaseAuth = getAuth(firebaseApp)
const googleProvider = new GoogleAuthProvider()
googleProvider.setCustomParameters({ prompt: "select_account" })

const auth: AuthPort = {
  subscribe(listener) {
    return onAuthStateChanged(firebaseAuth, (user) => {
      listener(user ? { uid: user.uid, email: user.email } : null)
    })
  },
  async signIn() {
    await signInWithPopup(firebaseAuth, googleProvider)
  },
  async signOut() {
    await signOut(firebaseAuth)
  },
  async token() {
    const user = firebaseAuth.currentUser
    if (!user) throw new Error("Authentication is required")
    return user.getIdToken()
  },
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "")
if (!apiBaseUrl) throw new Error("VITE_API_BASE_URL is required")

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await auth.token()
  const headers = new Headers(init.headers)
  headers.set("Authorization", `Bearer ${token}`)
  if (init.body) headers.set("Content-Type", "application/json")

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const api: ApiPort = {
  ask(question, conversationId) {
    return apiRequest("/v1/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
    })
  },
  conversations() {
    return apiRequest("/v1/conversations")
  },
  conversation(id) {
    return apiRequest(`/v1/conversations/${encodeURIComponent(id)}`)
  },
  deleteConversation(id) {
    return apiRequest(`/v1/conversations/${encodeURIComponent(id)}`, { method: "DELETE" })
  },
  feedback(messageId, rating, comment) {
    return apiRequest("/v1/feedback", {
      method: "POST",
      body: JSON.stringify({
        answer_message_id: messageId,
        rating,
        ...(comment ? { comment } : {}),
      }),
    })
  },
  deleteAccount() {
    return apiRequest("/v1/account", { method: "DELETE" })
  },
}

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

let installPrompt: InstallPromptEvent | undefined
const install: InstallPort = {
  get available() {
    return installPrompt !== undefined
  },
  async install() {
    if (!installPrompt) return false
    const prompt = installPrompt
    installPrompt = undefined
    await prompt.prompt()
    const choice = await prompt.userChoice
    return choice.outcome === "accepted"
  },
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault()
  installPrompt = event as InstallPromptEvent
  window.dispatchEvent(new Event("mtg-install-ready"))
})

registerSW({ immediate: true })

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
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
