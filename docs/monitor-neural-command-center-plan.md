# 监管端 Neural Command Center 重构进度

## 目标

将现有 `/monitor/dashboard` 重构为 Stitch 风格的深色 AI 指挥中心，并保留天枢大屏作为监管端侧栏模块之一。监管端侧栏固定为六个模块：核心态势、天枢大屏、指挥广播、履约监控、数据智能挖掘、AI 核心对话。

## 模块职责与数据口径

| 模块 | 页面职责 | 主要数据源 | 空态 | 验收标准 |
| --- | --- | --- | --- | --- |
| 核心态势 | 总览 KPI、订单生命周期、风险事件、最近订单 | `/api/monitor/neural/overview`、实时 WS | 展示 0 值和“暂无事件” | `/monitor/dashboard` 默认进入，KPI、趋势、事件流不白屏 |
| 天枢大屏 | 保留原天枢沉浸式大屏 | `/monitor/tianshu` iframe、`/api/insights/business/*` | iframe 仍可显示原空态 | 侧栏切入/切出不破坏原大屏 |
| 指挥广播 | 今日指令、风险频道、调度建议 | `/api/monitor/neural/overview` | 展示默认指挥频道 | 能看到订单、预警、账务、质检类频道 |
| 履约监控 | 车辆、配送、IoT、温湿度、异常链路 | `/api/monitor/neural/logistics` | 展示无车辆/无设备状态 | 配送和设备指标来自真实表 |
| 数据智能挖掘 | 区域、品类、商品、客户、退货、价差、预测预警 | `/api/monitor/neural/mining`、`/api/xinfadi/*` | 展示待采集/待训练 | 可查看价差与单品预测接口返回 |
| AI 核心对话 | 监管助手、工具调用、报告导出 | `/api/chat`、`/api/chat/stream`、`/api/chat/report/export` | 无模型 key 时本地规则兜底 | 可回答 KPI、排行、预测、报告类问题 |

## 接口清单

- `GET /api/monitor/neural/overview`：核心态势 KPI、订单生命周期、风险计数、今日事件流。
- `GET /api/monitor/neural/logistics`：车辆、路线、IoT 设备、温湿度、配送异常、容量/时效指标。
- `GET /api/monitor/neural/mining`：区域、品类、商品、客户、退货、价差、预测预警聚合。
- `GET /api/insights/business/category-distribution`：天枢/机器人品类聚合。
- `GET /api/insights/business/backorder-daily`：退货/补货趋势。
- `GET /api/insights/business/orders-calendar-heatmap`：订单日历热力。
- `GET /api/insights/business/order-head`：订单头信息。
- `GET /api/insights/business/meta/tables`：可用表和字段元信息。
- `GET /api/insights/business/xinfadi-summary-series`：价格行情摘要序列。
- `GET /api/xinfadi/*`：爬虫、补抓、行情分析、训练状态、预测总览、单品预测。
- `POST /api/chat`、`POST /api/chat/stream`、`POST /api/chat/report/export`：对话、流式对话、报告导出。

## 分阶段进度

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| Phase 0 文档与口径冻结 | Done | 已创建本文档并固定模块、接口、空态、验收标准。 |
| Phase 1 监管布局改造 | Done | `/monitor/dashboard` 已按 Stitch 源设计重建为 6 模块 Neural Command Center；天枢作为侧栏模块复用原组件承载。 |
| Phase 2 后端数据底座 | Done | 已新增 `/monitor/neural/*`，并补齐机器人/天枢缺失的洞察接口。 |
| Phase 3 核心态势/指挥/履约 UI | Done | 已完成核心 KPI、生命周期、趋势、事件流、指挥频道、车辆、IoT、异常展示。 |
| Phase 4 数据智能挖掘中心 | Partial | 已迁入新发地同构表、行情接口、补抓/进度接口、轻量预测与训练状态接口；已导入 ai-agent 历史行情样本，完整 Prophet/LSTM/XGBoost 模型文件流水线后续继续增强。 |
| Phase 5 AI 核心对话 | Partial | 已接入 ai-agent DashScope key、OpenAI 兼容 Function Calling、监管工具、报告导出和无 key/调用失败兜底；需继续补迁 ai-agent 原回归集。 |
| Phase 6 联调验收 | Partial | 已完成后端语法、路由挂载 smoke、前端 production build；Playwright 截图和真实登录态接口回归待补。 |

## 本轮完成记录

- 创建本文档。
- 后端新增 `backend/routers/xinfadi.py`、`backend/routers/chat.py`。
- 后端扩展 `backend/routers/monitor.py`：`/api/monitor/neural/overview`、`/api/monitor/neural/logistics`、`/api/monitor/neural/mining`。
- 后端扩展 `backend/routers/tianshu_insights.py`：品类分布、退货趋势、日历热力、订单头、表元信息、行情摘要序列。
- 前端新增 `frontend/src/api/chat.js`，扩展 `frontend/src/api/monitor.js`。
- 前端重构 `frontend/src/views/monitor/Dashboard.vue` 为 Stitch 风格 6 模块监管中心。
- 修正视觉基准：已读取 Stitch 项目 `3160891468617554770`、screen `d3d059da5d1e4937bec9718950d1deb5` 的源设计结构与 token，按 `#00e5ff` 主色、Space Grotesk / Inter / JetBrains Mono、8px glass panel、80px topbar、左侧模块导航重建监管端，不再按截图静态仿写。
- 修正天枢模块：`Dashboard.vue` 复用 `TianshuBigScreen.vue` 嵌入天枢，`TianshuBigScreen.vue` 新增 `embedded` 模式；保留 `/monitor/tianshu` 独立路由和 iframe `postMessage` 全屏逻辑。
- 稳定性补强：`loadAll` 改为分区 `Promise.allSettled`，核心态势、履约监控、数据智能挖掘接口失败时只显示对应模块空态，不拖垮整个监管端初始化。
- 导入用户提供的 Stitch 导出包 `/Users/Admin/Downloads/stitch_advanced_ai_neural_architecture.zip`，静态资产落位到 `frontend/public/stitch/advanced-ai-neural-architecture/`；监管端 5 个非天枢模块先按 `code.html` 视觉源直接承载：`ai_1` 对应核心态势、`_1` 对应履约监控、`_2` 对应指挥广播、`_3` 对应数据智能挖掘、`ai_2` 对应 AI 核心对话。
- `/monitor/dashboard` 已改为 Stitch 页面宿主，底部半透明模块切换器负责 6 个模块切换；天枢大屏仍走原 Vue 组件，不改写天枢本体。
- 按最新标注调整导航位置：已取消底部模块切换器，把 6 个模块直接放入 Stitch 左侧 96px 轨道区域，和源 HTML 的左栏视觉位置一致；窄屏下保留底部横向降级。
- 已开始替换 5 个 Stitch HTML 中的静态数字：核心态势接入履约完成率、订单链路、今日 GMV、开放预警；履约监控接入车辆、IoT、配送任务、到达率、异常、运力吨位；指挥广播接入指挥频道、最新预警和待处理预警；数据智能挖掘接入商品数、报价数、映射数、高价差商品、最高报价和价差率；AI 核心对话接入监管脱敏上下文和业务指标入口文案。
- 接入 ai-agent AI 配置：从本机 ai-agent `.env` 同步 `AI_API_KEY`、`AI_BASE_URL`、`AI_MODEL_PLANNER`、`AI_MODEL_ANSWER` 到 `backend/.env`，密钥不写代码、不写本文档。
- 新增 dazong MySQL 新发地同构表：`xinfadi_price_crawl`、`xinfadi_forecast_jobs`、`xinfadi_forecast_models`、`xinfadi_forecast_metrics`。
- 新发地历史行情：已从本机 `agent-mysql` 导入 51,165 行行情样本，覆盖 `2025-06-06` 至 `2026-04-22`；导入后已修复可逆 UTF-8/latin1 双重编码，`白菜` 可命中 `大白菜/小白菜/圆白菜/奶白菜` 等品名。
- AI 核心对话：`/api/chat` 支持 DashScope OpenAI 兼容调用、Function Calling 工具、自然语言商品关键词提取、新发地行情/预测工具和报告导出。
- 数据库稳定性修复：导入过程中发现旧演示 `iot_data` InnoDB 页异常会拖垮 MySQL；已停后端后重建 `iot_data` 表，后端重启时由 SQLAlchemy 幂等创建，避免监管履约接口继续触发崩溃。

## 验证记录

- `python3 -m py_compile backend/routers/monitor.py backend/routers/tianshu_insights.py backend/routers/xinfadi.py backend/routers/chat.py backend/main.py`：通过。
- FastAPI 路由挂载 smoke：`/api/monitor/neural/overview`、`/api/monitor/neural/logistics`、`/api/monitor/neural/mining`、`/api/insights/business/category-distribution`、`/api/xinfadi/predict`、`/api/chat` 均已挂载。
- 浏览器检查：`http://localhost:5173/monitor/dashboard` 可登录进入，核心态势、天枢大屏、数据智能挖掘、AI 核心对话侧栏模块可切换。
- Stitch/天枢修正验收：`/monitor/dashboard` 已显示 Stitch 源设计风格的顶栏、侧栏、glass panel 与霓虹主色；侧栏“天枢大屏”可见原天枢内容，点击“独立打开”进入 `/monitor/tianshu` 正常显示。
- Stitch zip 验收：Docker `http://127.0.0.1/monitor/dashboard` 可显示导出包中的“神经核心”页面；切换“履约监控”可显示导出包中的“多维算力监控面板”；切换“天枢大屏”可显示原天枢大屏。
- 左侧轨道导航验收：Docker `http://127.0.0.1/monitor/dashboard` 已显示 CORE、TS、CMD、LOG、MINE、AI 纵向模块按钮，位置覆盖 Stitch 源设计左侧模块区，不再占用底部主内容区。
- Stitch 静态数据替换验收：浏览器逐页检查 CORE、CMD、LOG、MINE、AI，已看到真实业务值注入，例如核心态势 `履约完成率 33.3%`、`订单链路 457单`、`开放预警 80`，履约监控 `车辆到达率 84.9%`、`车辆 16`、`设备 19`、`配送任务 179单`，数据智能挖掘 `2,788 条报价`、`商品 2,041 / 映射 2,041`。
- 天枢模块验收：从左侧 `TS` 模块进入后，原天枢大屏组件可完整加载，顶部“独立打开”入口保留。
- 本地登录态接口 smoke：`/api/monitor/neural/overview`、`/api/monitor/neural/logistics`、`/api/monitor/neural/mining`、`/api/xinfadi/predict/overview`、`/api/chat` 均返回 200。
- Docker 重建：`docker compose up -d --build --force-recreate backend frontend` 已执行；当前 `backend`、`frontend`、`mysql` 均为 Up。
- `npm --prefix frontend run build`：通过；仅有既有 Sass deprecated、UnoCSS 默认配置和 chunk size 警告。
- `PYTHONPATH=backend python3 -m pytest backend/tests -q`：7 passed，1 failed；失败项为集成测试连接本机 MySQL 时 `Access denied for user 'root'`，属于当前测试数据库凭据/网络环境问题。
- 新发地表 smoke：4 张 `xinfadi_*` 表存在，`xinfadi_price_crawl` 已有历史行情样本。
- AI 配置 smoke：后端容器可读到 `AI_API_KEY`，接口响应和日志不输出密钥。
- 2026-05-12 收尾 smoke：登录 `monitor001/demo123` 后，`/api/monitor/neural/overview`、`/logistics`、`/mining`、`/api/xinfadi/analytics/products`、`/api/xinfadi/predict?product_name=白菜&days=7`、`/api/chat/catalog`、`/api/chat` 均返回 200；`/monitor/dashboard` 返回 200。
- DashScope 连通性 smoke：`AI_API_KEY` 已配置且容器可读取，但当前本机/容器访问 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` 返回 `ConnectTimeout`，因此 `/api/chat` 按设计降级到本地工具调用，并在 `debug.provider_error` 返回 `ConnectTimeout('')`。

## 当前遗留问题

- 当前网络访问 `www.xinfadi.com.cn` 偶发超时；监管端优先使用已导入的 ai-agent 历史行情样本，联网恢复后 `/api/xinfadi/crawl` 可继续补抓。
- 新发地预测当前为轻量时间序列兜底，接口会返回 `fallback=true`；完整 Prophet/LSTM/XGBoost 模型文件持久化后续继续增强。
- AI 对话已实际接入 DashScope key，但模型侧网络或供应商异常时会自动降级到本地规则工具调用。
