# 运维与发布运行手册（简版）

## 1. 健康检查
- API健康：`GET /api/system/healthz`
- API就绪：`GET /api/system/readyz`

## 2. 数据库迁移
- 生成迁移：`alembic revision -m "desc"`
- 执行迁移：`alembic upgrade head`
- 回滚一步：`alembic downgrade -1`

## 3. 备份与恢复
- 全量备份：`bash scripts/mysql_backup.sh`
- 恢复示例：`mysql -h 127.0.0.1 -P 3306 -u root -p dazong < backup.sql`

## 4. 发布步骤（建议）
1. 先执行后端测试与前端构建
2. 执行数据库迁移
3. 再滚动发布应用容器
4. 发布后验证健康检查与关键业务链路

## 5. Codex 修改交付规则
- 每次代码修改如果影响 Docker 运行态，Codex 需要直接执行对应的 `docker compose up -d --build --force-recreate ...` 或等效重构/重启命令，不把重构步骤留给使用者手动操作。
- 重构完成后，Codex 需要给出可直接访问的本机 URL，并验证关键页面和接口已经可用。

## 6. 故障回滚
1. 快速回滚镜像版本
2. 按需执行数据库降级脚本
3. 校验订单、账单、预警核心链路
