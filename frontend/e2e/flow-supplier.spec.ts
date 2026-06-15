import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const OUT = resolve(HERE, '../../../dazong-manual/images/supplier')
const ORDER_ID = '2706' // supplier001 配货(待发货) 真实单

async function shot(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true })
  await page.waitForTimeout(900)
  await page.screenshot({ path: resolve(OUT, `${name}.png`) })
  console.log(`[shot] ${name}`)
}

async function login(page: Page, user: string, withShot = false) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill(user)
  await page.getByPlaceholder('请输入登录密码').fill('demo123')
  if (withShot) await shot(page, '01-login')
  const me = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 30_000 }).catch(() => null)
  await page.getByRole('button', { name: /立即登录/ }).click()
  await me
  await page.waitForURL((u) => !u.pathname.endsWith('/login'), { timeout: 30_000 }).catch(() => {})
  await page.waitForTimeout(1200)
}

test.use({ viewport: { width: 1440, height: 900 }, video: 'off' })

test('供货方 深度操作流', async ({ page }) => {
  test.setTimeout(240_000)
  // 拦截原生打印，避免 headless 卡住
  await page.addInitScript(() => { window.print = () => {} })

  await login(page, 'supplier001', true)

  // 待配货 / 待发货 订单列表
  await page.goto('/supplier/orders'); await page.waitForTimeout(1800)
  await shot(page, '02-orders')

  // 订单详情（配货明细 + 打印 / 出库 动作）
  await page.goto(`/supplier/orders/${ORDER_ID}`); await page.waitForTimeout(1800)
  await shot(page, '03-order-detail')

  // 尝试展开/触发「打印配货单」预览（若为页内预览）
  try {
    for (const label of ['打印配货单', '打印小票', '打印拣货单', '打印']) {
      const b = page.getByRole('button', { name: label }).first()
      if (await b.isVisible().catch(() => false)) { await b.click().catch(() => {}); await page.waitForTimeout(1500); await shot(page, '04-print'); break }
    }
  } catch (e) { console.log('[print-fail]', (e as Error).message) }

  // 报价 / 招投标
  await page.goto('/supplier/quotes'); await page.waitForTimeout(1800)
  await shot(page, '05-quotes')

  // 周期质检报告
  await page.goto('/supplier/periodic-reports'); await page.waitForTimeout(1800)
  await shot(page, '06-periodic-reports')

  // 账单
  await page.goto('/supplier/bills'); await page.waitForTimeout(1800)
  await shot(page, '07-bills')

  // 消息中心
  await page.goto('/supplier/notifications'); await page.waitForTimeout(1800)
  await shot(page, '08-notifications')
})
