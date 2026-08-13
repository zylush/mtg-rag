import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
// Route coverage follows the public-to-authenticated product flow.

import { App } from "./App"
import { ApiClientError } from "./api-client"
import type {
  ApiPort,
  AskResponse,
  AuthPort,
  ConversationDetail,
  ConversationSummary,
  InstallPort,
  User,
} from "./types"

const ANSWER: AskResponse = {
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

class FakeAuth implements AuthPort {
  user: User | null
  private listener: ((user: User | null) => void) | null = null

  constructor(user: User | null = null) {
    this.user = user
  }

  subscribe(listener: (user: User | null) => void) {
    this.listener = listener
    listener(this.user)
    return () => {
      this.listener = null
    }
  }

  async signIn() {
    this.user = { uid: "firebase-1", email: "judge@example.com" }
    this.listener?.(this.user)
  }

  async signOut() {
    this.user = null
    this.listener?.(null)
  }

  async token() {
    return "test-token"
  }
}

function fakeApi(): ApiPort {
  return {
    ask: vi.fn().mockResolvedValue(ANSWER),
    conversations: vi.fn().mockResolvedValue([
      {
        id: "conversation-1",
        title: "Flying blockers",
        updated_at: "2026-08-12T00:00:00Z",
      } satisfies ConversationSummary,
    ]),
    conversation: vi.fn().mockResolvedValue({
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
          content: ANSWER.answer,
          created_at: "2026-08-12T00:00:01Z",
          citations: ANSWER.citations,
        },
      ],
    } satisfies ConversationDetail),
    deleteConversation: vi.fn().mockResolvedValue(undefined),
    feedback: vi.fn().mockResolvedValue(undefined),
    deleteAccount: vi.fn().mockResolvedValue(undefined),
  }
}

function renderApp(
  auth: AuthPort = new FakeAuth({ uid: "firebase-1", email: "judge@example.com" }),
  api: ApiPort = fakeApi(),
  install: InstallPort = { available: false, install: vi.fn() },
  path = "/desk",
) {
  window.history.replaceState({}, "", path)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App auth={auth} api={api} install={install} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  Object.defineProperty(window.navigator, "onLine", {
    configurable: true,
    value: true,
  })
})

describe("MTG Rules Desk", () => {
  it("renders a public welcome page with a static source preview", () => {
    renderApp(new FakeAuth(null), undefined, undefined, "/")

    expect(screen.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
    expect(screen.getByText(/question.*answer.*sources/i)).toBeVisible()
    expect(screen.getByRole("link", { name: /terms of service/i })).toBeVisible()
    expect(screen.getByRole("link", { name: /privacy policy/i })).toBeVisible()
  })

  it("renders about and legal pages without authentication or API calls", async () => {
    const api = fakeApi()
    renderApp(new FakeAuth(null), api, undefined, "/about")

    expect(screen.getByRole("heading", { name: /about mtg rules desk/i })).toBeVisible()
    expect(screen.getByText(/how an answer is produced/i)).toBeVisible()
    expect(api.conversations).not.toHaveBeenCalled()

    window.history.replaceState({}, "", "/terms")
    window.dispatchEvent(new PopStateEvent("popstate"))
    expect(await screen.findByRole("heading", { name: /terms of service/i })).toBeVisible()
    expect(screen.getByText(/pending legal review/i)).toBeVisible()

    window.history.replaceState({}, "", "/privacy")
    window.dispatchEvent(new PopStateEvent("popstate"))
    expect(await screen.findByRole("heading", { name: /privacy policy/i })).toBeVisible()
  })

  it("redirects a protected desk route to login and returns after sign-in", async () => {
    const user = userEvent.setup()
    renderApp(new FakeAuth(null), undefined, undefined, "/desk")

    expect(screen.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
    expect(window.location.pathname).toBe("/login")
    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("textbox", { name: /rules question/i })).toBeVisible()
    expect(window.location.pathname).toBe("/desk")
  })

  it("shows sign-in progress while authentication is pending", async () => {
    const user = userEvent.setup()
    const auth = new FakeAuth(null)
    auth.signIn = vi.fn(() => new Promise<void>(() => undefined))
    renderApp(auth, undefined, undefined, "/login")

    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(screen.getByRole("button", { name: /signing you in/i })).toBeDisabled()
  })

  it("requires Firebase sign-in before exposing the rules desk", async () => {
    const user = userEvent.setup()
    renderApp(new FakeAuth(null))

    expect(screen.getByRole("heading", { name: /settle the rules question/i })).toBeVisible()
    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("textbox", { name: /rules question/i })).toBeVisible()
  })

  it("displays source attribution and the unofficial-product notice", async () => {
    renderApp(new FakeAuth(null))

    expect(screen.getByText(/unofficial fan content/i)).toBeVisible()
    expect(screen.getByText(/card data and rulings are provided by scryfall/i)).toBeVisible()
  })

  it("asks a question, displays quota and renders only server citations as links", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "What can block a creature with flying?",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    expect(await screen.findByText(/only be blocked by creatures with flying/i)).toBeVisible()
    expect(screen.getByText("19 answers left today")).toBeVisible()
    expect(screen.getByRole("link", { name: /comprehensive rules 702.9/i })).toHaveAttribute(
      "href",
      ANSWER.citations[0].url,
    )
    expect(api.ask).toHaveBeenCalledWith("What can block a creature with flying?", undefined)
  })

  it("does not send an answer request while offline", async () => {
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: false,
    })
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "What is first strike?",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    expect(screen.getByText(/answers require an internet connection/i)).toBeVisible()
    expect(api.ask).not.toHaveBeenCalled()
  })

  it("shows an actionable sign-in message when an answer token cannot be acquired", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.ask = vi.fn().mockRejectedValue(new ApiClientError("AUTH_SESSION"))
    renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "Define a target",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /sign-in session could not be verified.*sign out and sign in again/i,
    )
  })

  it("shows a safe network error when history cannot load", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.conversations = vi.fn().mockRejectedValue(new ApiClientError("NETWORK"))
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /history/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /temporarily unreachable.*check your connection/i,
    )
  })

  it("opens and permanently deletes owned history after confirmation", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    vi.spyOn(window, "confirm").mockReturnValue(true)
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /history/i }))
    await user.click(await screen.findByRole("button", { name: /flying blockers/i }))
    expect(await screen.findByText("What blocks flying?")).toBeVisible()

    await user.click(screen.getByRole("button", { name: /delete conversation/i }))
    await waitFor(() => expect(api.deleteConversation).toHaveBeenCalledWith("conversation-1"))
  })

  it("requires typed confirmation before account deletion", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /settings/i }))
    await user.click(screen.getByRole("button", { name: /delete account/i }))
    await user.type(screen.getByRole("textbox", { name: /type delete/i }), "DELETE")
    await user.click(screen.getByRole("button", { name: /permanently delete account/i }))

    await waitFor(() => expect(api.deleteAccount).toHaveBeenCalledOnce())
  })

  it("offers installation only when the browser exposes an install prompt", async () => {
    const user = userEvent.setup()
    const install = { available: true, install: vi.fn().mockResolvedValue(true) }
    renderApp(undefined, undefined, install)

    await user.click(await screen.findByRole("button", { name: /install app/i }))

    expect(install.install).toHaveBeenCalledOnce()
  })

  it("submits explicit answer feedback", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "Define flying",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    await user.click(await screen.findByRole("button", { name: /^helpful answer$/i }))

    expect(api.feedback).toHaveBeenCalledWith(ANSWER.message_id, 1)
  })

  it("renders answer markdown without raw HTML or arbitrary links", async () => {
    const api = fakeApi()
    api.ask = vi.fn().mockResolvedValue({
      ...ANSWER,
      answer: '<img src=x onerror="alert(1)"> [bad](javascript:alert(1)) **safe**',
    })
    const user = userEvent.setup()
    const { container } = renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "Define flying",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    expect(await screen.findByText("safe")).toBeVisible()
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
  })
})
