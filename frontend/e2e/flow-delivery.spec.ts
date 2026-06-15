import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(new URL('.', import.meta.url))
const OUT = resolve(HERE, '../../../dazong-manual/images/delivery')
const TRIPS_DATE = '2026-05-28' // 有 10 个车次的日期

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

test('配送方 深度操作流', async ({ page }) => {
  test.setTimeout(300_000)
  await page.addInitScript(() => { window.print = () => {} })
  await login(page, 'delivery001', true)

  // 工作台
  await page.goto('/delivery/workbench'); await page.waitForTimeout(1800); await shot(page, '02-workbench')

  // 智能分单：选待分单 → 生成建议 → 综合分拆解（不提交）
  await page.goto('/delivery/smart-split'); await page.waitForTimeout(2000)
  await shot(page, '03-smart-split')
  try {
    // 全选待分单订单
    const headCb = page.locator('thead .el-checkbox__inner').first()
    if (await headCb.isVisible().catch(() => false)) { await headCb.click(); await page.waitForTimeout(600) }
    else { for (const cb of await page.locator('tbody .el-checkbox__inner').all()) { await cb.click().catch(() => {}) } }
    const gen = page.getByRole('button', { name: /生成建议|智能分单|生成分单/ }).first()
    if (await gen.isVisible().catch(() => false)) {
      await gen.click().catch(() => {}); await page.waitForTimeout(2500)
      await shot(page, '04-smart-split-result')
    }
  } catch (e) { console.log('[ss-fail]', (e as Error).message) }

  // 智能排线
  await page.goto('/delivery/smart-routing'); await page.waitForTimeout(2500); await shot(page, '05-smart-routing')

  // 发车计划（指定有数据的日期）
  await page.goto(`/delivery/dispatch-trips?date=${TRIPS_DATE}`); await page.waitForTimeout(2200); await shot(page, '06-dispatch-trips')
  try {
    const row = page.locator('tbody tr, .trip-card, .clickable-rows tr').first()
    if (await row.isVisible().catch(() => false)) { await row.click().catch(() => {}); await page.waitForTimeout(1800); await shot(page, '07-dispatch-detail') }
  } catch {}

  // 车队：车辆 / 设备 / 仓库
  await page.goto('/delivery/vehicles'); await page.waitForTimeout(1800); await shot(page, '08-vehicles')
  await page.goto('/delivery/devices'); await page.waitForTimeout(1800); await shot(page, '09-devices')
  await page.goto('/delivery/warehouses'); await page.waitForTimeout(1800); await shot(page, '10-warehouses')

  // 供货商管理
  await page.goto('/delivery/suppliers'); await page.waitForTimeout(1800); await shot(page, '11-suppliers')

  // 收货差异
  await page.goto('/delivery/receiving-differences'); await page.waitForTimeout(1800); await shot(page, '12-receiving-differences')

  // 售后工单
  await page.goto('/delivery/complaints'); await page.waitForTimeout(1800); await shot(page, '13-complaints')

  // 账单中心
  await page.goto('/delivery/bills'); await page.waitForTimeout(1800); await shot(page, '14-bills')

  // 消息中心
  await page.goto('/delivery/notifications'); await page.waitForTimeout(1800); await shot(page, '15-notifications')
})
