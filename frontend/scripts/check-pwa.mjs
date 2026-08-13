import assert from "node:assert/strict"
import { readFile, readdir, stat } from "node:fs/promises"
import path from "node:path"

const dist = path.resolve("dist")
const manifest = JSON.parse(await readFile(path.join(dist, "manifest.webmanifest"), "utf8"))

assert.equal(manifest.id, "/")
assert.equal(manifest.start_url, "/")
assert.equal(manifest.scope, "/")
assert.equal(manifest.display, "standalone")
assert.equal(manifest.lang, "en")

const expectedIcons = [
  ["pwa-192x192.png", "192x192", "any"],
  ["pwa-512x512.png", "512x512", "any"],
  ["maskable-icon-512x512.png", "512x512", "maskable"],
]
for (const [filename, sizes, purpose] of expectedIcons) {
  const icon = manifest.icons.find((candidate) => candidate.src.endsWith(filename))
  assert(icon, `manifest is missing ${filename}`)
  assert.equal(icon.type, "image/png")
  assert.equal(icon.sizes, sizes)
  assert.equal(icon.purpose, purpose)
  assert((await stat(path.join(dist, filename))).size > 0, `${filename} is empty`)
}

const files = await readdir(dist, { recursive: true })
assert(files.includes("sw.js"), "service worker is missing")
assert(!files.some((file) => file.endsWith(".map")), "production source maps must be disabled")
assert(!files.includes("e2e.html"), "development E2E harness was included in production")
assert(!files.some((file) => file.includes("e2e-harness")), "E2E code was included in production")

const serviceWorker = await readFile(path.join(dist, "sw.js"), "utf8")
for (const [filename] of expectedIcons) {
  assert(serviceWorker.includes(filename), `${filename} is not precached`)
}
assert(!serviceWorker.includes("/v1/"), "service worker must not cache API routes")
assert(serviceWorker.includes("skipWaiting"), "service worker must activate release updates")
assert(serviceWorker.includes("clientsClaim"), "service worker must control open clients after update")

const JavaScript = await Promise.all(
  files.filter((file) => file.endsWith(".js")).map((file) => readFile(path.join(dist, file), "utf8")),
)
const bundleText = JavaScript.join("\n").toLowerCase()
assert(!bundleText.includes("openai_api_key"), "OpenAI credential name leaked into browser assets")
assert(!bundleText.includes("sk-proj-"), "OpenAI project key leaked into browser assets")
assert(
  !bundleText.includes("http://localhost:8080") &&
    !bundleText.includes("http://127.0.0.1:8080"),
  "production browser assets must not include the configured development API origin",
)

console.log("PWA checks passed")
