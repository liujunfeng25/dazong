# Dazong 主前端

六类业务角色共用的 Vue 3 单页应用，并承载监管驾驶舱、天枢大屏、价格分析和前端接口说明。

## 技术栈

- Vue 3、Vue Router、Pinia
- Element Plus
- ECharts、Three.js
- Vite 8
- Playwright

## 本地开发

推荐从仓库根目录启动完整环境：

```bash
make dev-up
```

单独启动前端：

```bash
cd frontend
npm install
npm run dev
```

API 代理目标由 `VITE_API_PROXY_TARGET` 或 Vite 配置决定。

## 构建

```bash
npm run build
```

完整构建会先构建 `tianshu-src`，再构建主前端。只构建主应用：

```bash
npm run build:app
```

## 测试

```bash
npm run test:unit
npm run test:e2e
```

常用专项：

```bash
npm run test:e2e:order
npm run test:e2e:fence
npm run test:e2e:beijing
npm run test:e2e:ai-chat
```

## 路由

- `/operation/*`：运营端
- `/client/*`：采购方
- `/supplier/*`：供货方
- `/delivery/*`：配送商
- `/factory/*`：指定厂家
- `/monitor/*`：监管端
- `/docs`：前端接口说明

业务说明见 [操作手册](../docs/操作手册/README.md)，架构说明见 [系统技术文档](../docs/系统技术文档.md)。
