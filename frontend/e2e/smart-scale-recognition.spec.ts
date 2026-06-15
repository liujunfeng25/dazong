import { expect, test, type Page, type Route } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const SAMPLE_IMAGE =
  'data:image/svg+xml;charset=utf-8,' +
  encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="640" height="480">
      <rect width="640" height="480" fill="#eef2ff"/>
      <rect x="80" y="300" width="480" height="95" rx="18" fill="#94a3b8"/>
      <circle cx="225" cy="235" r="72" fill="#d9b36c"/>
      <circle cx="330" cy="215" r="78" fill="#c99a4f"/>
      <circle cx="430" cy="250" r="68" fill="#e2bd78"/>
    </svg>
  `)

const categories = [
  {
    id: 1,
    name: '土豆',
    product_id: 101,
    product_name: '土豆',
    sample_count: 32,
    total_sample_count: 40,
    review_counts: { approved: 32, pending: 5, needs_attention: 2, rejected: 1 },
    status: 'active',
    source: 'receiving',
  },
  {
    id: 2,
    name: '红薯',
    product_id: 102,
    product_name: '红薯',
    sample_count: 18,
    total_sample_count: 21,
    review_counts: { approved: 18, pending: 3 },
    status: 'active',
    source: 'manual',
  },
  {
    id: 3,
    name: '洋葱',
    product_id: 103,
    product_name: '洋葱',
    sample_count: 6,
    total_sample_count: 7,
    review_counts: { approved: 6, pending: 1 },
    status: 'active',
    source: 'manual',
  },
]

const samples = Array.from({ length: 12 }, (_, index) => ({
  id: index + 1,
  category_id: 1,
  image_url: SAMPLE_IMAGE,
  original_image_url: SAMPLE_IMAGE,
  cropped_image_url: SAMPLE_IMAGE,
  source: index < 8 ? 'receiving' : 'manual',
  angle: index < 5 ? '收货' : '手动',
  quality: 1,
  quality_status: index === 11 ? 'failed' : 'passed',
  quality_reason: index === 11 ? '画面疑似模糊' : null,
  review_status: index < 8 ? 'approved' : index < 10 ? 'pending' : index === 10 ? 'rejected' : 'needs_attention',
  device_id: index < 8 ? 'scale-camera-01' : null,
  roi_version: index < 8 ? 3 : null,
  roi_override: index >= 8 ? { x: 0.2, y: 0.2, width: 0.6, height: 0.6 } : null,
  created_at: '2026-06-10T08:00:00',
}))

const device = {
  device_id: 'scale-camera-01',
  device_name: '首衡智能秤',
  latest_image_url: SAMPLE_IMAGE,
  latest_photo_at: '2026-06-10T08:00:00Z',
  roi_profile: {
    id: 3,
    device_id: 'scale-camera-01',
    device_name: '首衡智能秤',
    version: 3,
    x: 0.24,
    y: 0.18,
    width: 0.5,
    height: 0.58,
    rotation: 0,
    status: 'active',
  },
}

const deployedModel = {
  task_id: 41,
  version: '20260525005846',
  status: 'done',
  is_deployed: true,
  epochs: 10,
  batch_size: 16,
  classes: [
    { category_id: 1, product_id: 101, product_name: '土豆', sample_count: 32 },
    { category_id: 2, product_id: 102, product_name: '红薯', sample_count: 18 },
  ],
  metrics: { train_acc: 1, val_acc: 1, loss: 0.02 },
  created_at: '2026-05-25T00:58:46',
}

const runningModel = {
  task_id: 44,
  version: '20260610143000',
  status: 'running',
  is_deployed: false,
  epochs: 10,
  batch_size: 16,
  classes: deployedModel.classes,
  metrics: null,
  progress: {
    status: 'running',
    epoch: 7,
    total_epochs: 10,
    train_acc: 0.946,
    val_acc: 0.921,
    loss: 0.184,
    message: '正在训练 Epoch 7 / 10',
  },
  created_at: '2026-06-10T14:30:00',
}

const deployableModel = {
  ...deployedModel,
  task_id: 42,
  version: '20260609120000',
  is_deployed: false,
  metrics: { train_acc: 0.97, val_acc: 0.932, loss: 0.11 },
  created_at: '2026-06-09T12:00:00',
}

type MockState = {
  models: Array<Record<string, unknown>>
  trainStatus: Record<string, unknown>
  trainStatusRequests: number
  samples: Array<Record<string, unknown>>
  roiProfiles: Array<Record<string, unknown>>
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

async function installMockApi(page: Page, state: MockState) {
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()

    if (path === '/api/auth/login' && method === 'POST') {
      return json(route, {
        token: 'smart-scale-test-token',
        role: 'operation',
        company_name: '测试运营中心',
      })
    }
    if (path === '/api/auth/me' && method === 'GET') {
      return json(route, {
        id: 99,
        username: 'operation-test',
        role: 'operation',
        company_name: '测试运营中心',
        status: 'active',
        address: '',
        lng: null,
        lat: null,
        canteen_id: null,
        canteen_name: null,
      })
    }
    if (path === '/api/notifications' && method === 'GET') {
      return json(route, [])
    }
    if (path === '/api/smart-scale-recognition/categories' && method === 'GET') {
      return json(route, { items: categories })
    }
    if (path === '/api/smart-scale-recognition/categories/1/samples' && method === 'GET') {
      return json(route, { items: state.samples })
    }
    if (/\/api\/smart-scale-recognition\/categories\/\d+\/samples$/.test(path) && method === 'GET') {
      return json(route, { items: [] })
    }
    if (path === '/api/operation/products' && method === 'GET') {
      return json(route, {
        items: categories.map((category) => ({ id: category.product_id, name: category.product_name })),
        total: categories.length,
      })
    }
    if (path === '/api/smart-scale-recognition/models' && method === 'GET') {
      return json(route, { items: state.models })
    }
    if (path === '/api/smart-scale-recognition/devices' && method === 'GET') {
      return json(route, { items: [{ ...device, roi_profile: state.roiProfiles.at(-1) || device.roi_profile }] })
    }
    if (path === '/api/smart-scale-recognition/roi-profiles' && method === 'GET') {
      return json(route, { items: state.roiProfiles })
    }
    if (path === '/api/smart-scale-recognition/roi-profiles' && method === 'POST') {
      const payload = request.postDataJSON()
      state.roiProfiles = state.roiProfiles.map((profile) => ({ ...profile, status: 'archived' }))
      const nextVersion =
        Math.max(0, ...state.roiProfiles.map((profile) => Number(profile.version || 0))) + 1
      const created = {
        id: nextVersion,
        ...payload,
        version: nextVersion,
        status: 'active',
      }
      state.roiProfiles.push(created)
      return json(route, created)
    }
    if (path === '/api/smart-scale-recognition/samples/review' && method === 'POST') {
      const payload = request.postDataJSON()
      state.samples = state.samples.map((sample) =>
        payload.sample_ids.includes(sample.id)
          ? { ...sample, review_status: payload.status, rejection_reason: payload.rejection_reason }
          : sample,
      )
      return json(route, { updated: payload.sample_ids.length, status: payload.status })
    }
    if (path === '/api/smart-scale-recognition/samples/recrop' && method === 'POST') {
      const payload = request.postDataJSON()
      state.samples = state.samples.map((sample) =>
        payload.sample_ids.includes(sample.id)
          ? {
              ...sample,
              review_status: 'pending',
              quality_status: 'passed',
              device_id: payload.device_id || sample.device_id,
              cropped_image_url: SAMPLE_IMAGE,
            }
          : sample,
      )
      return json(route, { updated: payload.sample_ids.length })
    }
    if (path === '/api/smart-scale-recognition/categories/1/samples' && method === 'POST') {
      return json(route, { id: 99, review_status: 'pending', quality_status: 'passed' })
    }
    if (path === '/api/smart-scale-recognition/train/44' && method === 'GET') {
      state.trainStatusRequests += 1
      return json(route, state.trainStatus)
    }
    if (path === '/api/smart-scale-recognition/train/44/cancel' && method === 'POST') {
      state.models = state.models.map((model) =>
        model.task_id === 44 ? { ...model, status: 'cancelled', progress: null } : model,
      )
      state.trainStatus = { ...state.trainStatus, status: 'cancelled' }
      return json(route, { message: 'ok', status: 'cancelled' })
    }
    if (path === '/api/smart-scale-recognition/import-receiving' && method === 'POST') {
      return json(route, {
        imported: 12,
        skipped: 3,
        by_product: [
          { product_id: 101, product_name: '土豆', count: 7 },
          { product_id: 102, product_name: '红薯', count: 5 },
        ],
      })
    }
    if (path === '/api/smart-scale-recognition/models/42/deploy' && method === 'POST') {
      state.models = state.models.map((model) => ({
        ...model,
        is_deployed: model.task_id === 42,
      }))
      return json(route, { message: 'ok', task_id: 42, version: '20260609120000' })
    }
    if (path === '/api/smart-scale-recognition/recognize' && method === 'POST') {
      return json(route, {
        model_version: '20260525005846',
        results: [
          { category_id: 1, category_name: '土豆', product_id: 101, product_name: '土豆', score: 0.94 },
          { category_id: 2, category_name: '红薯', product_id: 102, product_name: '红薯', score: 0.03 },
          { category_id: 3, category_name: '胡萝卜', product_id: 103, product_name: '胡萝卜', score: 0.015 },
          { category_id: 4, category_name: '洋葱', product_id: 104, product_name: '洋葱', score: 0.01 },
          { category_id: 5, category_name: '生姜', product_id: 105, product_name: '生姜', score: 0.005 },
        ],
      })
    }

    return json(route, { message: 'ok' })
  })
}

test.use({ viewport: { width: 1440, height: 1024 }, video: 'off' })

test('智能秤训练工作台覆盖三页签和关键状态', async ({ page }) => {
  const qaDir = '/tmp/dazong-smart-scale-roi-qa'
  mkdirSync(qaDir, { recursive: true })
  const state: MockState = {
    models: [runningModel, deployedModel, deployableModel],
    trainStatus: {
      ...runningModel,
      progress: runningModel.progress,
    },
    trainStatusRequests: 0,
    samples: samples.map((sample) => ({ ...sample })),
    roiProfiles: [{ ...device.roi_profile }],
  }
  await installMockApi(page, state)

  await page.goto('/login')
  await page.getByPlaceholder('用户名 / 手机号 / ID').fill('operation-test')
  await page.getByPlaceholder('请输入登录密码').fill('demo123')
  await page.getByRole('button', { name: /立即登录/ }).click()
  await page.waitForURL('**/operation/dashboard')
  await page.goto('/operation/smart-scale-recognition')
  await expect(page.getByRole('heading', { name: '智能秤识别训练' })).toBeVisible()
  await expect(page.locator('.deployment-head strong')).toHaveText('20260525005846')
  await expect(page.locator('.overview-item').filter({ hasText: '类目总数' }).getByText('3', { exact: true })).toBeVisible()

  await page.getByText('土豆', { exact: true }).first().click()
  await expect(page.getByText('32 / 40 已批准')).toBeVisible()
  await expect(page.locator('.sample-card')).toHaveCount(12)
  await expect(page.getByText('来自收货').first()).toBeVisible()
  await page.screenshot({ path: `${qaDir}/catalog-1440x1024.png`, fullPage: true })

  await page.getByRole('button', { name: '待审核' }).click()
  await expect(page.locator('.sample-card')).toHaveCount(2)
  await page.getByRole('button', { name: '全部' }).click()

  await page.locator('.sample-card').nth(8).locator('.el-checkbox').click()
  await page.getByRole('button', { name: '批准', exact: true }).click()
  await expect(page.getByText('已选择 1 张')).toHaveCount(0)

  await page.getByRole('button', { name: '补导历史收货照片' }).first().click()
  const importDialog = page.getByRole('dialog', { name: '补导历史收货照片' })
  await expect(importDialog).toBeVisible()
  await page.getByRole('button', { name: '开始导入' }).click()
  await expect(page.getByText('新增 12 张，跳过 3 张')).toBeVisible()
  await importDialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(importDialog).toBeHidden()

  await page.getByRole('button', { name: '首衡 ROI' }).click()
  const roiDialog = page.getByRole('dialog', { name: '首衡固定机位 ROI' })
  await expect(roiDialog).toBeVisible()
  const roiPanel = roiDialog.locator('.el-dialog')
  await expect
    .poll(() => roiPanel.evaluate((element) => getComputedStyle(element).backgroundColor))
    .toBe('rgb(255, 255, 255)')
  await expect
    .poll(() =>
      roiDialog.evaluate((element) => getComputedStyle(element.parentElement as Element).opacity),
    )
    .toBe('1')
  await expect(roiDialog.getByText('ROI v3', { exact: true })).toBeVisible()
  await expect(roiDialog.getByText('2026/06/10 16:00:00', { exact: true })).toBeVisible()
  await expect(roiDialog.getByText('首衡智能秤', { exact: true })).toBeVisible()
  await expect(roiDialog.locator('.roi-frame')).toBeVisible()
  await page.screenshot({ path: `${qaDir}/roi-dialog-1440x1024.png`, fullPage: true })
  await roiDialog.getByRole('button', { name: '保存为新版本' }).click()
  await expect(roiDialog.getByText('v4 · 当前')).toBeVisible()
  await roiDialog.getByRole('button', { name: '关闭', exact: true }).click()

  const manualInput = page.locator('.sample-actions input[type="file"]')
  await manualInput.setInputFiles({
    name: 'manual.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2f14AAAAASUVORK5CYII=',
      'base64',
    ),
  })
  await expect(page.getByRole('dialog', { name: '补录训练素材' })).toBeVisible()
  await expect(page.getByText('自动继承首衡固定机位 ROI，可针对本图微调')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()

  await page.getByRole('tab', { name: /训练与模型/ }).click()
  await expect(page.getByText('Epoch 7 / 10', { exact: true })).toBeVisible()
  await expect(page.getByText('92.1%', { exact: true })).toBeVisible()
  await expect(page.getByText('0.184', { exact: true })).toBeVisible()
  await page.screenshot({ path: `${qaDir}/train-1440x1024.png`, fullPage: true })

  await page.getByRole('button', { name: '部署', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '部署模型' })).toBeVisible()
  await page.getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('20260609120000', { exact: true }).first()).toBeVisible()

  await page.getByRole('tab', { name: /识别测试/ }).click()
  const recognitionInput = page.locator('.recognition-image-panel input[type="file"]')
  await expect(recognitionInput).toHaveCount(1)
  await recognitionInput.setInputFiles({
    name: 'potato.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2f14AAAAASUVORK5CYII=',
      'base64',
    ),
  })
  const topCandidate = page.locator('.candidate-row.is-top')
  await expect(topCandidate.locator('.candidate-copy strong')).toHaveText('土豆')
  await expect(topCandidate.getByText('94%', { exact: true })).toBeVisible()
  await expect(topCandidate.getByText('高置信度', { exact: true })).toBeVisible()
  await page.screenshot({ path: `${qaDir}/recognize-1440x1024.png`, fullPage: true })

  await page.goto('/docs')
  const pollingCountAfterUnmount = state.trainStatusRequests
  await page.waitForTimeout(2300)
  expect(state.trainStatusRequests).toBe(pollingCountAfterUnmount)

  state.models = [deployableModel]
  await page.goto('/operation/smart-scale-recognition')
  await page.getByRole('tab', { name: /识别测试/ }).click()
  await expect(page.getByText('尚未部署识别模型')).toBeVisible()

  await page.setViewportSize({ width: 1280, height: 720 })
  await expect(page.locator('.ssr-page')).toBeVisible()
  let overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
  await page.screenshot({ path: `${qaDir}/no-model-1280x720.png`, fullPage: true })

  await page.setViewportSize({ width: 820, height: 900 })
  await expect(page.locator('.ssr-page')).toBeVisible()
  overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
  await page.screenshot({ path: `${qaDir}/no-model-820x900.png`, fullPage: true })
})
