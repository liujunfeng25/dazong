from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from minio import Minio

from config import settings

logger = logging.getLogger(__name__)


def _anonymous_get_object_policy_json(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


def _ensure_anonymous_get_object_policy(client: Minio, bucket: str) -> None:
    """允许匿名 GET 对象，否则浏览器用 MINIO_PUBLIC_BASE_URL/... 直链会 AccessDenied。"""
    if not settings.minio_anonymous_read:
        return
    try:
        client.set_bucket_policy(bucket, _anonymous_get_object_policy_json(bucket))
        logger.info("MinIO bucket %s: anonymous GetObject policy applied", bucket)
    except Exception:
        logger.exception("MinIO set_bucket_policy failed bucket=%s", bucket)


def ensure_minio_bucket_ready_at_startup() -> None:
    """应用启动时调用：确保桶存在且（可选）匿名可读，不依赖「先上传一次」才套策略。"""
    try:
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        _ensure_anonymous_get_object_policy(client, settings.minio_bucket)
    except Exception:
        logger.exception("ensure_minio_bucket_ready_at_startup: MinIO 不可用（上传/预览将失败）")


def _get_client() -> Minio:
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    _ensure_anonymous_get_object_policy(client, settings.minio_bucket)
    return client


def get_minio_client() -> Minio:
    """共享给只读下载代理使用。"""
    return _get_client()


def minio_proxy_url(object_name: str) -> str:
    safe = str(object_name or "").strip().lstrip("/")
    if not safe or ".." in safe.split("/"):
        return ""
    return f"/api/system/files/minio/{quote(safe, safe='/')}"


def normalize_public_image_url(url: str | None) -> str | None:
    """把存库的 MinIO 直链归一化为后端代理 URL；非 MinIO URL 原样返回。"""
    raw = str(url or "").strip()
    if not raw:
        return None
    if raw.startswith("/api/system/files/minio/"):
        return raw
    public_base = (settings.minio_public_base_url or "").rstrip("/")
    if public_base and raw.startswith(public_base + "/"):
        return minio_proxy_url(unquote(raw[len(public_base) + 1 :]))
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    api_proxy_prefix = "/api/system/files/minio/"
    if parsed.scheme in {"http", "https"} and (parsed.path or "").startswith(api_proxy_prefix):
        return parsed.path
    bucket = str(settings.minio_bucket or "").strip("/")
    if parsed.scheme in {"http", "https"} and bucket:
        path = unquote(parsed.path or "").lstrip("/")
        prefix = f"{bucket}/"
        if path.startswith(prefix):
            return minio_proxy_url(path[len(prefix) :])
    return raw


def normalize_public_image_urls(urls: list | None) -> list[str]:
    out: list[str] = []
    for u in urls or []:
        v = normalize_public_image_url(str(u))
        if v:
            out.append(v)
    return out


def _quality_object_suffix(filename: str | None) -> str:
    """仅用短后缀生成对象名，避免把整段原始文件名拼进 URL 导致超过 quality_reports.file_url VARCHAR(255)。"""
    ext = (Path(filename or "").suffix or "").lower()
    if not ext or len(ext) > 12 or not ext.startswith("."):
        return ".bin"
    body = ext[1:]
    if not body or not all(c.isalnum() for c in body):
        return ".bin"
    return ext


async def upload_quality_file(file: UploadFile) -> str:
    """上传到 Minio；失败时抛出 503，便于前端区分「存储未就绪」与业务 4xx。"""
    object_name = f"quality/{uuid4().hex}{_quality_object_suffix(file.filename)}"
    data = await file.read()
    from io import BytesIO

    try:
        client = _get_client()
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as e:
        logger.exception("MinIO upload_quality_file failed bucket=%s key=%s", settings.minio_bucket, object_name)
        raise HTTPException(
            status_code=503,
            detail=(
                "质检文件存储不可用：无法连接或写入 Minio。"
                "本地开发请确认 Minio 已启动（默认 127.0.0.1:9000），并检查环境变量 MINIO_ENDPOINT / MINIO_PUBLIC_BASE_URL。"
            ),
        ) from e
    return minio_proxy_url(object_name)


async def upload_product_image(file: UploadFile) -> str:
    client = _get_client()
    object_name = f"product/{uuid4().hex}_{file.filename}"
    data = await file.read()
    from io import BytesIO

    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=file.content_type or "application/octet-stream",
    )
    return minio_proxy_url(object_name)


async def upload_complaint_image(file: UploadFile) -> str:
    """客户端售后投诉图片上传，落到 complaint/ 目录。"""
    client = _get_client()
    object_name = f"complaint/{uuid4().hex}_{file.filename}"
    data = await file.read()
    from io import BytesIO

    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=file.content_type or "application/octet-stream",
    )
    return minio_proxy_url(object_name)


async def upload_receiving_lock_photo(file: UploadFile) -> str:
    """智能收货端锁定读数时上传的秤盘留痕照片。"""
    return await _upload_receiving_image(file, "receiving/lock-photo", "收货留痕照片")


async def upload_receiving_return_photo(file: UploadFile) -> str:
    """智能收货端退货/质量问题证据照片。"""
    return await _upload_receiving_image(file, "receiving/return-evidence", "退货证据照片")


async def upload_dispatch_exception_photo(file: UploadFile) -> str:
    """调度/司机端异常发车、未随车、装车异常证据照片。"""
    return await _upload_receiving_image(file, "dispatch/exception-evidence", "发车异常证据照片")


async def upload_receiving_signature(file: UploadFile) -> str:
    """智能收货端收货签字图片。"""
    return await _upload_receiving_image(file, "receiving/signature", "收货签字图片")


async def _upload_receiving_image(file: UploadFile, prefix: str, label: str) -> str:
    content_type = (file.content_type or "").lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp 图片")
    suffix = _quality_object_suffix(file.filename)
    if suffix == ".bin":
        suffix = ".jpg"
    object_name = f"{prefix}/{uuid4().hex}{suffix}"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="照片为空")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="照片不能超过 8MB")
    from io import BytesIO

    try:
        client = _get_client()
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=file.content_type or "image/jpeg",
        )
    except Exception as e:
        logger.exception("MinIO upload_receiving_image failed bucket=%s key=%s", settings.minio_bucket, object_name)
        raise HTTPException(status_code=503, detail=f"{label}存储不可用") from e
    return minio_proxy_url(object_name)


async def upload_smart_scale_recognition_sample(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持图片样本")
    suffix = _quality_object_suffix(file.filename)
    if suffix == ".bin":
        suffix = ".jpg"
    object_name = f"smart-scale-recognition/{uuid4().hex}{suffix}"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="样本图片为空")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="样本图片不能超过 8MB")
    from io import BytesIO

    try:
        client = _get_client()
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=file.content_type or "image/jpeg",
        )
    except Exception as e:
        logger.exception("MinIO upload_smart_scale_recognition_sample failed bucket=%s key=%s", settings.minio_bucket, object_name)
        raise HTTPException(status_code=503, detail="智能秤训练样本存储不可用") from e
    return minio_proxy_url(object_name)


async def upload_smart_scale_recognition_bytes(
    data: bytes,
    *,
    content_type: str = "image/jpeg",
    prefix: str = "smart-scale-recognition/cropped",
) -> str:
    """Store a generated recognition artifact without fabricating an UploadFile."""
    if not data:
        raise HTTPException(status_code=400, detail="智能秤识别图片为空")
    object_name = f"{prefix.strip('/')}/{uuid4().hex}.jpg"
    from io import BytesIO

    try:
        client = _get_client()
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
    except Exception as e:
        logger.exception(
            "MinIO upload_smart_scale_recognition_bytes failed bucket=%s key=%s",
            settings.minio_bucket,
            object_name,
        )
        raise HTTPException(status_code=503, detail="智能秤裁剪图片存储不可用") from e
    return minio_proxy_url(object_name)
