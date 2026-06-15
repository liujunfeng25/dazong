# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: qa-nine-end-audit.spec.ts >> 商品列表空数据与加载失败均不应白屏
- Location: e2e/qa-nine-end-audit.spec.ts:272:1

# Error details

```
Error: expect(received).toEqual(expected) // deep equality

- Expected  - 1
+ Received  + 3

- Array []
+ Array [
+   "Request failed with status code 500",
+ ]
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e3]:
    - complementary [ref=e4]:
      - generic [ref=e5]:
        - generic [ref=e6]: DAZONG PLATFORM
        - generic [ref=e7]: 运营端
      - menubar [ref=e8]:
        - menuitem "运营看板" [ref=e9] [cursor=pointer]
        - menuitem "分类管理" [ref=e10] [cursor=pointer]
        - menuitem "商品管理" [ref=e11] [cursor=pointer]
        - menuitem "智能秤识别训练" [ref=e12] [cursor=pointer]
        - menuitem "周期报告审核" [ref=e13] [cursor=pointer]
        - menuitem "合约查看" [ref=e14] [cursor=pointer]
        - menuitem "账号管理" [ref=e15] [cursor=pointer]
        - menuitem "客户食堂" [ref=e16] [cursor=pointer]
        - menuitem "订单监控" [ref=e17] [cursor=pointer]
        - menuitem "收货差异" [ref=e18] [cursor=pointer]
        - menuitem "账单总览" [ref=e19] [cursor=pointer]
        - menuitem "账期配置" [ref=e20] [cursor=pointer]
        - menuitem "工单处理" [ref=e21] [cursor=pointer]
        - menuitem "消息中心" [ref=e22] [cursor=pointer]
    - generic [ref=e23]:
      - generic [ref=e25]:
        - generic [ref=e26]:
          - generic [ref=e27]: 大宗物资供应链管理系统
          - generic [ref=e28]: 2026/6/12 17:37:27
        - generic [ref=e29]:
          - generic [ref=e30]:
            - button "通知" [ref=e31] [cursor=pointer]:
              - generic [ref=e32]: 通知
            - superscript [ref=e33]: "11"
          - generic [ref=e34]: 运营端
          - button "O" [ref=e36] [cursor=pointer]:
            - generic [ref=e37]: O
      - generic [ref=e38]:
        - generic [ref=e41]:
          - generic [ref=e42]:
            - textbox "搜索商品" [ref=e47]
            - generic [ref=e51] [cursor=pointer]:
              - generic:
                - combobox [ref=e53]
                - generic [ref=e54]: 一级分类
              - img [ref=e57]
            - generic [ref=e62] [cursor=pointer]:
              - generic:
                - combobox [ref=e64]
                - generic [ref=e65]: 二级分类
              - img [ref=e68]
            - generic [ref=e73] [cursor=pointer]:
              - generic:
                - combobox [ref=e75]
                - generic [ref=e76]: 所属厂家
              - img [ref=e79]
            - button "搜索" [ref=e83] [cursor=pointer]:
              - generic [ref=e84]: 搜索
          - button "新增商品" [ref=e86] [cursor=pointer]:
            - generic [ref=e87]: 新增商品
        - generic [ref=e89]:
          - generic [ref=e91]:
            - table [ref=e93]:
              - rowgroup [ref=e105]:
                - row "编号 商品 分类 参考价 图片 品类类型 所属厂家 质检模式 状态 操作" [ref=e106]:
                  - columnheader "编号" [ref=e107]:
                    - generic [ref=e108]: 编号
                  - columnheader "商品" [ref=e109]:
                    - generic [ref=e110]: 商品
                  - columnheader "分类" [ref=e111]:
                    - generic [ref=e112]: 分类
                  - columnheader "参考价" [ref=e113]:
                    - generic [ref=e114]: 参考价
                  - columnheader "图片" [ref=e115]:
                    - generic [ref=e116]: 图片
                  - columnheader "品类类型" [ref=e117]:
                    - generic [ref=e118]: 品类类型
                  - columnheader "所属厂家" [ref=e119]:
                    - generic [ref=e120]: 所属厂家
                  - columnheader "质检模式" [ref=e121]:
                    - generic [ref=e122]: 质检模式
                  - columnheader "状态" [ref=e123]:
                    - generic [ref=e124]: 状态
                  - columnheader "操作" [ref=e125]:
                    - generic [ref=e126]: 操作
            - generic [ref=e130]:
              - table:
                - rowgroup
              - generic [ref=e132]: 暂无数据
          - generic [ref=e135]:
            - generic [ref=e136]: 共 0 条
            - generic [ref=e139] [cursor=pointer]:
              - generic:
                - combobox [ref=e141]
                - generic [ref=e142]: 20条/页
              - img [ref=e145]
            - button "上一页" [disabled] [ref=e147]:
              - generic:
                - img
            - list [ref=e148]:
              - listitem "第 1 页" [ref=e149]: "1"
            - button "下一页" [disabled] [ref=e150]:
              - generic:
                - img
            - generic [ref=e151]:
              - generic [ref=e152]: 前往
              - spinbutton "页" [ref=e155]: "1"
              - generic [ref=e156]: 页
  - alert [ref=e157]:
    - img [ref=e159]
    - paragraph [ref=e161]: QA forced failure
```

# Test source

```ts
  206 |     }
  207 |     await context.close()
  208 |   }
  209 | 
  210 |   writeFileSync(
  211 |     resolve(OUTPUT, 'route-smoke-results.json'),
  212 |     JSON.stringify(results, null, 2),
  213 |     'utf8',
  214 |   )
  215 |   const hardFailures = results.filter(
  216 |     (row) => row.error || row.api5xx.length > 0 || row.pageErrors.length > 0,
  217 |   )
  218 |   expect(
  219 |     hardFailures,
  220 |     `route failures: ${JSON.stringify(hardFailures, null, 2)}`,
  221 |   ).toEqual([])
  222 | })
  223 | 
  224 | test('商品标品与单位联动不能在 UI 中形成非法组合', async ({ page }) => {
  225 |   mkdirSync(OUTPUT, { recursive: true })
  226 |   await login(page, 'operation')
  227 |   await page.goto('/operation/products')
  228 |   await page.getByRole('button', { name: '新增商品' }).click()
  229 |   const drawer = page.getByRole('dialog', { name: '新增商品' })
  230 |   await expect(drawer).toBeVisible()
  231 | 
  232 |   const unitSelect = formItem(page, drawer, '单位').locator('.el-select')
  233 |   await unitSelect.click()
  234 |   let options = await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').allTextContents()
  235 |   expect(options).not.toContain('斤')
  236 |   expect(options).not.toContain('kg')
  237 |   await page.keyboard.press('Escape')
  238 | 
  239 |   const typeSelect = formItem(page, drawer, '品类类型').locator('.el-select')
  240 |   await typeSelect.click()
  241 |   await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: '非标品' }).click()
  242 |   await expect(unitSelect.locator('.el-select__placeholder')).toContainText('斤')
  243 | 
  244 |   await unitSelect.click()
  245 |   const nonstandardUnitDropdown = page.locator('.el-select-dropdown:visible').filter({ hasText: 'kg' })
  246 |   await expect(nonstandardUnitDropdown).toBeVisible()
  247 |   options = await nonstandardUnitDropdown.locator('.el-select-dropdown__item').allTextContents()
  248 |   expect(options).toEqual(expect.arrayContaining(['斤', 'kg']))
  249 |   expect(options).not.toContain('件')
  250 |   await page.keyboard.press('Escape')
  251 | 
  252 |   await typeSelect.click()
  253 |   await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: /^标品$/ }).click()
  254 |   await expect(unitSelect.locator('.el-select__placeholder')).toContainText('件')
  255 |   await page.screenshot({ path: resolve(OUTPUT, 'product-unit-linkage.png'), fullPage: true })
  256 | })
  257 | 
  258 | test('未登录和错误角色不能进入其他业务端页面', async ({ browser }) => {
  259 |   const anonymous = await browser.newPage()
  260 |   await anonymous.goto('/operation/products')
  261 |   await expect(anonymous).toHaveURL(/\/login$/)
  262 |   await anonymous.close()
  263 | 
  264 |   const context = await browser.newContext()
  265 |   const page = await context.newPage()
  266 |   await login(page, 'client')
  267 |   await page.goto('/operation/products')
  268 |   await expect(page).toHaveURL(/\/client\/dashboard$/)
  269 |   await context.close()
  270 | })
  271 | 
  272 | test('商品列表空数据与加载失败均不应白屏', async ({ page }) => {
  273 |   mkdirSync(OUTPUT, { recursive: true })
  274 |   await login(page, 'operation')
  275 | 
  276 |   await page.route('**/api/operation/products**', async (route) => {
  277 |     await route.fulfill({
  278 |       status: 200,
  279 |       contentType: 'application/json',
  280 |       body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
  281 |     })
  282 |   })
  283 |   await page.goto('/operation/products')
  284 |   await expect(page.getByRole('button', { name: '新增商品' })).toBeVisible()
  285 |   expect((await page.locator('body').innerText()).trim().length).toBeGreaterThan(20)
  286 |   await page.unroute('**/api/operation/products**')
  287 | 
  288 |   const pageErrors: string[] = []
  289 |   page.on('pageerror', (error) => pageErrors.push(error.message))
  290 |   await page.route('**/api/operation/products**', async (route) => {
  291 |     await route.fulfill({
  292 |       status: 500,
  293 |       contentType: 'application/json',
  294 |       body: JSON.stringify({ detail: 'QA forced failure' }),
  295 |     })
  296 |   })
  297 |   await page.reload({ waitUntil: 'domcontentloaded' })
  298 |   await expect(page.getByRole('button', { name: '新增商品' })).toBeVisible()
  299 |   await expect(page.locator('.el-message', { hasText: 'QA forced failure' })).toBeVisible()
  300 |   await page.waitForTimeout(500)
  301 |   writeFileSync(
  302 |     resolve(OUTPUT, 'products-load-failure.json'),
  303 |     JSON.stringify({ pageErrors }, null, 2),
  304 |     'utf8',
  305 |   )
> 306 |   expect(pageErrors).toEqual([])
      |                      ^ Error: expect(received).toEqual(expected) // deep equality
  307 | })
  308 | 
```