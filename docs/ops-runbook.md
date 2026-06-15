# Dazong 运维手册

> 适用范围：当前 Docker Compose 部署
>
> 最后核验：2026-06-12
> 不适用：Kubernetes、Helm 或云厂商托管集群

## 1. 环境要求

- Docker Engine 和 Docker Compose v2。
- 生产主机应具备独立数据盘、备份空间、域名和 HTTPS 入口。
- 后端镜像使用 Python 3.11；不要以本机旧版 Python 代替容器运行。
- 前端构建使用 Node.js 20。

## 2. 启动与停止

首次初始化：

```bash
cp .env.example .env
```

开发环境：

```bash
make dev-up
docker compose --profile dev ps
```

生产环境：

```bash
make prod-up
docker compose --profile prod ps
```

停止：

```bash
make dev-down
make prod-down
```

不要在未备份的情况下执行带 `-v` 的 `docker compose down`，该操作可能删除持久化卷。

## 3. 健康检查

```bash
curl -fsS http://127.0.0.1:8000/api/system/healthz
curl -fsS http://127.0.0.1:8000/api/system/readyz
```

- `healthz` 判断 API 进程是否存活。
- `readyz` 判断服务是否完成启动并可接收业务请求。
- 每个 HTTP 响应都应包含 `X-Trace-Id`。

容器状态：

```bash
docker compose ps
docker compose logs --tail=200 backend-dev
docker compose logs --tail=200 mysql
docker compose logs --tail=200 minio
```

生产 profile 将后端服务名替换为 `backend-prod`。

## 4. 配置分层

正式环境必须覆盖：

- MySQL 用户、密码和数据库。
- `JWT_SECRET_KEY`。
- MinIO 账号、密码、桶和公开地址。
- `CORS_ORIGINS`。
- AI、OCR、地图、北斗、摄像头、冷链和打印平台密钥。

生产建议：

```text
DEMO_MODE=false
SEED_ON_START=false
SIMULATOR_ENABLED=false
```

`AUTO_CREATE_SCHEMA` 是否开启应由团队迁移策略决定。正式环境推荐使用 Alembic 作为受控结构变更入口。

## 5. 数据库迁移

后端入口脚本会根据部署配置执行初始化。手工迁移前先备份，并确认当前 revision：

```bash
docker compose exec -T backend-dev alembic current
docker compose exec -T backend-dev alembic upgrade head
```

迁移后检查：

```bash
curl -fsS http://127.0.0.1:8000/api/system/readyz
```

当前迁移序列包含调度车次、分检记录、仓库冷链、周期质检、识别训练和 ROI 等结构。禁止跳过中间 revision 直接手工建最终表。

## 6. 备份与恢复

至少备份：

- MySQL 全库。
- MinIO 数据卷或对象桶。
- 后端 `data/` 中的模型、RAG 索引和分析产物。
- 部署环境变量和反向代理配置，密钥应进入受控密钥系统。

示例数据库备份：

```bash
docker compose exec -T mysql sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > dazong-backup.sql
```

恢复应先在隔离环境演练，并核对迁移 revision、订单数量、账单汇总和对象附件。

## 7. 外部服务排障

### 7.1 通用原则

1. 先检查本地 API 是否健康。
2. 再检查容器内 DNS、TLS 和目标域名连通性。
3. 核对 VPN、代理、出口 IP 白名单、账号权限和调用配额。
4. 查看后端日志中的供应商错误和 trace id。
5. 不能把 mock、缓存或直线估算伪装成外部服务真实成功。

### 7.2 常见影响

- 开启 VPN 后，高德、天气、北斗、DashScope 或国内数据源可能超时。
- 新发地连续补抓可能触发 403、429、502、503 或 504，需要慢速模式和退避。
- 萤石直播、精创冷云和快麦打印依赖供应商账号授权。
- 外部服务失败不应阻断无关的订单查看，但依赖该服务的操作必须给出明确失败提示。

## 8. 演示环境

演示接口只应在隔离环境启用：

```text
DEMO_MODE=true
SEED_ON_START=true
```

`/api/demo/*` 包含批量造数、推进履约和清理订单链路等破坏性能力。生产必须关闭，且不允许通过公网开放。

## 9. APK 发布

三个 Android 项目分别构建：

```bash
cd /Users/Admin/Project/smart-scale-android && ./gradlew :app:assembleDebug
cd /Users/Admin/Project/sorter-pda-android && ./gradlew :app:assembleDebug
cd /Users/Admin/Project/driver-android && ./gradlew :app:assembleDebug
```

发布前必须：

- 提升 `versionCode` 和 `versionName`。
- 确认 API 根地址不是临时隧道。
- 确认地图 Key、签名和包名匹配。
- 在目标硬件上完成登录、网络、扫码/串口/相机或定位测试。
- 使用正式签名构建 Release APK。

## 10. 文档与 RAG

文档修改后运行：

```bash
make docs-build
make docs-check
```

RAG 只允许索引 `docs/操作手册/` 中的权威文件。修改索引来源后应重启后端，确保进程重新加载新索引。

## 11. 回滚

1. 停止继续发布。
2. 记录故障版本、时间、trace id 和受影响订单。
3. 回滚应用镜像；数据库有迁移时按迁移设计处理，不直接删除业务表。
4. 恢复前一个可验证的 RAG 和文档产物。
5. 运行健康检查和关键角色登录、下单、分单、配送、收货 smoke。
