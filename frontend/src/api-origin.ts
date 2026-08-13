export function resolveApiBaseUrl(
  configuredBaseUrl: string | undefined,
  browserOrigin: string,
  isDevelopment: boolean,
): string {
  const baseUrl = (isDevelopment ? configuredBaseUrl?.trim() : undefined) || browserOrigin
  const normalized = baseUrl.replace(/\/+$/, "")
  if (!normalized) throw new Error("An API base URL or browser origin is required")
  return normalized
}
