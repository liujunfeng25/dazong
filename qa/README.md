# Dazong QA 隔离环境

该环境仅用于九端产品审计，端口与数据卷均和日常演示环境隔离。

| 服务 | 地址 |
| --- | --- |
| Web | `http://127.0.0.1:18080` |
| API | `http://127.0.0.1:18000` |
| MySQL | `127.0.0.1:13306` |
| MinIO | `http://127.0.0.1:19000` |

审计证据写入 `qa-reports/2026-06-12/`。该目录中的测试允许改变 QA 数据，不得指向日常演示库。

## 启动与停止

```bash
docker compose -f qa/docker-compose.qa.yml up -d
docker compose -f qa/docker-compose.qa.yml ps
docker compose -f qa/docker-compose.qa.yml down
```

默认仅监听 `127.0.0.1`，不得改成公网监听后继续使用当前 QA 密码。

## 审计命令

```bash
python3 qa/audit_api.py
python3 qa/dynamic_security_checks.py
python3 qa/runtime_resilience_checks.py
python3 qa/driver_state_checks.py
python3 qa/receive_concurrency_check.py
python3 qa/settlement_consistency_check.py
qa/dependency_readiness_check.sh
mysql -h127.0.0.1 -P13306 -uroot -pqa_root_password dazong_qa \
  < qa/database_consistency.sql
```

`driver_state_checks.py`、`receive_concurrency_check.py` 和
`settlement_consistency_check.py` 会改变隔离 QA 订单状态。重复执行前应重新复制基线数据或换用新的测试对象。

Web 断言：

```bash
cd frontend
PLAYWRIGHT_TEST_BASE_URL=http://127.0.0.1:18080 \
  npx playwright test e2e/qa-nine-end-audit.spec.ts --workers=1
```

预期结果包含一条刻意制造的失败：商品接口返回 500 时，当前页面存在未捕获 Promise 错误。
