import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'; import { resolve } from 'node:path'; import { fileURLToPath } from 'node:url'
const OUT = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../../dazong-manual/images/monitor')
async function shot(page:Page,n:string){ mkdirSync(OUT,{recursive:true}); await page.screenshot({path:resolve(OUT,`${n}.png`)}); console.log('[shot]',n) }
async function login(page:Page,u:string,s=false){ await page.goto('/login'); await page.getByPlaceholder('用户名 / 手机号 / ID').fill(u); await page.getByPlaceholder('请输入登录密码').fill('demo123'); if(s){await page.waitForTimeout(700);await shot(page,'01-login')} const me=page.waitForResponse(r=>r.url().includes('/api/auth/me')&&r.status()===200,{timeout:30000}).catch(()=>null); await page.getByRole('button',{name:/立即登录/}).click(); await me; await page.waitForURL(x=>!x.pathname.endsWith('/login'),{timeout:30000}).catch(()=>{}); await page.waitForTimeout(1200) }
test.use({ viewport:{width:1920,height:1080}, video:'off' })
test('监管端', async ({ page }) => {
  test.setTimeout(220000)
  await login(page,'monitor001',true)
  await page.goto('/monitor/dashboard'); await page.waitForTimeout(3500); await shot(page,'02-dashboard')
  await page.goto('/monitor/tianshu'); await page.waitForTimeout(16000); await shot(page,'03-tianshu')
  await page.goto('/monitor/route-planning'); await page.waitForTimeout(3500); await shot(page,'04-route-planning')
  await page.goto('/monitor/orders'); await page.waitForTimeout(4000); await shot(page,'05-orders-trace')
  await page.goto('/monitor/logistics'); await page.waitForTimeout(3000); await shot(page,'06-logistics')
  await page.goto('/monitor/alerts'); await page.waitForTimeout(3000); await shot(page,'07-alerts')
  await page.goto('/monitor/reports'); await page.waitForTimeout(3000); await shot(page,'08-reports')
  await page.goto('/monitor/notifications'); await page.waitForTimeout(2500); await shot(page,'09-notifications')
})
