"""中农价格网采集账号：DB 持久化（Fernet 加密）+ .env 回退。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal

CRED_TBL = "zgncpjgw_account_config"
_ROW_ID = 1

_lock = asyncio.Lock()
_username: str = ""
_password: str = ""
_source: str = "env"  # env | database
_updated_at: Optional[str] = None

# Playwright 同步实例全局互斥，避免 Docker 内多 Chromium 抢资源卡死
_PLAYWRIGHT_LOCK = threading.Lock()
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ZgncpjgwAuthError(RuntimeError):
    """账号或密码错误，与网络/WAF 区分。"""


def _fernet() -> Fernet:
    digest = hashlib.sha256((settings.jwt_secret_key or "zgncpjgw").encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def format_login_failure(payload: dict[str, Any]) -> str:
    """将 user.login 响应转为面向运营的可读错误。"""
    status = int(payload.get("status") or 0)
    msg = str(payload.get("message") or "").strip()
    if status == 40003 or "密码" in msg or "用户名" in msg:
        return (
            f"中农价格网账号或密码错误（{msg or 'status=40003'}）。"
            "请在「全国农产品价格 → 配置」中核对手机号与密码，保存后点「测试登录」验证。"
        )
    if status != 200:
        return f"中农价格网登录失败：{msg or payload}"
    return ""


def is_auth_failure_message(message: str) -> bool:
    text_value = message or ""
    return (
        "账号或密码错误" in text_value
        or "用户名或密码" in text_value
        or "40003" in text_value
        or isinstance(message, str) and "ZgncpjgwAuthError" in text_value
    )


def get_username() -> str:
    return (_username or settings.zgncpjgw_username or "").strip()


def get_password() -> str:
    return _password or settings.zgncpjgw_password or ""


def get_source() -> str:
    return _source


def get_updated_at() -> Optional[str]:
    return _updated_at


def credentials_configured() -> bool:
    return bool(get_username() and get_password())


def _apply_runtime(username: str, password: str, *, source: str, updated_at: Optional[str] = None) -> None:
    global _username, _password, _source, _updated_at
    _username = (username or "").strip()
    _password = password or ""
    _source = source
    _updated_at = updated_at


async def load_from_db(session: AsyncSession) -> bool:
    res = await session.execute(
        text(
            f"""
            SELECT username, password_enc, updated_at
            FROM `{CRED_TBL}` WHERE id = :id LIMIT 1
            """
        ),
        {"id": _ROW_ID},
    )
    row = res.mappings().first()
    if not row or not (row.get("username") or "").strip():
        return False
    pwd = _decrypt(str(row.get("password_enc") or ""))
    if not pwd:
        return False
    ts = row.get("updated_at")
    updated = ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None)
    _apply_runtime(str(row["username"]), pwd, source="database", updated_at=updated)
    return True


async def refresh_credentials() -> None:
    """启动或保存后刷新内存中的有效账号。"""
    async with _lock:
        if "mysql" not in settings.database_url:
            _apply_runtime(settings.zgncpjgw_username, settings.zgncpjgw_password, source="env")
            return
        async with SessionLocal() as session:
            if await load_from_db(session):
                return
        _apply_runtime(settings.zgncpjgw_username, settings.zgncpjgw_password, source="env")


async def save_credentials(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    updated_by: str = "",
) -> None:
    user = (username or "").strip()
    if not user:
        raise ValueError("手机号不能为空")
    if not password:
        raise ValueError("密码不能为空")
    enc = _encrypt(password)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    await session.execute(
        text(
            f"""
            INSERT INTO `{CRED_TBL}` (id, username, password_enc, updated_at, updated_by)
            VALUES (:id, :username, :password_enc, :updated_at, :updated_by)
            ON DUPLICATE KEY UPDATE
                username = VALUES(username),
                password_enc = VALUES(password_enc),
                updated_at = VALUES(updated_at),
                updated_by = VALUES(updated_by)
            """
        ),
        {
            "id": _ROW_ID,
            "username": user,
            "password_enc": enc,
            "updated_at": now,
            "updated_by": (updated_by or "")[:64],
        },
    )
    await session.commit()
    _apply_runtime(user, password, source="database", updated_at=now.isoformat())


def snapshot_for_api() -> dict[str, Any]:
    return {
        "username": get_username(),
        "password": get_password(),
        "password_configured": bool(get_password()),
        "source": get_source(),
        "updated_at": get_updated_at(),
    }


def _base_url() -> str:
    return (settings.zgncpjgw_base_url or "https://www.zgncpjgw.com").rstrip("/")


def _is_waf_html(body: str) -> bool:
    text_value = (body or "").strip().lower()
    return bool(text_value) and (text_value.startswith("<html") or "acw_sc__v2" in text_value)


def fetch_waf_cookies_sync() -> list[dict[str, Any]]:
    """同步过 WAF 取 Cookie（在线程中调用，可被 wait_for 限时）。"""
    from playwright.sync_api import sync_playwright

    base = _base_url()
    with _PLAYWRIGHT_LOCK:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=20_000)
            try:
                context = browser.new_context(user_agent=_UA)
                page = context.new_page()
                page.goto(base, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(1200)
                return list(context.cookies())
            finally:
                browser.close()


def test_login_sync(username: str, password: str) -> dict[str, Any]:
    """同步测试登录：过 WAF + user.login，供 credentials/test 在线程池执行。"""
    import httpx

    user = (username or "").strip()
    if not user or not password:
        return {
            "ok": False,
            "message": "请填写手机号与密码",
            "error_kind": "other",
            "username": user,
        }
    base = _base_url()
    try:
        cookies = fetch_waf_cookies_sync()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"无法打开中农价格网（可能网络或 WAF 拦截）：{exc}",
            "error_kind": "network",
            "username": user,
        }

    jar = httpx.Cookies()
    for item in cookies:
        jar.set(
            item.get("name", ""),
            item.get("value", ""),
            domain=item.get("domain") or "",
            path=item.get("path") or "/",
        )
    headers = {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": base,
        "Referer": f"{base}/",
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(30.0, connect=12.0),
            cookies=jar,
            follow_redirects=True,
            trust_env=False,
            headers=headers,
        ) as client:
            url = f"{base}/home/rest.php?method=user.login"
            files = {"username": (None, user), "password": (None, password)}
            response = client.post(url, files=files)
            body = response.text
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"登录接口请求失败：{exc}",
            "error_kind": "network",
            "username": user,
        }

    if _is_waf_html(body):
        return {
            "ok": False,
            "message": "触发网站 WAF 防护，请稍后重试",
            "error_kind": "waf",
            "username": user,
        }
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"登录接口返回非 JSON：{body[:120]}",
            "error_kind": "other",
            "username": user,
        }

    err = format_login_failure(payload)
    if err:
        kind = "auth" if int(payload.get("status") or 0) == 40003 or "密码" in err else "other"
        return {"ok": False, "message": err, "error_kind": kind, "username": user}
    return {
        "ok": True,
        "message": "登录成功，账号可用",
        "error_kind": None,
        "username": user,
    }
