import { expect, test } from '@playwright/test'

async function loginClientAndSelectCanteen(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('textbox', { name: '用户名' }).fill('client001')
  await page.getByRole('textbox', { name: '密码' }).fill('demo123')
  await page.getByRole('button', { name: '登录系统' }).click()

  await expect(page).toHaveURL(/\/client\/select-canteen/, { timeout: 30_000 })
  const enterButtons = page.getByRole('button', { name: '进入该食堂' })
  await expect(enterButtons.first()).toBeVisible({ timeout: 30_000 })
  const canteenSessionPromise = page.waitForResponse(
    (response) =>
      response.url().includes('/api/client/canteen-session') &&
      response.request().method() === 'POST' &&
      response.status() === 200,
    { timeout: 30_000 },
  )
  await enterButtons.first().click()
  await canteenSessionPromise
  await page.waitForFunction(() => window.location.pathname === '/client/contracts', undefined, {
    timeout: 30_000,
  })
}

async function waitForOrderPost(page: import('@playwright/test').Page) {
  return page.waitForResponse(
    (response) =>
      response.url().includes('/api/orders') &&
      response.request().method() === 'POST' &&
      response.status() === 200,
    { timeout: 30_000 },
  )
}

test.describe('采购端下单流程', () => {
  test('客户可选商品、提交配送时间，并在订单列表看到新订单', async ({ page }) => {
    await loginClientAndSelectCanteen(page)

    await page.goto('/client/orders/new')
    await expect(page.getByText('选购商品')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('暂无可选配送单位')).toBeHidden({ timeout: 10_000 })

    const firstProduct = page.getByTestId('order-product-card').first()
    await expect(firstProduct).toBeVisible({ timeout: 30_000 })
    const productName = (await firstProduct.locator('.product-name').innerText()).trim()

    await firstProduct.getByRole('button', { name: '加入购物车' }).click()
    await page.getByRole('button', { name: '打开购物车' }).first().click()

    const cartLine = page.getByTestId('order-cart-line').first()
    await expect(cartLine).toBeVisible({ timeout: 10_000 })
    await expect(cartLine).toContainText(productName)

    await page.getByTestId('order-submit-cart').click()
    const scheduleDialog = page.getByRole('dialog', { name: '选择配送时间' })
    await expect(scheduleDialog).toBeVisible({ timeout: 10_000 })
    await expect(scheduleDialog.getByPlaceholder('请输入本次订单配送地址（可精确到门牌）')).not.toHaveValue('')

    let orderResponsePromise = waitForOrderPost(page)
    await page.getByTestId('order-confirm-submit').click()
    let orderPayload = await (await orderResponsePromise).json()

    if (orderPayload.need_confirm) {
      orderResponsePromise = waitForOrderPost(page)
      await page.getByRole('button', { name: '继续下单' }).click()
      orderPayload = await (await orderResponsePromise).json()
    }

    expect(orderPayload.order_no, '创建订单接口应返回订单号').toBeTruthy()
    expect(orderPayload.status).toBe('下单')
    await expect(page.getByText('订单提交成功')).toBeVisible({ timeout: 10_000 })
    await expect(scheduleDialog).toBeHidden({ timeout: 10_000 })

    await page.goto('/client/orders')
    await page.getByPlaceholder('订单号').fill(orderPayload.order_no)
    await page.getByRole('button', { name: '筛选' }).click()

    await expect(page.getByText(orderPayload.order_no)).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.el-table__body-wrapper')).toContainText('待履约')
  })
})
