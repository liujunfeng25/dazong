import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'; import { resolve } from 'node:path'; import { fileURLToPath } from 'node:url'
const OUT = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../../dazong-manual/images/factory')
async function shot(page:Page,n:string){ mkdirSync(OUT,{recursive:true}); await page.waitForTimeout(900); await page.screenshot({path:resolve(OUT,`${n}.png`)}); console.log('[shot]',n) }
async function login(page:Page,u:string,s=false){ await page.goto('/login'); await page.getByPlaceholder('用户名 / 手机号 / ID').fill(u); await page.getByPlaceholder('请输入登录密码').fill('demo123'); if(s)await shot(page,'01-login'); const me=page.waitForResponse(r=>r.url().includes('/api/auth/me')&&r.status()===200,{timeout:30000}).catch(()=>null); await page.getByRole('button',{name:/立即登录/}).click(); await me; await page.waitForURL(u2=>!u2.pathname.endsWith('/login'),{timeout:30000}).catch(()=>{}); await page.waitForTimeout(1200) }
test.use({ viewport:{width:1440,height:900}, video:'off' })
test('工厂端', async ({ page }) => {
  test.setTimeout(180000)
  await login(page,'factory001',true)
  await page.goto('/factory/orders'); await page.waitForTimeout(1800); await shot(page,'02-orders')
  await page.goto('/factory/reports'); await page.waitForTimeout(1800); await shot(page,'03-reports')
  await page.goto('/factory/reports/upload'); await page.waitForTimeout(1800); await shot(page,'04-report-upload')
  await page.goto('/factory/periodic-reports'); await page.waitForTimeout(1800); await shot(page,'05-periodic-reports')
  await page.goto('/factory/bills'); await page.waitForTimeout(1800); await shot(page,'06-bills')
  await page.goto('/factory/notifications'); await page.waitForTimeout(1800); await shot(page,'07-notifications')
})
