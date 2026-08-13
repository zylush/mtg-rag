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
import { createApiClient } from "./api-client"
import { resolveApiBaseUrl } from "./api-origin"
import type { AuthPort, InstallPort } from "./types"
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

const apiBaseUrl = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL as string | undefined,
  window.location.origin,
)

const api = createApiClient({ baseUrl: apiBaseUrl, token: () => auth.token() })

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
