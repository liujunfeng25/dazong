from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/system", tags=["system"])


class SmartScaleAppVersionOut(BaseModel):
    """智能秤 App 拉取版本信息（无需登录，供 Pad 启动自检）。"""

    version_code: int
    version_name: str = ""
    apk_url: str = ""
    wgt_url: str = ""
    force: bool = False
    notes: str = ""


@router.get("/healthz")
async def healthz():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


@router.get("/readyz")
async def readyz():
    return {"status": "ready", "ts": datetime.utcnow().isoformat()}


@router.get("/smart-scale-app/version", response_model=SmartScaleAppVersionOut)
async def smart_scale_app_version():
    """智能秤客户端启动时调用；通过环境变量配置各环境下载地址（内网 http / 上线 https）。"""
    return SmartScaleAppVersionOut(
        version_code=int(settings.smart_scale_app_version_code),
        version_name=str(settings.smart_scale_app_version_name or ""),
        apk_url=str(settings.smart_scale_app_apk_url or "").strip(),
        wgt_url=str(settings.smart_scale_app_wgt_url or "").strip(),
        force=bool(settings.smart_scale_app_force_update),
        notes=str(settings.smart_scale_app_notes or ""),
    )
