import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const OUT = resolve(HERE, '../../../dazong-manual/images/client')
const RECEIPT = '/Users/Admin/Pictures/单据/IMG_1803.jpg'
const RECV_ORDER_ID = '2441' // canteen51 收货状态真实单 OD26080431225911
const ADV_ORDER_ID = '2443'  // 收货确认状态，进度更完整 OD27002932120347

async function shot(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true })
  await page.waitForTimeout(800)
  await page.screenshot({ path: resolve(OUT, `${name}.png`) })
  console.log(`[shot] ${name}`)
}

async function loginClient(page: Page, withShots = false) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill('client001')
  await page.getByPlaceholder('请输入登录密码').fill('demo123')
  if (withShots) await shot(page, '01-login')
  const me = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 30_000 }).catch(() => null)
  await page.getByRole('button', { name: /立即登录/ }).click()
  await me
  await page.waitForURL(/\/client\/select-canteen/, { timeout: 30_000 }).catch(() => {})
  const enter = page.getByRole('button', { name: '进入该食堂' }).first()
  await enter.waitFor({ state: 'visible', timeout: 30_000 }).catch(() => {})
  if (withShots) await shot(page, '02-select-canteen')
  const me2 = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 20_000 }).catch(() => null)
  await enter.click()
  await me2
  await page.waitForTimeout(1500)
}

async function ensureCanteen(page: Page) {
  const picker = page.getByRole('button', { name: '进入该食堂' }).first()
  if (await picker.isVisible().catch(() => false)) {
    const me = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 15_000 }).catch(() => null)
    await picker.click(); await me; await page.waitForTimeout(1200)
  }
}

test.use({ viewport: { width: 1440, height: 900 }, video: 'off' })

// ============ 测试一：下单簇（看板 / 选购 / OCR / 语音 / 下单）============
test('采购方-下单簇', async ({ page }) => {
  test.setTimeout(180_000)
  await loginClient(page, true)

  await page.goto('/client/dashboard'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '03-dashboard')

  await page.goto('/client/orders/new'); await ensureCanteen(page)
  await page.getByText('选购商品').first().waitFor({ state: 'visible', timeout: 30_000 }).catch(() => {})
  await page.waitForTimeout(1500)
  await shot(page, '04-order-new')

  // 语音下单面板（仅展示输入界面；解析依赖 LLM，可能需关 VPN）
  try {
    const vb = page.getByRole('button', { name: '语音下单' }).first()
    if (await vb.isVisible().catch(() => false)) { await vb.click(); await page.waitForTimeout(1000); await shot(page, '06-voice-panel'); await vb.click().catch(() => {}) }
  } catch {}

  // 手动选商品 → 购物车 → 配送时间 → 下单成功
  try {
    await page.getByTestId('order-product-card').nth(0).getByRole('button', { name: '加入购物车' }).click().catch(() => {})
    await page.getByTestId('order-product-card').nth(2).getByRole('button', { name: '加入购物车' }).click().catch(() => {})
    await page.getByRole('button', { name: '打开购物车' }).first().click().catch(() => {})
    await page.getByTestId('order-cart-line').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
    await shot(page, '07-cart')
    await page.getByTestId('order-submit-cart').click().catch(() => {})
    await page.getByRole('dialog', { name: '选择配送时间' }).waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
    await shot(page, '08-schedule')
    const op = page.waitForResponse((r) => r.url().includes('/api/orders') && r.request().method() === 'POST' && r.status() === 200, { timeout: 20000 }).catch(() => null)
    await page.getByTestId('order-confirm-submit').click().catch(() => {})
    const rp = await op
    try { const pl = await rp?.json(); if (pl?.need_confirm) { await page.getByRole('button', { name: '继续下单' }).click().catch(() => {}); await page.waitForTimeout(1200) } } catch {}
    await page.getByText('订单提交成功').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
    await shot(page, '09-order-success')
  } catch (e) { console.log('[order-fail]', (e as Error).message) }

  // OCR 放最后：真实上传 IMG_1803.jpg → 识别结果弹窗（演示模式返回示例表格）
  // 注意：观测到上传后 headless 页面会崩溃，故置于最后，不影响前面采集
  try {
    await page.goto('/client/orders/new'); await ensureCanteen(page)
    await page.getByText('选购商品').first().waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {})
    await page.locator('input[type="file"]').first().setInputFiles(RECEIPT)
    await page.waitForTimeout(5000)
    await shot(page, '05-ocr-result')
  } catch (e) { console.log('[ocr-fail]', (e as Error).message) }
})

// ============ 测试二：浏览簇（订单 / 收货 / 合约 / 招标 / 账单 / 消息）============
test('采购方-浏览簇', async ({ page }) => {
  test.setTimeout(180_000)
  await loginClient(page)

  await page.goto('/client/orders'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '10-orders-list')

  await page.goto(`/client/orders/${ADV_ORDER_ID}`); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '11-order-detail')

  await page.goto(`/client/orders/${RECV_ORDER_ID}`); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '12-order-receivable')

  await page.goto(`/client/receive/${RECV_ORDER_ID}`); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '13-receive')

  await page.goto('/client/contracts'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '14-contracts')

  await page.goto('/client/contracts/new'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '15-tender-new')

  await page.goto('/client/tenders'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '16-tenders')

  await page.goto('/client/bills'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '17-bills')

  await page.goto('/client/notifications'); await ensureCanteen(page); await page.waitForTimeout(1800)
  await shot(page, '18-notifications')
})
