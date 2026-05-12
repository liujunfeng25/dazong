import { defineConfig } from '@playwright/test'

/**
 * E2E 依赖本机已启动：`docker compose up -d`（前端 :80、后端 :8000）。
 * 演示订单：`docker compose exec backend python scripts/reset_orders_tomorrow_demo.py`
 *
 * 电子围栏含高德地图：在 **Docker 内** 跑 Playwright 时建议设置
 * `PLAYWRIGHT_TEST_BASE_URL=http://host.docker.internal:80`；地图常因 Key 域名白名单被跳过，
 * 真绘制验证请在宿主机用 **Node 20+** 执行 `npm run test:e2e:fence`（baseURL 默认 http://127.0.0.1）。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  use: {
    /** 本机直接跑用默认；在 Docker 内跑 E2E 时设为 `http://host.docker.internal:80` */
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL || 'http://127.0.0.1',
    viewport: { width: 1440, height: 900 },
    trace: 'on-first-retry',
  },
})
