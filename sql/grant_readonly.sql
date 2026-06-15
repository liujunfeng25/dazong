-- AI run_sql 工具专用只读账号。
-- 用法（按实际 root 密码与库名替换；docker：docker exec -i dazong-mysql-1 mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < sql/grant_readonly.sql）
-- 然后在 backend/.env 配置：MYSQL_RO_USER=dazong_ro  MYSQL_RO_PASSWORD=<下面设置的密码>
--
-- 安全要点：只授 SELECT，不授任何写/DDL/FILE 权限；配合应用层 sqlglot 校验 + 强制 LIMIT + 超时 + 表白名单 + PII 脱敏，纵深防御。

CREATE USER IF NOT EXISTS 'dazong_ro'@'%' IDENTIFIED BY 'ChangeMe_ReadOnly_2026';

-- 仅授读权限到业务库（库名与 MYSQL_DB 一致，默认 dazong）
GRANT SELECT ON `dazong`.* TO 'dazong_ro'@'%';

-- 显式确保没有全局写/FILE 权限（默认即无，此处仅作声明性提醒，不需 REVOKE）
FLUSH PRIVILEGES;
