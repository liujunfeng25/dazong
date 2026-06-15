import { expect, test } from '@playwright/test'

async function loginMonitor(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill('monitor001')
  await page.getByPlaceholder('密码').fill('demo123')
  await page.getByRole('button', { name: '立即登录 LOGIN' }).click()
  await expect(page).toHaveURL(/\/monitor\/dashboard/, { timeout: 30_000 })
}

test.describe('监管端 AI 浮窗冒烟', () => {
  test('打开浮窗、示例问题、出现参考来源或图表', async ({ page }) => {
    await loginMonitor(page)
    await page.getByRole('button', { name: /监管智能体/ }).click()
    await expect(page.getByText('监管智能体', { exact: true }).first()).toBeVisible({ timeout: 10_000 })

    const chip = page.locator('.ai-chip').filter({ hasText: '稽核链路怎么查' }).first()
    await expect(chip).toBeVisible({ timeout: 5_000 })
    await chip.click()

    await expect(
      page.locator('.ai-citations, .ai-chart, .ai-md').first(),
    ).toBeVisible({ timeout: 90_000 })
  })
})
