import { expect, test } from '@playwright/test'

/**
 * 电子围栏 E2E
 *
 * - 冒烟：不依赖高德脚本，验证 Tab + 工具条 DOM。
 * - 绘制：需地图容器出现（Key 有效且域名白名单包含当前访问来源）。在 Docker 内用
 *   `PLAYWRIGHT_TEST_BASE_URL=http://host.docker.internal:80` 时，若白名单仅有 127.0.0.1，
 *   地图可能永不就绪，此时用例会 test.skip，避免假失败。
 *
 * 推荐本机验证绘制：`cd frontend && npx playwright test e2e/electronic-fence-draw.spec.ts`
 * （Node 20+，且 `docker compose up` 后 baseURL 指向 http://127.0.0.1）。
 */
async function loginDelivery(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('textbox', { name: '用户名' }).fill('delivery001')
  await page.getByRole('textbox', { name: '密码' }).fill('demo123')
  await page.getByRole('button', { name: '登录系统' }).click()
  await page.waitForTimeout(2200)
}

async function openFenceTab(page: import('@playwright/test').Page) {
  await page.goto('/delivery/smart-routing')
  await page.waitForTimeout(600)
  await page.getByRole('tab', { name: '电子围栏' }).click()
  await page.waitForTimeout(500)
}

/** 地图是否已挂载（高德在 div 内创建 .amap-container） */
async function waitFenceMapReady(page: import('@playwright/test').Page, ms: number) {
  try {
    await page.waitForFunction(
      () => {
        const w = document.querySelector('.fence-map')
        if (!w) return false
        const c = w.querySelector('.amap-container')
        if (!c) return false
        const r = c.getBoundingClientRect()
        if (r.width < 80 || r.height < 80) return false
        const poly = [...document.querySelectorAll('.fence-tool-btn')].find(
          (b) => b.textContent?.trim() === '多边形',
        ) as HTMLButtonElement | undefined
        return Boolean(poly && !poly.disabled)
      },
      undefined,
      { timeout: ms },
    )
    return true
  } catch {
    return false
  }
}

async function clickFenceMap(
  page: import('@playwright/test').Page,
  box: { x: number; y: number; width: number; height: number },
  rx: number,
  ry: number,
) {
  const x = box.x + box.width * rx
  const y = box.y + box.height * ry
  await page.mouse.click(x, y)
  await page.waitForTimeout(140)
}

test.describe('配送端电子围栏', () => {
  test('冒烟：电子围栏 Tab 与左侧工具条可见', async ({ page }) => {
    await loginDelivery(page)
    await openFenceTab(page)

    await expect(page.getByText('绘制工具')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.fence-map').first()).toBeVisible()
    await expect(page.locator('.fence-map-tools').getByRole('button', { name: '浏览' })).toBeVisible()
    await expect(page.locator('.fence-map-tools').getByRole('button', { name: '多边形' })).toBeVisible()
    await expect(page.getByText('围栏列表')).toBeVisible()
  })

  test('多边形：地图就绪时，点击后应出现底部预览条，取消后消失', async ({ page }) => {
    await loginDelivery(page)
    await openFenceTab(page)

    if (await page.getByText('未配置高德 Key').isVisible().catch(() => false)) {
      test.skip(true, '构建未注入 VITE_AMAP_KEY')
    }

    const mapOk = await waitFenceMapReady(page, 22_000)
    if (!mapOk) {
      test.skip(
        true,
        '地图未就绪（多为 Key 安全域名不含当前访问来源；请在宿主机用 Node 20 执行 npm run test:e2e:fence 且用 http://127.0.0.1 打开站点）',
      )
    }

    const mapEl = page.locator('.fence-map').first()
    const mapBox = await mapEl.boundingBox()
    expect(mapBox).not.toBeNull()
    if (!mapBox) return

    const polyBtn = page.locator('.fence-map-tools').getByRole('button', { name: '多边形' })
    await expect(polyBtn).toBeEnabled({ timeout: 10_000 })
    await polyBtn.click()
    await expect(page.getByText('多边形：单击加点，双击结束')).toBeVisible({ timeout: 8000 })

    await clickFenceMap(page, mapBox, 0.42, 0.48)
    await clickFenceMap(page, mapBox, 0.58, 0.46)
    await clickFenceMap(page, mapBox, 0.52, 0.62)
    const lx = mapBox.x + mapBox.width * 0.52
    const ly = mapBox.y + mapBox.height * 0.62
    await page.mouse.click(lx, ly, { clickCount: 2, delay: 80 })
    await page.waitForTimeout(200)

    const draftBar = page.locator('.fence-draft-bar')
    await expect(draftBar).toBeVisible({ timeout: 25_000 })
    await expect(draftBar.getByRole('button', { name: '保存' })).toBeVisible()
    await expect(draftBar.getByText(/禁行区域/)).toBeVisible()
    await expect(draftBar.getByText(/多边形/)).toBeVisible()

    await draftBar.getByRole('button', { name: '取消' }).click()
    await expect(draftBar).toBeHidden({ timeout: 12_000 })
  })

  test('圆形：地图就绪时拖动后出现预览条', async ({ page }) => {
    await loginDelivery(page)
    await openFenceTab(page)

    if (await page.getByText('未配置高德 Key').isVisible().catch(() => false)) {
      test.skip(true, '构建未注入 VITE_AMAP_KEY')
    }

    const mapOk = await waitFenceMapReady(page, 22_000)
    if (!mapOk) {
      test.skip(true, '地图未就绪，跳过（见多边形用例说明）')
    }

    const mapEl = page.locator('.fence-map').first()
    const mapBox = await mapEl.boundingBox()
    expect(mapBox).not.toBeNull()
    if (!mapBox) return

    await page.locator('.fence-map-tools').getByRole('button', { name: '圆形' }).click()
    await expect(page.getByText(/圆形：按下拖动/)).toBeVisible({ timeout: 8000 })

    const ax = mapBox.x + mapBox.width * 0.45
    const ay = mapBox.y + mapBox.height * 0.48
    const bx = mapBox.x + mapBox.width * 0.58
    const by = mapBox.y + mapBox.height * 0.55
    await page.mouse.move(ax, ay)
    await page.mouse.down()
    await page.mouse.move(bx, by, { steps: 14 })
    await page.mouse.up()
    await page.waitForTimeout(500)

    const draftBar = page.locator('.fence-draft-bar')
    await expect(draftBar).toBeVisible({ timeout: 25_000 })
    await draftBar.getByRole('button', { name: '取消' }).click()
    await expect(draftBar).toBeHidden({ timeout: 12_000 })
  })

  test('浏览：结束多边形绘制提示', async ({ page }) => {
    await loginDelivery(page)
    await openFenceTab(page)

    if (!(await waitFenceMapReady(page, 18_000))) {
      test.skip(true, '地图未就绪')
    }

    await page.locator('.fence-map-tools').getByRole('button', { name: '多边形' }).click()
    await expect(page.getByText('多边形：单击加点，双击结束')).toBeVisible()
    await page.locator('.fence-map-tools').getByRole('button', { name: '浏览' }).click()
    await expect(page.getByText('多边形：单击加点，双击结束')).toBeHidden({ timeout: 8000 })
  })
})
