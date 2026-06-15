import { expect, test } from '@playwright/test'

/**
 * 监管端「北京全域」高德驾驶舱。
 *
 * 依赖：`docker compose up` 后前端 :80、后端 :8000（见 playwright.config.ts）。
 * - 接口用例不依赖高德 Key。
 * - 地图按钮依赖 VITE_AMAP_KEY / 安全域名；未就绪时跳过 UI 交互并注明原因。
 */
const base = () => process.env.PLAYWRIGHT_TEST_BASE_URL || 'http://127.0.0.1'

async function loginMonitor(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill('monitor001')
  await page.getByPlaceholder('请输入登录密码').fill('demo123')
  await page.getByRole('button', { name: /立即登录/ }).click()
  await page.waitForURL(/\/monitor/, { timeout: 45_000 })
}

test.describe('监管端北京驾驶舱', () => {
  test('驾车演示车辆接口：监管登录后可 200 拉全量清单', async ({ page }) => {
    await loginMonitor(page)
    const token = await page.evaluate(() => localStorage.getItem('dz_token'))
    expect(token, '登录后 localStorage 应有 dz_token').toBeTruthy()
    const res = await page.request.get(`${base()}/api/monitor/neural/beijing-demo/vehicles`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok()) {
      throw new Error(`HTTP ${res.status()}: ${await res.text()}`)
    }
    const body = (await res.json()) as { total?: number; vehicles?: unknown[] }
    expect(typeof body.total).toBe('number')
    expect(Array.isArray(body.vehicles)).toBeTruthy()
  })

  test('北京全域页：驾驶舱 DOM；地图 LIVE 时可点模拟路线并截图', async ({ page }) => {
    await loginMonitor(page)
    await page.goto('/monitor/dashboard?module=beijing-map')
    await expect(page.getByRole('heading', { name: /北京全域运营驾驶舱/ })).toBeVisible({ timeout: 30_000 })

    const locBtn = page.getByRole('button', { name: '模拟车辆定位' })
    const routeBtn = page.getByRole('button', { name: '模拟车辆路线' })
    const clearBtn = page.getByRole('button', { name: '清除演示' })
    await expect(locBtn).toBeVisible({ timeout: 20_000 })
    await expect(routeBtn).toBeVisible()
    await expect(clearBtn).toBeVisible()

    const mapLive = page.locator('.map-badge').filter({ hasText: 'MAP LIVE' })
    const live = await mapLive
      .waitFor({ state: 'visible', timeout: 120_000 })
      .then(() => true)
      .catch(() => false)

    if (!live || (await routeBtn.isDisabled())) {
      test.skip(
        true,
        '高德底图未就绪（容器未注入 VITE_AMAP_KEY 或域名白名单不含当前来源），已在上条用例验证演示接口；配置 Key 后重跑本用例可看路网轨迹截图',
      )
    }

    const vehiclesResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/monitor/neural/beijing-demo/vehicles') &&
        r.request().method() === 'GET' &&
        r.ok(),
      { timeout: 60_000 },
    )
    await routeBtn.click()
    const vr = await vehiclesResp
    expect(vr.status()).toBe(200)
    const body = (await vr.json()) as { vehicles?: unknown[] }
    expect(Array.isArray(body.vehicles)).toBeTruthy()

    await expect(page.getByText(/已开始绘制/).first()).toBeVisible({ timeout: 30_000 })
    await page.waitForTimeout(12_000)
    await page.screenshot({
      path: 'test-results/beijing-cockpit-routes.png',
      fullPage: true,
    })

    await clearBtn.click()
    await expect(clearBtn).toBeDisabled({ timeout: 10_000 })
  })
})
