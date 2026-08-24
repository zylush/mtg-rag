import { describe, expect, it, vi } from "vitest"

import { ApiClientError, createApiClient, userMessageFor } from "./api-client"

describe("API client error boundaries", () => {
  it("sends the caller-owned request ID with authenticated asks", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          conversation_id: "00000000-0000-0000-0000-000000000001",
          message_id: "00000000-0000-0000-0000-000000000002",
          answer: "A grounded answer.",
          citations: [],
          assumptions: [],
          confidence: "high",
          needs_clarification: false,
          quota_remaining: 19,
          cache_status: "miss",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockResolvedValue("test-token"),
      fetchImpl,
    })

    await api.ask(
      "What is flying?",
      undefined,
      "00000000-0000-0000-0000-000000000030",
    )

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({
      question: "What is flying?",
      request_id: "00000000-0000-0000-0000-000000000030",
    })
  })

  it("keeps the public question path unauthenticated", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          conversation_id: "00000000-0000-0000-0000-000000000001",
          message_id: "00000000-0000-0000-0000-000000000002",
          answer: "A public answer.",
          citations: [],
          assumptions: [],
          confidence: "high",
          needs_clarification: false,
          quota_remaining: 0,
          cache_status: "miss",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    const token = vi.fn().mockResolvedValue("must-not-be-requested")
    const api = createApiClient({
      baseUrl: "https://example.test",
      token,
      fetchImpl,
    })

    await api.publicAsk("What is flying?")

    expect(token).not.toHaveBeenCalled()
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://example.test/v1/public/ask",
      expect.objectContaining({ method: "POST" }),
    )
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Headers).has("Authorization")).toBe(false)
  })

  it("maps Firebase token failures without starting a request", async () => {
    const fetchImpl = vi.fn()
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockRejectedValue(new Error("sensitive provider detail")),
      fetchImpl,
    })

    await expect(api.conversations()).rejects.toMatchObject({
      code: "AUTH_SESSION",
    })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it("maps browser network failures without exposing their raw message", async () => {
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockResolvedValue("test-token"),
      fetchImpl: vi.fn().mockRejectedValue(new TypeError("secret network detail")),
    })

    const failure = await api.conversations().catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiClientError)
    expect(failure).toMatchObject({ code: "NETWORK" })
    expect(userMessageFor(failure)).not.toContain("secret network detail")
  })

  it('maps a conversation conflict to actionable client state', async () => {
    const api = createApiClient({
      baseUrl: 'https://example.test',
      token: vi.fn().mockResolvedValue('test-token'),
      fetchImpl: vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'conversation changed' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    })

    const failure = await api.conversations().catch((error: unknown) => error)

    expect(failure).toMatchObject({ code: 'CONVERSATION_CHANGED' })
    expect(userMessageFor(failure)).toMatch(/conversation changed.*review.*submit again/i)
  })

  it("distinguishes an in-progress idempotent retry from a conversation conflict", async () => {
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockResolvedValue("test-token"),
      fetchImpl: vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "the matching request is still in progress",
            code: "REQUEST_IN_PROGRESS",
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    })

    const failure = await api.conversations().catch((error: unknown) => error)

    expect(failure).toMatchObject({ code: "REQUEST_IN_PROGRESS" })
    expect(userMessageFor(failure)).toMatch(/previous submission is still processing/i)
  })

  it("does not mislabel request-ID reuse as a conversation change", async () => {
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockResolvedValue("test-token"),
      fetchImpl: vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "request ID was already used for a different request",
            code: "IDEMPOTENCY_CONFLICT",
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    })

    const failure = await api.conversations().catch((error: unknown) => error)

    expect(failure).toMatchObject({ code: "REQUEST_FAILED" })
    expect(userMessageFor(failure)).not.toMatch(/conversation changed/i)
  })

  it.each([
    [401, "AUTH_SESSION"],
    [429, "RATE_LIMITED"],
    [503, "SERVICE_UNAVAILABLE"],
    [422, "REQUEST_FAILED"],
  ] as const)("maps HTTP %i to %s", async (status, code) => {
    const api = createApiClient({
      baseUrl: "https://example.test",
      token: vi.fn().mockResolvedValue("test-token"),
      fetchImpl: vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "internal server detail" }), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    })

    await expect(api.conversations()).rejects.toMatchObject({ code })
  })
})
