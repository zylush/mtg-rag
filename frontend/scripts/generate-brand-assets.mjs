import { chromium } from "@playwright/test"
import { readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url))
const publicDirectory = path.resolve(scriptsDirectory, "../public")
const masterPath = path.join(publicDirectory, "favicon.svg")
const masterSvg = await readFile(masterPath, "utf8")

function maskableSvg(svg) {
  const body = svg.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "")
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">',
    '<rect width="48" height="48" fill="#17120f"/>',
    '<g transform="translate(7 7) scale(.7083333333)">',
    body,
    "</g></svg>",
  ].join("")
}

async function renderPng(browser, svg, size, filename) {
  const page = await browser.newPage({
    viewport: { width: size, height: size },
    deviceScaleFactor: 1,
  })
  const sizedSvg = svg.replace(
    "<svg ",
    '<svg style="display:block;width:100%;height:100%" ',
  )
  await page.setContent(
    '<!doctype html><style>html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#17120f}</style>' +
      sizedSvg,
  )
  await page.screenshot({
    path: path.join(publicDirectory, filename),
    type: "png",
    animations: "disabled",
  })
  await page.close()
}

function pngAsIco(png, size) {
  const header = Buffer.alloc(22)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(1, 4)
  header.writeUInt8(size >= 256 ? 0 : size, 6)
  header.writeUInt8(size >= 256 ? 0 : size, 7)
  header.writeUInt8(0, 8)
  header.writeUInt8(0, 9)
  header.writeUInt16LE(1, 10)
  header.writeUInt16LE(32, 12)
  header.writeUInt32LE(png.length, 14)
  header.writeUInt32LE(header.length, 18)
  return Buffer.concat([header, png])
}

const browser = await chromium.launch({ headless: true })
try {
  for (const [size, filename] of [
    [64, "pwa-64x64.png"],
    [180, "apple-touch-icon-180x180.png"],
    [192, "pwa-192x192.png"],
    [512, "pwa-512x512.png"],
  ]) {
    await renderPng(browser, masterSvg, size, filename)
  }
  await renderPng(browser, maskableSvg(masterSvg), 512, "maskable-icon-512x512.png")
} finally {
  await browser.close()
}

const faviconPng = await readFile(path.join(publicDirectory, "pwa-64x64.png"))
await writeFile(path.join(publicDirectory, "favicon.ico"), pngAsIco(faviconPng, 64))

console.log("Generated Ember Archive favicon and PWA assets")
