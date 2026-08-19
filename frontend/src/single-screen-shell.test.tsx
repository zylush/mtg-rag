import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { App } from "./App"
import type { ApiPort, AskResponse, AuthPort, InstallPort, User } from "./types"

const ANSWER: AskResponse = {
  conversation_id: "conversation-1",
  message_id: "message-2",
  answer: "Blood Moon removes Urza's Saga's printed land types and abilities.",
  citations: [
    {
      passage_id: "rule-305.7",
      claim: "Setting a land's basic land type replaces its rules text.",
      label: "Comprehensive Rules 305.7",
      url: "https://magic.wizards.com/en/rules#305.7",
    },
  ],
  assumptions: ["Blood Moon is already on the battlefield."],
  confidence: "high",
  needs_clarification: false,
  quota_remaining: 19,
  cache_status: "miss",
}

class SignedInAuth implements AuthPort {
  subscribe(listener: (user: User | null) => void) {
    listener({ uid: "firebase-1", email: "judge@example.com" })
    return () => undefined
  }

  async signIn() {}
  async signOut() {}
  async token() {
    return "test-token"
  }
}

function fakeApi(answer: Promise<AskResponse> = Promise.resolve(ANSWER)): ApiPort {
  return {
    ask: vi.fn(() => answer),
    conversations: vi.fn().mockResolvedValue([]),
    conversation: vi.fn().mockRejectedValue(new Error("not used")),
    deleteConversation: vi.fn().mockResolvedValue(undefined),
    feedback: vi.fn().mockResolvedValue(undefined),
    deleteAccount: vi.fn().mockResolvedValue(undefined),
  }
}

function renderDesk(
  api: ApiPort = fakeApi(),
  install: InstallPort = { available: true, install: vi.fn().mockResolvedValue(true) },
) {
  window.history.replaceState({}, "", "/desk")
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App auth={new SignedInAuth()} api={api} install={install} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  Object.defineProperty(window.navigator, "onLine", {
    configurable: true,
    value: true,
  })
})

describe("single-screen rules command desk", () => {
  it("starts at the command input and supports shortcuts and quick queries", async () => {
    const user = userEvent.setup()
    renderDesk()

    const input = await screen.findByRole("textbox", { name: /rules question/i })
    await waitFor(() => expect(input).toHaveFocus())
    expect(screen.getByText(/retrieval online/i)).toBeVisible()
    expect(screen.getByRole("button", { name: /install pwa/i })).toBeVisible()

    input.blur()
    await user.keyboard("/")
    expect(input).toHaveFocus()

    await user.click(screen.getByRole("button", { name: /blood moon.*urza's saga/i }))
    expect(input).toHaveValue("How does Blood Moon interact with Urza's Saga?")
  })

  it("shows a loading skeleton and then a grounded answer with usable evidence controls", async () => {
    const user = userEvent.setup()
    let resolveAnswer!: (answer: AskResponse) => void
    const pendingAnswer = new Promise<AskResponse>((resolve) => {
      resolveAnswer = resolve
    })
    const api = fakeApi(pendingAnswer)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
    renderDesk(api)

    const input = await screen.findByRole("textbox", { name: /rules question/i })
    await user.type(input, "What happens to Urza's Saga under Blood Moon?")
    await user.click(screen.getByRole("button", { name: /^ask$/i }))
    expect(screen.getByRole("status", { name: /checking official sources/i })).toBeVisible()

    resolveAnswer(ANSWER)
    expect(await screen.findByText(ANSWER.answer)).toBeVisible()
    expect(screen.getByText(/grounded in retrieved rules sources/i)).toBeVisible()
    expect(screen.getByText(/comprehensive rules 305\.7/i)).toBeVisible()
    expect(screen.getByText(/expand full citation tree/i)).toBeVisible()

    await user.click(screen.getByRole("button", { name: /copy ruling/i }))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining(ANSWER.answer))
    expect(await screen.findByText(/ruling copied/i)).toBeVisible()
  })
})
