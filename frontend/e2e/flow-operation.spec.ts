import { test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'; import { resolve } from 'node:path'; import { fileURLToPath } from 'node:url'
const OUT = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../../dazong-manual/images/operation')
async function shot(page:Page,n:string){ mkdirSync(OUT,{recursive:true}); await page.waitForTimeout(900); await page.screenshot({path:resolve(OUT,`${n}.png`)}); console.log('[shot]',n) }
async function login(page:Page,u:string,s=false){ await page.goto('/login'); await page.getByPlaceholder('用户名 / 手机号 / ID').fill(u); await page.getByPlaceholder('请输入登录密码').fill('demo123'); if(s)await shot(page,'01-login'); const me=page.waitForResponse(r=>r.url().includes('/api/auth/me')&&r.status()===200,{timeout:30000}).catch(()=>null); await page.getByRole('button',{name:/立即登录/}).click(); await me; await page.waitForURL(x=>!x.pathname.endsWith('/login'),{timeout:30000}).catch(()=>{}); await page.waitForTimeout(1200) }
test.use({ viewport:{width:1440,height:900}, video:'off' })
test('运营端', async ({ page }) => {
  test.setTimeout(280000)
  await login(page,'operation001',true)
  await page.goto('/operation/dashboard'); await page.waitForTimeout(2000); await shot(page,'02-dashboard')
  await page.goto('/operation/categories'); await page.waitForTimeout(1800); await shot(page,'03-categories')
  await page.goto('/operation/products'); await page.waitForTimeout(1800); await shot(page,'04-products')
  // 尝试打开商品编辑弹窗
  try { const e=page.getByRole('button',{name:/编辑/}).first(); if(await e.isVisible().catch(()=>false)){ await e.click(); await page.waitForTimeout(1500); await shot(page,'05-product-edit'); await page.keyboard.press('Escape').catch(()=>{}); await page.waitForTimeout(500) } } catch{}
  await page.goto('/operation/smart-scale-recognition'); await page.waitForTimeout(2200); await shot(page,'06-smart-scale')
  await page.goto('/operation/contracts'); await page.waitForTimeout(1800); await shot(page,'07-contracts')
  await page.goto('/operation/accounts'); await page.waitForTimeout(1800); await shot(page,'08-accounts')
  await page.goto('/operation/client-canteens'); await page.waitForTimeout(1800); await shot(page,'09-client-canteens')
  await page.goto('/operation/orders'); await page.waitForTimeout(1800); await shot(page,'10-orders')
  await page.goto('/operation/receiving-differences'); await page.waitForTimeout(1800); await shot(page,'11-receiving-differences')
  await page.goto('/operation/billing-overview'); await page.waitForTimeout(1800); await shot(page,'12-billing-overview')
  await page.goto('/operation/billing-cycles'); await page.waitForTimeout(1800); await shot(page,'13-billing-cycles')
  await page.goto('/operation/tickets'); await page.waitForTimeout(1800); await shot(page,'14-tickets')
  await page.goto('/operation/periodic-reports'); await page.waitForTimeout(1800); await shot(page,'15-periodic-reports')
  await page.goto('/operation/notifications'); await page.waitForTimeout(1800); await shot(page,'16-notifications')
})
