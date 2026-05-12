import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import (
    bearer_scheme,
    create_access_token,
    decode_access_token,
    get_current_user,
    verify_password,
)
from models import ClientCanteen, User
from schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    SimpleMessageResponse,
    UserMe,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用"
        )

    token = create_access_token(user)
    return LoginResponse(token=token, role=user.role, company_name=user.company_name)


@router.get("/me", response_model=UserMe)
async def me(
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    canteen_id = None
    canteen_name = None
    address = current_user.address or ""
    lng = float(current_user.lng) if current_user.lng is not None else None
    lat = float(current_user.lat) if current_user.lat is not None else None
    if current_user.role == "client":
        try:
            payload = decode_access_token(credentials.credentials)
            raw = payload.get("canteen_id")
            if raw is not None:
                canteen_id = int(raw)
        except (HTTPException, TypeError, ValueError):
            canteen_id = None
        if canteen_id is not None:
            row = await db.scalar(
                select(ClientCanteen).where(
                    ClientCanteen.id == canteen_id,
                    ClientCanteen.school_client_id == current_user.id,
                )
            )
            if row:
                canteen_name = row.name
                address = row.address or address
                lng = float(row.lng) if row.lng is not None else lng
                lat = float(row.lat) if row.lat is not None else lat
    return UserMe(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        company_name=current_user.company_name,
        status=current_user.status,
        address=address,
        lng=lng,
        lat=lat,
        canteen_id=canteen_id,
        canteen_name=canteen_name,
    )


@router.post("/change-password", response_model=SimpleMessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_password = (payload.old_password or "").strip()
    new_password = (payload.new_password or "").strip()
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="旧密码和新密码不能为空")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    if old_password == new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")

    current_user.password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    await db.commit()
    return SimpleMessageResponse(message="密码修改成功")
