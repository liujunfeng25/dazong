import { expect, test, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const OUTPUT = resolve(process.cwd(), '../qa-reports/2026-06-12/evidence/web')
const PASSWORD = 'demo123'

function redactEvidence(value: string) {
  return value
    .replace(/([?&]token=)[^&\s'"]+/gi, '$1<redacted>')
    .replace(/(Bearer\s+)[A-Za-z0-9._~-]+/gi, '$1<redacted>')
}

type RouteResult = {
  role: string
  route: string
  finalUrl?: string
  bodyLength?: number
  api5xx: Array<{ url: string; status: number }>
  pageErrors: string[]
  consoleErrors: string[]
  error?: string
}

const routesByRole: Record<string, string[]> = {
  operation: [
    '/operation/dashboard',
    '/operation/categories',
    '/operation/products',
    '/operation/smart-scale-recognition',
    '/operation/periodic-reports',
    '/operation/accounts',
    '/operation/client-canteens',
    '/operation/contracts',
    '/operation/orders',
    '/operation/receiving-differences',
    '/operation/billing-overview',
    '/operation/billing-cycles',
    '/operation/tickets',
    '/operation/notifications',
  ],
  client: [
    '/client/dashboard',
    '/client/contracts',
    '/client/contracts/new',
    '/client/tenders',
    '/client/orders/new',
    '/client/orders',
    '/client/bills',
    '/client/notifications',
  ],
  delivery: [
    '/delivery/workbench',
    '/delivery/tenders',
    '/delivery/contracts',
    '/delivery/suppliers',
    '/delivery/orders',
    '/delivery/receiving-differences',
    '/delivery/complaints',
    '/delivery/vehicles',
    '/delivery/devices',
    '/delivery/warehouses',
    '/delivery/smart-split',
    '/delivery/smart-routing',
    '/delivery/dispatch-trips',
    '/delivery/bills',
    '/delivery/notifications',
  ],
  supplier: [
    '/supplier/orders',
    '/supplier/quotes',
    '/supplier/periodic-reports',
    '/supplier/bills',
    '/supplier/notifications',
  ],
  factory: [
    '/factory/orders',
    '/factory/bills',
    '/factory/reports',
    '/factory/reports/upload',
    '/factory/periodic-reports',
    '/factory/notifications',
  ],
  monitor: [
    '/monitor/dashboard',
    '/monitor/tianshu',
    '/monitor/price-cockpit',
    '/monitor/route-planning',
    '/monitor/orders',
    '/monitor/logistics',
    '/monitor/alerts',
    '/monitor/reports',
    '/monitor/home',
    '/monitor/notifications',
  ],
}

const usernames: Record<string, string> = {
  operation: 'operation001',
  client: 'client001',
  delivery: 'delivery001',
  supplier: 'supplier001',
  factory: 'factory001',
  monitor: 'monitor001',
}

async function login(page: Page, role: string) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill(usernames[role])
  await page.getByPlaceholder('请输入登录密码').fill(PASSWORD)
  await page.getByRole('button', { name: /立即登录/ }).click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 30_000 })
  if (role === 'client') {
    const enter = page.getByRole('button', { name: '进入该食堂' }).first()
    await enter.waitFor({ state: 'visible', timeout: 30_000 })
    const sessionResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/client/canteen-session') && response.status() === 200,
      { timeout: 30_000 },
    )
    const meResponse = page.waitForResponse(
      (response) => response.url().includes('/api/auth/me') && response.status() === 200,
      { timeout: 30_000 },
    )
    await enter.click()
    await sessionResponse
    await meResponse
    await page.waitForURL(/\/client\/dashboard/, { timeout: 30_000 })
    await expect
      .poll(async () => {
        const raw = await page.evaluate(() => localStorage.getItem('dz_user'))
        const user = raw ? JSON.parse(raw) : null
        return user?.canteen_id ?? null
      })
      .not.toBeNull()
  }
}

function formItem(page: Page, drawer: ReturnType<Page['getByRole']>, label: string) {
  return drawer.locator('.el-form-item').filter({
    has: page.locator('.el-form-item__label', { hasText: new RegExp(`^${label}$`) }),
  })
}

test.describe.configure({ mode: 'serial' })
test.use({ viewport: { width: 1440, height: 900 }, video: 'off' })

test('六类 PC 角色静态路由真实断言巡检', async ({ browser }) => {
  test.setTimeout(12 * 60_000)
  mkdirSync(OUTPUT, { recursive: true })
  const results: RouteResult[] = []

  for (const [role, routes] of Object.entries(routesByRole)) {
    const context = await browser.newContext()
    const page = await context.newPage()
    await login(page, role)

    for (const route of routes) {
      const row: RouteResult = {
        role,
        route,
        api5xx: [],
        pageErrors: [],
        consoleErrors: [],
      }
      const onResponse = (response: { url(): string; status(): number }) => {
        if (response.url().includes('/api/') && response.status() >= 500) {
          row.api5xx.push({ url: redactEvidence(response.url()), status: response.status() })
        }
      }
      const onPageError = (error: Error) => row.pageErrors.push(redactEvidence(error.message))
      const onConsole = (message: { type(): string; text(): string }) => {
        if (message.type() === 'error') row.consoleErrors.push(redactEvidence(message.text()))
      }
      page.on('response', onResponse)
      page.on('pageerror', onPageError)
      page.on('console', onConsole)
      try {
        await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 30_000 })
        await page.waitForTimeout(1200)
        row.finalUrl = new URL(page.url()).pathname
        row.bodyLength = (await page.locator('body').innerText()).trim().length
        if (row.finalUrl !== route) {
          throw new Error(`unexpected redirect: ${row.finalUrl}`)
        }
        if (route === '/monitor/tianshu') {
          const iframeCount = await page.locator('iframe').count()
          if (iframeCount < 1) throw new Error('tianshu iframe is missing')
        } else if ((row.bodyLength || 0) < 20) {
          throw new Error(`body is nearly empty: ${row.bodyLength}`)
        }
      } catch (error) {
        row.error = (error as Error).message
        await page
          .screenshot({
            path: resolve(OUTPUT, `${role}-${route.replaceAll('/', '_') || 'root'}.png`),
            fullPage: true,
          })
          .catch(() => {})
      } finally {
        page.off('response', onResponse)
        page.off('pageerror', onPageError)
        page.off('console', onConsole)
      }
      results.push(row)
    }
    await context.close()
  }

  writeFileSync(
    resolve(OUTPUT, 'route-smoke-results.json'),
    JSON.stringify(results, null, 2),
    'utf8',
  )
  const hardFailures = results.filter(
    (row) => row.error || row.api5xx.length > 0 || row.pageErrors.length > 0,
  )
  expect(
    hardFailures,
    `route failures: ${JSON.stringify(hardFailures, null, 2)}`,
  ).toEqual([])
})

test('商品标品与单位联动不能在 UI 中形成非法组合', async ({ page }) => {
  mkdirSync(OUTPUT, { recursive: true })
  await login(page, 'operation')
  await page.goto('/operation/products')
  await page.getByRole('button', { name: '新增商品' }).click()
  const drawer = page.getByRole('dialog', { name: '新增商品' })
  await expect(drawer).toBeVisible()

  const unitSelect = formItem(page, drawer, '单位').locator('.el-select')
  await unitSelect.click()
  let options = await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').allTextContents()
  expect(options).not.toContain('斤')
  expect(options).not.toContain('kg')
  await page.keyboard.press('Escape')

  const typeSelect = formItem(page, drawer, '品类类型').locator('.el-select')
  await typeSelect.click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: '非标品' }).click()
  await expect(unitSelect.locator('.el-select__placeholder')).toContainText('斤')

  await unitSelect.click()
  const nonstandardUnitDropdown = page.locator('.el-select-dropdown:visible').filter({ hasText: 'kg' })
  await expect(nonstandardUnitDropdown).toBeVisible()
  options = await nonstandardUnitDropdown.locator('.el-select-dropdown__item').allTextContents()
  expect(options).toEqual(expect.arrayContaining(['斤', 'kg']))
  expect(options).not.toContain('件')
  await page.keyboard.press('Escape')

  await typeSelect.click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: /^标品$/ }).click()
  await expect(unitSelect.locator('.el-select__placeholder')).toContainText('件')
  await page.screenshot({ path: resolve(OUTPUT, 'product-unit-linkage.png'), fullPage: true })
})

test('未登录和错误角色不能进入其他业务端页面', async ({ browser }) => {
  const anonymous = await browser.newPage()
  await anonymous.goto('/operation/products')
  await expect(anonymous).toHaveURL(/\/login$/)
  await anonymous.close()

  const context = await browser.newContext()
  const page = await context.newPage()
  await login(page, 'client')
  await page.goto('/operation/products')
  await expect(page).toHaveURL(/\/client\/dashboard$/)
  await context.close()
})

test('商品列表空数据与加载失败均不应白屏', async ({ page }) => {
  mkdirSync(OUTPUT, { recursive: true })
  await login(page, 'operation')

  await page.route('**/api/operation/products**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
    })
  })
  await page.goto('/operation/products')
  await expect(page.getByRole('button', { name: '新增商品' })).toBeVisible()
  expect((await page.locator('body').innerText()).trim().length).toBeGreaterThan(20)
  await page.unroute('**/api/operation/products**')

  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.route('**/api/operation/products**', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'QA forced failure' }),
    })
  })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('button', { name: '新增商品' })).toBeVisible()
  await expect(page.locator('.el-message', { hasText: 'QA forced failure' })).toBeVisible()
  await page.waitForTimeout(500)
  writeFileSync(
    resolve(OUTPUT, 'products-load-failure.json'),
    JSON.stringify({ pageErrors }, null, 2),
    'utf8',
  )
  expect(pageErrors).toEqual([])
})
