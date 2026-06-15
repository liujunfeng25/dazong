from datetime import datetime
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from config import settings
from services.storage.minio_client import get_minio_client

router = APIRouter(prefix="/system", tags=["system"])
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DOWNLOAD_DIRS = [
    BACKEND_DIR / "public_downloads",
    PROJECT_ROOT / "frontend" / "public" / "downloads",
]


class SmartScaleAppVersionOut(BaseModel):
    """智能秤 App 拉取版本信息（无需登录，供 Pad 启动自检）。"""

    version_code: int
    version_name: str = ""
    apk_url: str = ""
    wgt_url: str = ""
    force: bool = False
    notes: str = ""


APP_DOWNLOADS = {
    "smart_scale": {
        "prefixes": ("smart-scale",),
        "latest_alias": "smart-scale-android-latest.apk",
    },
    "sorter_pda": {
        "prefixes": ("sorter-pda",),
        "latest_alias": "sorter-pda-latest.apk",
    },
    "driver_android": {
        "prefixes": ("driver-android",),
        "latest_alias": "driver-android-latest.apk",
    },
}


def _format_apk_size(size: int) -> str:
    mb = size / 1024 / 1024
    if mb >= 10:
        return f"约 {mb:.0f} MB"
    return f"约 {mb:.1f} MB"


def _iter_download_files():
    seen = set()
    for directory in DOWNLOAD_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.apk"):
            if path.name in seen:
                continue
            seen.add(path.name)
            yield path


def _file_payload(path: Path):
    stat = path.stat()
    return {
        "filename": path.name,
        "url": f"/api/system/downloads/{path.name}",
        "size_bytes": stat.st_size,
        "size_label": _format_apk_size(stat.st_size),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


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


@router.get("/downloads/manifest")
async def download_manifest():
    """下载页动态清单：避免 HTML 里写死 APK 文件名和大小。"""
    files = list(_iter_download_files())
    apps = {}
    for key, config in APP_DOWNLOADS.items():
        prefixes = tuple(config["prefixes"])
        alias_name = str(config["latest_alias"])
        candidates = [
            p for p in files
            if p.name != alias_name and any(p.name.startswith(prefix) for prefix in prefixes)
        ]
        latest_real = max(candidates, key=lambda p: p.stat().st_mtime, default=None)
        alias = next((p for p in files if p.name == alias_name), None)
        download_path = alias or latest_real
        if latest_real and download_path:
            payload = _file_payload(latest_real)
            payload["url"] = f"/api/system/downloads/{download_path.name}"
            payload["download_filename"] = download_path.name
            apps[key] = payload

    history = [
        _file_payload(path)
        for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        if "latest" not in path.name
    ][:12]
    return {"apps": apps, "history": history}


@router.get("/downloads/{filename}")
async def download_public_apk(filename: str):
    """给 Android 手机/PDA 下载 APK。

    部分国产手机浏览器接管静态文件下载时会拿到很小的中间页，导致“解析软件包出现问题”。
    这里用后端 FileResponse 明确返回 Content-Length、APK MIME 和附件文件名。
    """
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".apk"):
        raise HTTPException(404, "文件不存在")
    file_path = next((p / safe_name for p in DOWNLOAD_DIRS if (p / safe_name).is_file()), None)
    if file_path is None:
        raise HTTPException(404, "文件不存在")
    return FileResponse(
        file_path,
        media_type="application/vnd.android.package-archive",
        filename=safe_name,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/files/minio/{object_name:path}")
async def download_minio_file(object_name: str):
    """统一代理系统生成的 MinIO 图片，避免前端/Pad 直连 127.0.0.1:9000。"""
    safe_name = str(object_name or "").strip().lstrip("/")
    parts = [p for p in safe_name.split("/") if p]
    allowed_prefixes = {
        "quality",
        "product",
        "complaint",
        "receiving",
        "dispatch",
        "smart-scale-recognition",
    }
    if not parts or parts[0] not in allowed_prefixes or any(p in {".", ".."} for p in parts):
        raise HTTPException(404, "文件不存在")
    obj = None
    try:
        obj = get_minio_client().get_object(settings.minio_bucket, safe_name)
        data = obj.read()
    except Exception as exc:
        raise HTTPException(404, "文件不存在") from exc
    finally:
        if obj is not None:
            try:
                obj.close()
                obj.release_conn()
            except Exception:
                pass
    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        data,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
