export function resolveApiBaseUrl(configuredBaseUrl: string | undefined, browserOrigin: string): string {
  const baseUrl = configuredBaseUrl?.trim() || browserOrigin
  const normalized = baseUrl.replace(/\/+$/, "")
  if (!normalized) throw new Error("An API base URL or browser origin is required")
  return normalized
}
