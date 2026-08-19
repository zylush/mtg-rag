import assert from "node:assert/strict"
import { readFile, readdir, stat } from "node:fs/promises"
import path from "node:path"

const dist = path.resolve("dist")
const manifest = JSON.parse(await readFile(path.join(dist, "manifest.webmanifest"), "utf8"))
const EMBER_ARCHIVE_BACKGROUND = "#17120f"

assert.equal(manifest.id, "/")
assert.equal(manifest.start_url, "/")
assert.equal(manifest.scope, "/")
assert.equal(manifest.display, "standalone")
assert.equal(manifest.lang, "en")
assert.equal(manifest.background_color, EMBER_ARCHIVE_BACKGROUND)
assert.equal(manifest.theme_color, EMBER_ARCHIVE_BACKGROUND)

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
  const iconPath = path.join(dist, filename)
  assert((await stat(iconPath)).size > 0, `${filename} is empty`)
  const png = await readFile(iconPath)
  assert.equal(png.toString("ascii", 1, 4), "PNG", `${filename} is not a PNG`)
  const [expectedWidth, expectedHeight] = sizes.split("x").map(Number)
  assert.equal(png.readUInt32BE(16), expectedWidth, `${filename} has the wrong width`)
  assert.equal(png.readUInt32BE(20), expectedHeight, `${filename} has the wrong height`)
}

const appleTouchIcon = await readFile(path.join(dist, "apple-touch-icon-180x180.png"))
assert.equal(appleTouchIcon.readUInt32BE(16), 180, "Apple touch icon has the wrong width")
assert.equal(appleTouchIcon.readUInt32BE(20), 180, "Apple touch icon has the wrong height")

const faviconSvg = (await readFile(path.join(dist, "favicon.svg"), "utf8")).toLowerCase()
for (const color of ["#17120f", "#2a1b14", "#f0e1bf", "#b84a2f", "#c89b4b"]) {
  assert(faviconSvg.includes(color), `favicon.svg is missing ${color}`)
}
assert(!faviconSvg.includes("#102a43"), "favicon.svg still uses the previous blue brand color")
assert((await stat(path.join(dist, "favicon.ico"))).size > 22, "favicon.ico is invalid or empty")

const files = await readdir(dist, { recursive: true })
assert(files.includes("sw.js"), "service worker is missing")
assert(!files.some((file) => file.endsWith(".map")), "production source maps must be disabled")
assert(!files.includes("e2e.html"), "development E2E harness was included in production")
assert(!files.some((file) => file.includes("e2e-harness")), "E2E code was included in production")

const robots = await readFile(path.join(dist, "robots.txt"), "utf8")
assert.match(robots, /User-agent:\s*\*/i)
assert.match(robots, /Disallow:\s*\//i, "development deployment must block indexing")
assert.doesNotMatch(robots, /Sitemap:/i, "blocked development robots must not advertise a sitemap")
const sitemap = await readFile(path.join(dist, "sitemap.xml"), "utf8")
assert.match(sitemap, /<urlset\b/)
assert.match(sitemap, /https:\/\/mtg-rules-desk-dev\.web\.app\/about/)
assert.doesNotMatch(sitemap, /\/desk|\/terms|\/privacy/)

for (const filename of ["index.html", "about.html"]) {
  const html = await readFile(path.join(dist, filename), "utf8")
  assert.match(html, /<link[^>]+rel="canonical"/i, `${filename} is missing a canonical`)
  assert.match(html, /<meta[^>]+property="og:title"/i, `${filename} is missing Open Graph`)
  assert.match(html, /<meta[^>]+name="twitter:card"/i, `${filename} is missing Twitter metadata`)
}
const homeHtml = await readFile(path.join(dist, "index.html"), "utf8")
assert.match(homeHtml, /application\/ld\+json/i, "home page is missing JSON-LD")
assert.match(homeHtml, /SoftwareApplication/, "home page is missing application schema")
assert.match(
  homeHtml,
  /<meta[^>]+name="theme-color"[^>]+content="#17120f"/i,
  "home page theme color does not match Ember Archive",
)

const serviceWorker = await readFile(path.join(dist, "sw.js"), "utf8")
for (const [filename] of expectedIcons) {
  assert(serviceWorker.includes(filename), `${filename} is not precached`)
}
assert(!serviceWorker.includes("/v1/"), "service worker must not cache API routes")
assert(
  serviceWorker.includes("denylist:[/^\\/__/]"),
  "service worker must not intercept Firebase reserved auth routes",
)
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
