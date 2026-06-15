# 大宗物资供应链全链路管理系统

本项目面向食堂大宗物资采购与履约场景，覆盖招投标、合约、下单、分单、供货、分检、排线、配送、收货、退货、质检、对账和监管分析。

当前系统由 **六类业务角色和三个 Android 专用终端**组成：

| 类型 | 角色或终端 | 主要职责 |
| --- | --- | --- |
| PC 业务角色 | 采购方 | 选择食堂、招标、下单、收货、投诉、账单 |
| PC 业务角色 | 供货方 | 报价、查看分单、打印标签、出库、质检资料、账单 |
| PC 业务角色 | 配送商 | 供应商、车辆、仓库、智能分单、路线排程、车次、投诉、账单 |
| PC 业务角色 | 指定厂家 | 履约指定厂家商品、提交质检资料、查看账单 |
| PC 业务角色 | 运营方 | 商品、账号、食堂、合约、订单、工单、账期、识别训练 |
| PC 业务角色 | 监管方 | 核心态势、履约、价格、稽核、广播、AI 分析 |
| Android 终端 | 智能秤 | 采购方食堂收货、称重、拍照、退货留痕、双签 |
| Android 终端 | 分检 PDA | 配送商分单标签扫码和分检进度 |
| Android 终端 | 司机端 | 按车辆登录、查看车次、导航和确认送达 |

演示控制台、监管天枢大屏、BI 看板和图像识别工作台是辅助工具或功能模块，不额外计算为业务角色。

## 文档

- [文档中心](docs/README.md)
- [系统技术文档](docs/系统技术文档.md)
- [操作手册](docs/操作手册/README.md)
- [运维手册](docs/ops-runbook.md)
- [系统技术文档 Word 版](docs/系统技术文档.docx)

Markdown 是技术事实的唯一来源，Word 文档由 Markdown 生成。

## 技术栈

- 前端：Vue 3、Vite、Pinia、Element Plus、ECharts、Three.js
- 后端：FastAPI、SQLAlchemy Async、Alembic、MySQL 8
- 对象存储：MinIO
- Android：Kotlin、Jetpack Compose、Retrofit
- 模型与分析：PyTorch、scikit-learn、XGBoost、DashScope
- 运行方式：Docker Compose

仓库中当前没有 Kubernetes、Helm Chart、Deployment 或 Ingress 配置，不能将本项目描述为已使用 K8s 部署。

## 本地启动

要求 Docker Desktop 或兼容的 Docker Engine，并支持 `docker compose`。

```bash
cp .env.example .env
make dev-up
```

默认访问入口：

- 主前端：<http://127.0.0.1>
- 后端 OpenAPI：<http://127.0.0.1:8000/docs>
- 前端接口说明：<http://127.0.0.1/docs>
- 演示控制台：<http://127.0.0.1/demo-console/>
- MinIO 控制台：<http://127.0.0.1:9001>

停止开发环境：

```bash
make dev-down
```

生产 profile：

```bash
make prod-up
```

生产环境必须覆盖数据库密码、JWT 密钥、MinIO 凭据、CORS、公开地址和第三方服务密钥，并关闭演示数据与自动建表能力。

## 核心业务状态

主订单状态由后端状态机控制：

```text
下单 -> 配货 -> 发货 -> 收货 -> 收货确认 -> 已结算
  \-> 取消
```

配送工作台还会根据分单和分检记录派生“待分单、待供货商发货、待分拣、待取货、配送中、待客户收货、待结算、已完成”等操作阶段。派生阶段不是数据库中的另一套订单状态。

## 项目目录

```text
backend/          FastAPI、模型、迁移、服务、测试
frontend/         六角色 PC 前端、监管驾驶舱和天枢源码
demo-console/     开发与演示数据操盘台
docs/             权威技术文档、操作手册和运维手册
scripts/          部署、演示、APK 发布和文档工具
首衡电子秤资料/    第三方设备资料，不属于系统事实文档
```

三个 Android 项目位于同级目录：

```text
/Users/Admin/Project/smart-scale-android
/Users/Admin/Project/sorter-pda-android
/Users/Admin/Project/driver-android
```

## 文档一致性

```bash
make docs-build
make docs-check
```

`docs-build` 由技术 Markdown 生成 Word 并重建操作手册 RAG 索引；`docs-check` 校验文档链接、公开 API、前端路由、RAG 来源和已禁用的旧描述。
