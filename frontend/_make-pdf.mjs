import { chromium } from '@playwright/test'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
const [,, inArg, outArg] = process.argv
const inPath = resolve(inArg), outPath = resolve(outArg)
const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(pathToFileURL(inPath).href, { waitUntil: 'networkidle' })
await page.emulateMedia({ media: 'print' })
await page.pdf({ path: outPath, format: 'A4', printBackground: true, margin: { top:'0', bottom:'0', left:'0', right:'0' } })
await browser.close()
console.log('PDF 生成:', outPath)
