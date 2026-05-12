#!/usr/bin/env python3
"""
将「当前哈希无法通过 demo123 校验」的用户统一改为演示密码 demo123。

重要说明：
- 数据库只存 bcrypt 哈希，**不存在也无法导出明文密码**；本脚本只报告
  「是否与 demo123 匹配」，不会也不能打印真实密码。

用法（Docker，与仓库其他脚本一致）：
  docker compose exec backend python scripts/normalize_all_passwords_demo123.py
  docker compose exec backend python scripts/normalize_all_passwords_demo123.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import bcrypt
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine  # noqa: E402
from dependencies import verify_password  # noqa: E402
from models import User  # noqa: E402

DEMO = "demo123"


async def main(*, dry_run: bool) -> None:
    async with SessionLocal() as db:
        rows = (await db.scalars(select(User).order_by(User.id))).all()
        ok = 0
        bad = 0
        for u in rows:
            matches = verify_password(DEMO, u.password_hash)
            if matches:
                ok += 1
                print(f"[匹配] id={u.id:5d}  username={u.username!r}  role={u.role}")
            else:
                bad += 1
                print(f"[不符] id={u.id:5d}  username={u.username!r}  role={u.role}")
                if not dry_run:
                    u.password_hash = bcrypt.hashpw(DEMO.encode("utf-8"), bcrypt.gensalt()).decode(
                        "utf-8"
                    )

        if not dry_run and bad:
            await db.commit()
            print(f"\n已提交：{bad} 个账号已重置为 {DEMO!r} 的新哈希。")
        elif dry_run and bad:
            print(f"\n（--dry-run）未写入数据库。{bad} 个账号非 {DEMO!r}；去掉 --dry-run 后重跑以更新。")
        else:
            print(f"\n汇总：共 {len(rows)} 个用户；与 {DEMO!r} 匹配 {ok}；需修正 {bad}。")


async def _run(dry_run: bool) -> None:
    try:
        await main(dry_run=dry_run)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="只检查，不写库")
    args = p.parse_args()
    asyncio.run(_run(dry_run=args.dry_run))
