import { test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill('client001')
  await page.getByPlaceholder('请输入登录密码').fill('demo123')
  const me = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 30_000 }).catch(() => null)
  await page.getByRole('button', { name: /立即登录/ }).click()
  await me
  await page.waitForURL(/\/client\/select-canteen/, { timeout: 30_000 }).catch(() => {})
  const enter = page.getByRole('button', { name: '进入该食堂' }).first()
  await enter.waitFor({ state: 'visible', timeout: 30_000 }).catch(() => {})
  const me2 = page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 20_000 }).catch(() => null)
  await enter.click(); await me2; await page.waitForTimeout(1200)
}

async function placeQuoted(page: Page, term: string) {
  await page.goto('/client/orders/new')
  const picker = page.getByRole('button', { name: '进入该食堂' }).first()
  if (await picker.isVisible().catch(() => false)) { await picker.click(); await page.waitForTimeout(1200) }
  await page.getByText('选购商品').first().waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {})
  // 搜索有报价商品
  const search = page.getByPlaceholder('搜索商品...').first()
  if (await search.isVisible().catch(() => false)) { await search.fill(term); await page.waitForTimeout(1800) }
  const cards = page.getByTestId('order-product-card')
  const n = await cards.count()
  console.log(`[seed] term="${term}" 命中商品卡 ${n}`)
  if (n === 0) return false
  for (let i = 0; i < Math.min(n, 3); i++) {
    await cards.nth(i).getByRole('button', { name: '加入购物车' }).click().catch(() => {})
    await page.waitForTimeout(300)
  }
  await page.getByRole('button', { name: '打开购物车' }).first().click().catch(() => {})
  const submit = page.getByTestId('order-submit-cart')
  if (!(await submit.isVisible().catch(() => false))) return false
  await submit.click().catch(() => {})
  await page.getByRole('dialog', { name: '选择配送时间' }).waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
  const op = page.waitForResponse((r) => r.url().includes('/api/orders') && r.request().method() === 'POST' && r.status() === 200, { timeout: 20000 }).catch(() => null)
  await page.getByTestId('order-confirm-submit').click().catch(() => {})
  const rp = await op
  try { const pl = await rp?.json(); if (pl?.need_confirm) { const op2 = page.waitForResponse((r) => r.url().includes('/api/orders') && r.request().method() === 'POST' && r.status() === 200, { timeout: 20000 }).catch(() => null); await page.getByRole('button', { name: '继续下单' }).click().catch(() => {}); await op2 } } catch {}
  await page.waitForTimeout(800)
  console.log(`[seed] placed quoted order for "${term}"`)
  return true
}

test.use({ viewport: { width: 1280, height: 800 }, video: 'off' })

test('seed quoted orders', async ({ page }) => {
  test.setTimeout(180_000)
  await login(page)
  for (const term of ['中润长江鲜猪', '中粮鲜', '中润长江鲜猪肝']) await placeQuoted(page, term)
})
