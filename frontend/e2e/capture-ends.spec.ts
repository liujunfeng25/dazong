import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(new URL('.', import.meta.url))

/**
 * 采集脚本（非断言测试）：登录各端 → 导航到关键页面 → 截图 + 录像。
 * 产物用于操作说明视频的真实画面素材。
 * 运行：依赖 docker compose 已起（前端 :80 / 后端 :8000）。
 *   cd frontend && npx playwright test e2e/capture-ends.spec.ts --project=chromium
 * 截图输出：dazong-ops-videos/assets/captures/{role}/{name}.png
 * 录像输出：见 test.use 的 video 配置（test-results/ 下）。
 */

const CAPTURE_ROOT = resolve(HERE, '../../../dazong-ops-videos/assets/captures')

const PASSWORD = 'demo123'

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: 'on', size: { width: 1920, height: 1080 } },
})

async function login(page: Page, username: string) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill(username)
  await page.getByPlaceholder('请输入登录密码').fill(PASSWORD)
  // 登录会先 POST /auth/login 再 GET /auth/me 才写入 token 并跳转；必须等鉴权完成再继续，
  // 否则首个 goto 在未登录态被守卫打回 /login
  const meResp = page
    .waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 30_000 })
    .catch(() => null)
  await page.getByRole('button', { name: /立即登录/ }).click()
  await meResp
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 30_000 }).catch(() => {})
  await page.waitForTimeout(800)
}

async function loginClient(page: Page) {
  await login(page, 'client001')
  // client 登录后需选食堂
  await page.waitForURL(/\/client\/select-canteen/, { timeout: 30_000 }).catch(() => {})
  const enter = page.getByRole('button', { name: '进入该食堂' }).first()
  // 食堂卡片由 listClientCanteensApi 异步加载，必须等按钮渲染出来再点
  await enter.waitFor({ state: 'visible', timeout: 30_000 }).catch(() => {})
  if (await enter.isVisible().catch(() => false)) {
    const waitSession = page
      .waitForResponse(
        (r) => r.url().includes('/api/client/canteen-session') && r.status() === 200,
        { timeout: 30_000 },
      )
      .catch(() => null)
    await enter.click()
    await waitSession
    // applyCanteenSession 之后还会异步 fetchMe 写回 dz_user，必须等它落地再继续，否则重载丢 canteen_id
    await page
      .waitForResponse((r) => r.url().includes('/api/auth/me') && r.status() === 200, { timeout: 15_000 })
      .catch(() => null)
    await page.waitForTimeout(1500)
    await page.waitForLoadState('domcontentloaded').catch(() => {})
  }
}

async function shot(page: Page, role: string, name: string, route?: string) {
  try {
    if (route) {
      await page.goto(route)
      await page.waitForLoadState('domcontentloaded').catch(() => {})
    }
    // client 整页重载会丢失内存里的食堂选择，守卫弹出选择页；点"进入该食堂"用 SPA 跳回原页
    const enter = page.getByRole('button', { name: '进入该食堂' }).first()
    if (await enter.isVisible().catch(() => false)) {
      await enter.click().catch(() => {})
      await page.waitForTimeout(1500)
    }
    // 给图表/动画一点稳定时间
    await page.waitForTimeout(2500)
    const dir = resolve(CAPTURE_ROOT, role)
    mkdirSync(dir, { recursive: true })
    await page.screenshot({ path: resolve(dir, `${name}.png`) })
    console.log(`[shot] ${role}/${name} <- ${route ?? '(current)'}`)
  } catch (e) {
    console.log(`[shot-FAIL] ${role}/${name} <- ${route ?? '(current)'}: ${(e as Error).message}`)
  }
}

// ---------- 采购方 ----------
test('capture client', async ({ page }) => {
  await loginClient(page)
  await shot(page, 'client', '01-contracts', '/client/contracts')
  await shot(page, 'client', '02-order-new', '/client/orders/new')
  await shot(page, 'client', '03-orders', '/client/orders')
  await shot(page, 'client', '04-bills', '/client/bills')
})

// ---------- 供货方 ----------
test('capture supplier', async ({ page }) => {
  await login(page, 'supplier001')
  await shot(page, 'supplier', '01-orders', '/supplier/orders')
  await shot(page, 'supplier', '02-quotes', '/supplier/quotes')
  await shot(page, 'supplier', '03-bills', '/supplier/bills')
})

// ---------- 配送方 ----------
test('capture delivery', async ({ page }) => {
  await login(page, 'delivery001')
  await shot(page, 'delivery', '01-workbench', '/delivery/workbench')
  await shot(page, 'delivery', '02-smart-split', '/delivery/smart-split')
  await shot(page, 'delivery', '03-route-plan', '/delivery/route-plan')
  await shot(page, 'delivery', '04-dispatch-trips', '/delivery/dispatch-trips')
  await shot(page, 'delivery', '05-vehicles', '/delivery/vehicles')
})

// ---------- 工厂方 ----------
test('capture factory', async ({ page }) => {
  await login(page, 'factory001')
  await shot(page, 'factory', '01-orders', '/factory/orders')
  await shot(page, 'factory', '02-reports', '/factory/reports')
  await shot(page, 'factory', '03-bills', '/factory/bills')
})

// ---------- 运营方 ----------
test('capture operation', async ({ page }) => {
  await login(page, 'operation001')
  await shot(page, 'operation', '01-dashboard', '/operation/dashboard')
  await shot(page, 'operation', '02-products', '/operation/products')
  await shot(page, 'operation', '03-accounts', '/operation/accounts')
  await shot(page, 'operation', '04-client-canteens', '/operation/client-canteens')
  await shot(page, 'operation', '05-contracts', '/operation/contracts')
  await shot(page, 'operation', '06-smart-scale-recognition', '/operation/smart-scale-recognition')
})

// ---------- 监管方 ----------
test('capture monitor', async ({ page }) => {
  await login(page, 'monitor001')
  await shot(page, 'monitor', '01-dashboard', '/monitor/dashboard')
  await shot(page, 'monitor', '02-tianshu', '/monitor/tianshu')
  await shot(page, 'monitor', '03-price-cockpit', '/monitor/price-cockpit')
  await shot(page, 'monitor', '04-orders', '/monitor/orders')
  await shot(page, 'monitor', '05-logistics', '/monitor/logistics')
  await shot(page, 'monitor', '06-alerts', '/monitor/alerts')
})
