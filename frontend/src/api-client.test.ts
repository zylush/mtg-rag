import { describe, expect, it, vi } from "vitest"

import { ApiClientError, createApiClient, userMessageFor } from "./api-client"

describe("API client error boundaries", () => {
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
