# 大宗物资供应链全链路管理系统（阶段四）

本项目已覆盖六端业务闭环、监管驾驶舱实时监控、OCR/语音辅助下单、智能分单与路线规划（Mock）以及一键容器化部署。

## 1. 生产部署（Docker Compose）

执行：

```bash
docker compose up --build
```

访问地址：
- 前端：<http://localhost>
- 后端 API 文档：<http://localhost:8000/docs>
- MySQL：`127.0.0.1:3306`

重置并重建：

```bash
docker compose down
docker compose up --build
```

## 2. 演示账号

统一密码：`demo123`

- `client001`～`client006`（client，演示多采购方）
- `supplier001`～`supplier003`（supplier，演示多供货方，均绑定同一配送商 `delivery001`）
- `delivery001`（delivery）
- `factory001`（factory）
- `operation001`（operation）
- `monitor001`（monitor）

## 3. 关键功能清单

- 六端可独立登录并操作。
- 订单主线：下单 -> 分拣 -> 发货 -> 配送 -> 收货 -> 结算。
- 合约招标流程完整（发标、投标、中标、合约）。
- 异常商品自动校验并生成工单。
- 收货自动生成账单。
- 监管端驾驶舱支持 WebSocket 实时更新与演示控制台。
- `POST /api/demo/reset` 支持演示数据一键重置。
- 独立「演示数据 API 控制台」见仓库 [`demo-console/`](demo-console/) 与下文 **4.5**。

## 4. 第四阶段新增能力

### 4.1 OCR 下单（百度表格 / 演示）
- `GET /api/ocr/engine`：当前引擎、是否已配置百度 Key、是否使用演示数据。
- `POST /api/ocr/parse-order`：请求 `multipart/form-data` 图片文件。
- 若配置 **百度表格识别**（与 ai-agent 一致：`https://aip.baidubce.com/rest/2.0/ocr/v1/table`），返回表格结构化结果 `structured`，解析品名/数量/单位行，并与商品库做子串匹配；未匹配、多匹配时在响应 `warnings` / `match_summary` 中说明，客户端弹窗展示表格并引导在购物车中处理。
- 未配置 Key 或 `OCR_ENGINE=mock` 时返回固定示例表（可演示流程）。
- 环境变量（任选其一的 Key 名即可）：`BAIDU_TABLE_API_KEY` 或 `DOCUMENTS_BAIDU_TABLE_API_KEY`；`OCR_ENGINE` 或 `DOCUMENTS_OCR_ENGINE` 为 `auto`（有 Key 走百度否则 mock）/`baidu`/`mock`。
- 客户端下单页支持「上传采购单」：识别结果弹窗 + 购物车匹配状态标签。

### 4.2 语音下单（规则解析）
- `POST /api/voice/parse-order`
- 请求：`{ "text": "我要订100斤大白菜和50斤西红柿" }`
- 后端使用正则解析数量、单位、品名，并做商品名称模糊匹配。
- 下单页支持输入“语音转文字”内容并自动填充。

### 4.3 智能分单（配送端）
- `POST /api/delivery/smart-split`
- 请求：`{ "order_ids": [1,2,3] }`
- 规则（Mock）：蔬菜优先 `supplier001`，司机随机分配。
- 页面：`/delivery/smart-split`

### 4.4 智能物流规划（配送端）
- `POST /api/delivery/route-plan`
- 请求：`{ "driver_id": 3, "order_ids": [1,2] }`
- 返回：司机、总里程、预计时长、停靠顺序。
- 页面：`/delivery/route-plan`

### 4.5 演示数据 API 控制台（独立 H5）
- 目录：[`demo-console/`](demo-console/)：本地开发 **http://127.0.0.1:15175**；**Docker** 与主站同端口 **http://127.0.0.1/demo-console/**（详见 [`demo-console/README.md`](demo-console/README.md)）。
- 多采购账号串行登录；每个账号需 `GET /client/canteens` → `POST /client/canteen-session` 换取带 `canteen_id` 的 JWT 后再做合约与配送日校验、`orders/meta` 预览、按商品搜索批量 `POST /orders`（单配送商 + 多账号；多供货商体现在分单/行级 `supplier_id`）。
- 在 **`DEMO_MODE=true`** 且使用 **`monitor`** 账号时，可调用：
  - `POST /api/demo/orders/delete`：`{ "order_ids": [...] }` 级联删单；
  - `POST /api/demo/orders/mark-allocations-shipped`：将订单下全部分单行标为 **已出库**；
  - `POST /api/demo/orders/supplier-ship-bulk`：按供货商对指定订单的分单行 **一键发货（已出库）**（演示跳过打印门禁）。
- 直连后端时的 CORS：默认已包含 `http://127.0.0.1:15175` 等来源，生产请在环境变量中扩展 `CORS_ORIGINS`。

## 5. 演示顺序建议

1. 运营端检查分类、商品、账号。
2. 客户端通过 OCR 或语音辅助创建订单。
3. 供货商完成配货、打印、发货。
4. 配送商执行取货、智能分单、路线规划、送达。
5. 客户端收货、评价、结算。
6. 监管端查看驾驶舱、预警与实时物流变化。
7. 使用演示控制台触发模拟动作，必要时调用 `/api/demo/reset`。

## 6. 环境变量说明（容器）

`docker-compose.yml` 中已包含：

- 数据库：`DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` 及 `MYSQL_*`
- 鉴权：`JWT_SECRET`、`JWT_SECRET_KEY`
- 演示模式：`DEMO_MODE=true`
- OCR（可选）：`BAIDU_TABLE_API_KEY` 或 `DOCUMENTS_BAIDU_TABLE_API_KEY`；`OCR_ENGINE` 或 `DOCUMENTS_OCR_ENGINE`（`auto` / `baidu` / `mock`）

## 7. 部署结构

- `mysql:8.0`：持久化目录 `./mysql_data`。
- `backend`：`python:3.11-slim` 多阶段构建，`uvicorn` 生产启动。
- `frontend`：`node:20-alpine` 构建，`nginx:alpine` 运行。
- Nginx 规则：
  - `/` 静态资源并支持 Vue Router history（`try_files`）
  - `/api` 代理到 `backend:8000`
  - `/ws` 代理到 `backend:8000`（支持 WebSocket Upgrade）

## 8. 生产化改造新增项

- 订单域增强：状态机校验、幂等键支持、状态变更日志与审计日志。
- WebSocket 鉴权：`/ws/*` 连接需携带 `token` 查询参数。
- 安全基线：CORS 支持按环境配置，默认收敛到本地域名列表。
- 系统健康探针：
  - `GET /api/system/healthz`
  - `GET /api/system/readyz`
- 数据库迁移：引入 Alembic（目录：`backend/migrations`）。
- 运维手册：见 `docs/ops-runbook.md`。
- 备份脚本：`scripts/mysql_backup.sh`。
