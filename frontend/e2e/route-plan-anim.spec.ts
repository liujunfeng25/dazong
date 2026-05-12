import { expect, test } from '@playwright/test'

/** 默认点标：用 marker 的 style 中 top/left（相对地图容器） */
async function animMarkerMapOffset(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const m = document.querySelector('.amap-marker[title^="模拟在途"]') as HTMLElement | null
    if (!m) return null
    const st = m.getAttribute('style') || ''
    const top = /top:\s*([0-9.]+)px/.exec(st)
    const left = /left:\s*([0-9.]+)px/.exec(st)
    if (!top || !left) return null
    return { top: Number(top[1]), left: Number(left[1]) }
  })
}

function dist(
  a: { x: number; y: number } | null,
  b: { x: number; y: number } | null,
): number {
  if (!a || !b) return 0
  return Math.hypot(a.x - b.x, a.y - b.y)
}

test.describe('配送端路线规划 · 轨迹动画', () => {
  test('选明日单排线后播放轨迹，车标在屏幕上发生明显位移；地图可拖移', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('textbox', { name: '用户名' }).fill('delivery001')
    await page.getByRole('textbox', { name: '密码' }).fill('demo123')
    await page.getByRole('button', { name: '登录系统' }).click()
    await page.waitForTimeout(2500)

    await page.goto('/delivery/smart-routing')
    await page.waitForTimeout(1500)

    const dateInput = page.locator('.el-form-item').filter({ hasText: '计划日期' }).locator('input').first()
    await dateInput.fill('2026-05-07')
    await dateInput.press('Tab')
    await page.waitForTimeout(1200)

    await expect(page.getByText(/已选 0 \/ [1-9]/)).toBeVisible({ timeout: 30_000 })

    await page.getByRole('button', { name: '全选' }).click()
    await expect(page.getByText(/已选 [1-9]\d* \/ [1-9]/)).toBeVisible()

    const planBtn = page.getByRole('button', { name: '生成智能路线' })
    await planBtn.click()
    await page.locator('.el-button.is-loading').first().waitFor({ state: 'hidden', timeout: 120_000 })

    await expect(page.getByText(/总距离：[\d.]+/)).toBeVisible({ timeout: 15_000 })

    const vehicleSelect = page.locator('.map-toolbar .el-select').first()
    await vehicleSelect.click()
    const firstPlate = page.locator('.el-select-dropdown__item').filter({ hasText: /^京/ }).first()
    await firstPlate.waitFor({ state: 'visible', timeout: 10_000 })
    await firstPlate.click({ force: true })
    await page.waitForTimeout(800)

    const playBtn = page.getByRole('button', { name: '播放轨迹' })
    await expect(playBtn).toBeEnabled()
    await playBtn.click()

    await page.waitForTimeout(800)
    const p1 = await animMarkerMapOffset(page)
    expect(p1, '应能找到模拟在途 marker').not.toBeNull()

    await page.waitForTimeout(5000)
    const p2 = await animMarkerMapOffset(page)
    expect(p2).not.toBeNull()

    const moved = dist(p1, p2)
    expect(moved, `marker 在地图容器内位移应 > 5px，实际 ${moved}`).toBeGreaterThan(5)

    const mapBox = page.locator('.amap-container').first()
    await expect(mapBox).toBeVisible()
    const box = await mapBox.boundingBox()
    expect(box).not.toBeNull()
    if (box) {
      const cx = box.x + box.width / 2
      const cy = box.y + box.height / 2
      await page.mouse.move(cx, cy)
      await page.mouse.down()
      await page.mouse.move(cx - 180, cy + 40, { steps: 12 })
      await page.mouse.up()
    }
    await page.waitForTimeout(400)
    const p3 = await animMarkerMapOffset(page)
    expect(p3).not.toBeNull()
    expect(dist(p2, p3), '拖移地图后 marker 的 top/left 应变化').toBeGreaterThan(3)

    await page.getByRole('button', { name: '停止' }).click()
    await expect(playBtn).toBeEnabled()
  })

  test('未选具体车辆时播放按钮禁用', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('textbox', { name: '用户名' }).fill('delivery001')
    await page.getByRole('textbox', { name: '密码' }).fill('demo123')
    await page.getByRole('button', { name: '登录系统' }).click()
    await page.waitForTimeout(2500)
    await page.goto('/delivery/smart-routing')
    await page.waitForTimeout(1200)

    await expect(page.getByRole('button', { name: '播放轨迹' })).toBeDisabled()
  })
})
