from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import ClientCanteen, User

bearer_scheme = HTTPBearer(auto_error=True)


def verify_password(plain_password: str, password_hash: Optional[str]) -> bool:
    """校验登录密码；哈希缺失或非 bcrypt 格式时返回 False，避免未捕获异常导致 500。"""
    if not plain_password or not password_hash or not str(password_hash).strip():
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            str(password_hash).encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user: User, *, canteen_id: Optional[int] = None) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict = {"sub": str(user.id), "role": user.role, "exp": expires}
    if user.role == "client" and canteen_id is not None:
        payload["canteen_id"] = int(canteen_id)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的令牌"
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的令牌"
        ) from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用"
        )
    return user


def require_role(role: str):
    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"仅允许 {role} 角色访问",
            )
        return current_user

    return _checker


def parse_client_canteen_id_from_authorization(authorization: Optional[str]) -> Optional[int]:
    """从 Bearer Token 解析客户端当前食堂 ID（不含校验归属）。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        raw_payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
    cid = raw_payload.get("canteen_id")
    if cid is None:
        return None
    try:
        return int(cid)
    except (TypeError, ValueError):
        return None


async def resolve_client_canteen_id_from_request(
    db: AsyncSession,
    user: User,
    request: Request,
) -> int:
    """解析采购端 JWT 中的食堂 ID，并校验为归属本校的启用食堂（与下单/账单一致）。"""
    cid = parse_client_canteen_id_from_authorization(request.headers.get("authorization"))
    if cid is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先选择食堂")
    row = await db.scalar(
        select(ClientCanteen).where(
            ClientCanteen.id == cid,
            ClientCanteen.school_client_id == user.id,
            ClientCanteen.status == "active",
        )
    )
    if not row:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "食堂无效或已停用，请重新选择",
        )
    return int(row.id)


async def require_client_with_canteen(
    user: User = Depends(require_role("client")),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, ClientCanteen]:
    payload = decode_access_token(credentials.credentials)
    raw = payload.get("canteen_id")
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先选择食堂")
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先选择食堂")
    row = await db.scalar(
        select(ClientCanteen).where(
            ClientCanteen.id == cid,
            ClientCanteen.school_client_id == user.id,
            ClientCanteen.status == "active",
        )
    )
    if not row:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "食堂无效或已停用，请重新选择",
        )
    return user, row
