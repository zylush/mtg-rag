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
    publicAsk: vi.fn().mockResolvedValue(ANSWER),
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

    expect(screen.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
    expect(screen.getByText("Question / Answer / Sources")).toBeVisible()
    expect(screen.getByRole("link", { name: /terms of service/i })).toBeVisible()
    expect(screen.getByRole("link", { name: /privacy policy/i })).toBeVisible()
  })

  it("starts Firebase auth from the first screen without an intermediate screen", async () => {
    const user = userEvent.setup()
    const auth = new FakeAuth(null)
    renderApp(auth, undefined, undefined, "/")

    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("textbox", { name: /rules question/i })).toBeVisible()
    expect(window.location.pathname).toBe("/desk")
    expect(auth.user).not.toBeNull()
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
    expect(screen.getByText(/effective date: august 24, 2026/i)).toBeVisible()
    expect(screen.getByText(/firebase user id and email address/i)).toBeVisible()
    expect(screen.getByText(/openai receives your question/i)).toBeVisible()
    expect(screen.getAllByText(/semantic cache for up to seven days/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/do not use advertising cookies or analytics/i)).toBeVisible()
    expect(screen.getByRole("link", { name: /email the privacy contact/i })).toHaveAttribute(
      "href",
      "mailto:paoloinigo30@gmail.com",
    )
    expect(screen.queryByText(/describe firebase identity/i)).not.toBeInTheDocument()

    window.history.replaceState({}, "", "/patch-history")
    window.dispatchEvent(new PopStateEvent("popstate"))
    expect(await screen.findByRole("heading", { name: /every patch, with a paper trail/i })).toBeVisible()
    expect(screen.getByText("158 commits recorded")).toBeVisible()
    expect(api.conversations).not.toHaveBeenCalled()
  })

  it("gives authenticated public pages a direct route back to the desk", async () => {
    const user = userEvent.setup()
    renderApp(undefined, undefined, undefined, "/about")

    expect(screen.getByRole("link", { name: /back to desk/i })).toBeVisible()
    expect(screen.queryByRole("link", { name: /^sign in$/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: /back to desk/i }))
    expect(window.location.pathname).toBe("/desk")
  })

  it("redirects a protected desk route to the first screen and returns after sign-in", async () => {
    const user = userEvent.setup()
    renderApp(new FakeAuth(null), undefined, undefined, "/desk")

    expect(screen.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
    expect(window.location.pathname).toBe("/")
    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("textbox", { name: /rules question/i })).toBeVisible()
    expect(window.location.pathname).toBe("/desk")
  })

  it("returns an intentional sign-out to the public first screen", async () => {
    const user = userEvent.setup()
    renderApp(undefined, undefined, undefined, "/desk")

    await user.click(await screen.findByRole("button", { name: /sign out/i }))

    expect(await screen.findByText("Question / Answer / Sources")).toBeVisible()
    expect(window.location.pathname).toBe("/")
  })

  it("shows sign-in progress while authentication is pending", async () => {
    const user = userEvent.setup()
    const auth = new FakeAuth(null)
    auth.signIn = vi.fn(() => new Promise<void>(() => undefined))
    renderApp(auth, undefined, undefined, "/")

    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(screen.getByRole("button", { name: /signing you in/i })).toBeDisabled()
  })

  it("shows authentication failures on the first screen", async () => {
    const user = userEvent.setup()
    const auth = new FakeAuth(null)
    auth.signIn = vi.fn().mockRejectedValue(new Error("provider failure"))
    renderApp(auth, undefined, undefined, "/")

    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(/sign-in did not complete/i)
    expect(window.location.pathname).toBe("/")
  })

  it("requires Firebase sign-in before exposing the rules desk", async () => {
    const user = userEvent.setup()
    renderApp(new FakeAuth(null))

    expect(screen.getByRole("heading", { name: /settle the ruling/i })).toBeVisible()
    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(await screen.findByRole("textbox", { name: /rules question/i })).toBeVisible()
    expect(screen.getByText("Development preview")).toBeVisible()
  })

  it("displays source attribution and the unofficial-product notice", async () => {
    renderApp(new FakeAuth(null))

    expect(screen.getByText("Public development preview")).toBeVisible()
    expect(screen.getByText(/unofficial fan content/i)).toBeVisible()
    expect(screen.getByText(/card data and rulings are provided through scryfall/i)).toBeVisible()
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
    expect(api.ask).toHaveBeenCalledWith(
      "What can block a creature with flying?",
      undefined,
      expect.any(String),
    )
  })

  it("reuses the same request ID when a failed submission is tried again unchanged", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.ask = vi
      .fn()
      .mockRejectedValueOnce(new ApiClientError("NETWORK"))
      .mockResolvedValueOnce(ANSWER)
    renderApp(undefined, api)
    const input = await screen.findByRole("textbox", { name: /rules question/i })

    await user.type(input, "What is flying?")
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    await screen.findByRole("alert")
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    await screen.findByText(/only be blocked by creatures with flying/i)

    const firstRequestId = vi.mocked(api.ask).mock.calls[0][2]
    const secondRequestId = vi.mocked(api.ask).mock.calls[1][2]
    expect(firstRequestId).toMatch(/^[0-9a-f-]{36}$/i)
    expect(secondRequestId).toBe(firstRequestId)
  })

  it("shows a conflict without automatically retrying a stale follow-up", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.ask = vi
      .fn()
      .mockResolvedValueOnce(ANSWER)
      .mockRejectedValueOnce(new ApiClientError("CONVERSATION_CHANGED"))
    renderApp(undefined, api)
    const input = await screen.findByRole("textbox", { name: /rules question/i })

    await user.type(input, "My opponent targets Slippery Bogle with Murder.")
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    await screen.findByText(/only be blocked by creatures with flying/i)
    await user.type(input, "What if it loses hexproof?")
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /conversation changed.*review.*submit again/i,
    )
    expect(api.ask).toHaveBeenNthCalledWith(
      2,
      "What if it loses hexproof?",
      "conversation-1",
      expect.any(String),
    )
    expect(api.ask).toHaveBeenCalledTimes(2)
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

  it("loads a saved chat into the desk and continues the same conversation", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /flying blockers/i }))

    expect(await screen.findByText("What blocks flying?")).toBeVisible()
    expect(api.conversation).toHaveBeenCalledWith("conversation-1")
    expect(window.location.pathname).toBe("/desk")

    await user.type(
      screen.getByRole("textbox", { name: /rules question/i }),
      "What if the blocker has reach?",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    await waitFor(() =>
      expect(api.ask).toHaveBeenCalledWith(
        "What if the blocker has reach?",
        "conversation-1",
        expect.any(String),
      ),
    )
  })

  it("starts a new chat without attaching the next question to loaded history", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /flying blockers/i }))
    expect(await screen.findByText("What blocks flying?")).toBeVisible()

    await user.click(screen.getByRole("button", { name: /new chat/i }))

    expect(screen.queryByText("What blocks flying?")).not.toBeInTheDocument()
    await user.type(
      screen.getByRole("textbox", { name: /rules question/i }),
      "How does deathtouch change combat?",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))

    await waitFor(() =>
      expect(api.ask).toHaveBeenCalledWith(
        "How does deathtouch change combat?",
        undefined,
        expect.any(String),
      ),
    )
  })

  it("uses route-backed modal drawers and restores trigger focus on Escape", async () => {
    const user = userEvent.setup()
    renderApp()
    const historyTrigger = await screen.findByRole("button", { name: /history/i })

    await user.click(historyTrigger)
    expect(window.location.pathname).toBe("/desk/history")
    expect(screen.getByRole("dialog", { name: /history/i })).toBeVisible()
    expect(screen.getByRole("button", { name: /close history/i })).toHaveFocus()

    await user.keyboard("{Escape}")
    await waitFor(() => expect(window.location.pathname).toBe("/desk"))
    expect(historyTrigger).toHaveFocus()
  })

  it("surfaces conversation deletion failures", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.deleteConversation = vi.fn().mockRejectedValue(new ApiClientError("NETWORK"))
    vi.spyOn(window, "confirm").mockReturnValue(true)
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /history/i }))
    await user.click(await screen.findByRole("button", { name: /flying blockers/i }))
    await user.click(screen.getByRole("button", { name: /delete conversation/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unreachable/i)
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

  it("surfaces account deletion failures", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.deleteAccount = vi.fn().mockRejectedValue(new ApiClientError("NETWORK"))
    renderApp(undefined, api)

    await user.click(await screen.findByRole("button", { name: /settings/i }))
    await user.click(screen.getByRole("button", { name: /delete account/i }))
    await user.type(screen.getByRole("textbox", { name: /type delete/i }), "DELETE")
    await user.click(screen.getByRole("button", { name: /permanently delete account/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unreachable/i)
  })

  it("offers installation only when the browser exposes an install prompt", async () => {
    const user = userEvent.setup()
    const install = { available: true, install: vi.fn().mockResolvedValue(true) }
    renderApp(undefined, undefined, install)

    await user.click(await screen.findByRole("button", { name: /settings/i }))
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
    expect(await screen.findByText(/feedback saved/i)).toBeVisible()
    expect(screen.getByRole("button", { name: /^helpful answer$/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("surfaces answer feedback failures", async () => {
    const user = userEvent.setup()
    const api = fakeApi()
    api.feedback = vi.fn().mockRejectedValue(new ApiClientError("NETWORK"))
    renderApp(undefined, api)

    await user.type(
      await screen.findByRole("textbox", { name: /rules question/i }),
      "Define flying",
    )
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    await user.click(await screen.findByRole("button", { name: /^helpful answer$/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(/feedback.*try again/i)
  })

  it("keeps secondary product links in Settings and removes the decorative empty desk", async () => {
    const user = userEvent.setup()
    renderApp()

    expect(screen.queryByText("704.5")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /open navigation/i })).not.toBeInTheDocument()
    await user.click(await screen.findByRole("button", { name: /settings/i }))
    expect(screen.getByRole("link", { name: /about/i })).toBeVisible()
    expect(screen.getByRole("link", { name: /terms of service/i })).toBeVisible()
    expect(screen.getByRole("link", { name: /privacy policy/i })).toBeVisible()
    expect(screen.queryByText(/^language$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^offline use$/i)).not.toBeInTheDocument()
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
