import type { ApiPort } from "./types"

export type ApiClientErrorCode =
  | "AUTH_SESSION"
  | "NETWORK"
  | "CONVERSATION_CHANGED"
  | "REQUEST_IN_PROGRESS"
  | "RATE_LIMITED"
  | "SERVICE_UNAVAILABLE"
  | "REQUEST_FAILED"

export class ApiClientError extends Error {
  readonly code: ApiClientErrorCode

  constructor(code: ApiClientErrorCode) {
    super(code)
    this.name = "ApiClientError"
    this.code = code
    Object.setPrototypeOf(this, new.target.prototype)
  }
}

const USER_MESSAGES: Record<ApiClientErrorCode, string> = {
  AUTH_SESSION:
    "Your sign-in session could not be verified. Sign out and sign in again.",
  NETWORK:
    "The rules desk is temporarily unreachable. Check your connection and try again.",
  CONVERSATION_CHANGED:
    "This conversation changed in another tab. Review the latest messages and submit again.",
  REQUEST_IN_PROGRESS:
    "Your previous submission is still processing. Wait a moment and try again.",
  RATE_LIMITED: "You have reached the answer limit. Try again after the quota resets.",
  SERVICE_UNAVAILABLE: "The rules desk is temporarily unavailable. Try again shortly.",
  REQUEST_FAILED: "The request could not be completed. Check it and try again.",
}

export function userMessageFor(
  error: unknown,
  fallback = "The rules desk could not complete this request. Try again.",
): string {
  return error instanceof ApiClientError ? USER_MESSAGES[error.code] : fallback
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

type ApiClientOptions = {
  baseUrl: string
  token: () => Promise<string>
  fetchImpl?: FetchLike
}

async function codeForResponse(response: Response): Promise<ApiClientErrorCode> {
  if (response.status === 409) {
    try {
      const payload = (await response.clone().json()) as { code?: unknown }
      if (payload.code === "REQUEST_IN_PROGRESS") return "REQUEST_IN_PROGRESS"
      if (payload.code === "IDEMPOTENCY_CONFLICT") return "REQUEST_FAILED"
    } catch {
      // Fall through to the status-only mapping for non-JSON error responses.
    }
  }
  const status = response.status
  if (status === 401 || status === 403) return "AUTH_SESSION"
  if (status === 409) return "CONVERSATION_CHANGED"
  if (status === 429) return "RATE_LIMITED"
  if ([500, 502, 503, 504].includes(status)) return "SERVICE_UNAVAILABLE"
  return "REQUEST_FAILED"
}

export function createApiClient({
  baseUrl,
  token,
  fetchImpl = globalThis.fetch.bind(globalThis),
}: ApiClientOptions): ApiPort {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "")

  async function request<T>(
    path: string,
    init: RequestInit = {},
    requiresAuth = true,
  ): Promise<T> {
    const headers = new Headers(init.headers)
    if (requiresAuth) {
      let idToken: string
      try {
        idToken = await token()
      } catch {
        throw new ApiClientError("AUTH_SESSION")
      }
      headers.set("Authorization", `Bearer ${idToken}`)
    }
    if (init.body) headers.set("Content-Type", "application/json")

    let response: Response
    try {
      response = await fetchImpl(`${normalizedBaseUrl}${path}`, {
        ...init,
        cache: "no-store",
        headers,
      })
    } catch {
      throw new ApiClientError("NETWORK")
    }

    if (!response.ok) throw new ApiClientError(await codeForResponse(response))
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  return {
    ask(question, conversationId, requestId) {
      return request("/v1/ask", {
        method: "POST",
        body: JSON.stringify({
          question,
          request_id: requestId,
          ...(conversationId ? { conversation_id: conversationId } : {}),
        }),
      })
    },
    publicAsk(question) {
      return request(
        "/v1/public/ask",
        {
          method: "POST",
          body: JSON.stringify({ question }),
        },
        false,
      )
    },
    conversations() {
      return request("/v1/conversations")
    },
    conversation(id) {
      return request(`/v1/conversations/${encodeURIComponent(id)}`)
    },
    deleteConversation(id) {
      return request(`/v1/conversations/${encodeURIComponent(id)}`, { method: "DELETE" })
    },
    feedback(messageId, rating, comment) {
      return request("/v1/feedback", {
        method: "POST",
        body: JSON.stringify({
          answer_message_id: messageId,
          rating,
          ...(comment ? { comment } : {}),
        }),
      })
    },
    deleteAccount() {
      return request("/v1/account", { method: "DELETE" })
    },
  }
}
