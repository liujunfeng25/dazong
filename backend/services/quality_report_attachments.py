"""质检报告多附件：校验、Minio 上传、URL 列表与删除。"""

import logging
from typing import Optional
from urllib.parse import unquote

from fastapi import HTTPException, UploadFile
from minio import Minio

from config import settings
from models import QualityReport
from services.storage.minio_client import upload_quality_file

logger = logging.getLogger(__name__)

MAX_BYTES_PER_FILE = 20 * 1024 * 1024
MAX_FILES_PER_REPORT = 20

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
    }
)

# 常见扩展名兜底（部分浏览器对 heic 等仍 octet-stream）
ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"})


def file_urls_from_row(row) -> list[str]:
    """有序 URL 列表：单图仅 file_url；多图为 file_url + attachments_json。"""
    first = (row.file_url or "").strip()
    if not first:
        return []
    extra = row.attachments_json
    if isinstance(extra, list) and len(extra) > 0:
        rest = [str(u).strip() for u in extra if str(u).strip()]
        return [first] + rest
    return [first]


def _suffix_ok(filename: Optional[str]) -> bool:
    if not filename:
        return False
    lower = filename.lower()
    for suf in ALLOWED_SUFFIXES:
        if lower.endswith(suf):
            return True
    return False


def _validate_one_file(file: UploadFile, data: bytes) -> None:
    if len(data) > MAX_BYTES_PER_FILE:
        raise HTTPException(400, f"单文件不能超过 {MAX_BYTES_PER_FILE // (1024 * 1024)}MB")
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct in ALLOWED_CONTENT_TYPES:
        return
    if _suffix_ok(file.filename):
        return
    raise HTTPException(
        400,
        "不支持的文件类型，请上传 JPG、PNG、GIF、WebP 或 PDF",
    )


def _object_key_from_public_url(url: str) -> Optional[str]:
    proxy_prefix = "/api/system/files/minio/"
    if url.startswith(proxy_prefix):
        key = unquote(url[len(proxy_prefix) :]).strip().lstrip("/")
        return key if key and ".." not in key.split("/") else None
    base = (settings.minio_public_base_url or "").rstrip("/")
    if not url or not base:
        return None
    prefix = base + "/"
    if not url.startswith(prefix):
        return None
    return url[len(prefix) :]


def delete_public_urls(urls: list[str]) -> None:
    """按公开 URL 删除 Minio 对象；失败仅打日志。"""
    if not urls:
        return
    try:
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    except Exception:
        logger.exception("delete_public_urls: cannot create Minio client")
        return
    for url in urls:
        key = _object_key_from_public_url(url.strip())
        if not key:
            continue
        try:
            client.remove_object(settings.minio_bucket, key)
        except Exception:
            logger.exception("remove_object bucket=%s key=%s", settings.minio_bucket, key)


async def validate_and_upload_files(files: list[UploadFile]) -> list[str]:
    if not files:
        raise HTTPException(400, "请至少选择一个文件")
    if len(files) > MAX_FILES_PER_REPORT:
        raise HTTPException(400, f"单次最多上传 {MAX_FILES_PER_REPORT} 个文件")
    urls: list[str] = []
    for f in files:
        try:
            await f.seek(0)
        except Exception:
            pass
        data = await f.read()
        _validate_one_file(f, data)
        try:
            await f.seek(0)
        except Exception:
            pass
        urls.append(await upload_quality_file(f))
    return urls


def persist_urls_to_row(urls: list[str], row) -> None:
    """写入 ORM：首张 file_url，其余 attachments_json；单图时 attachments_json=None。"""
    if not urls:
        raise HTTPException(400, "无有效文件 URL")
    row.file_url = urls[0]
    if len(urls) == 1:
        row.attachments_json = None
    else:
        row.attachments_json = urls[1:]


def quality_report_to_dict(row: QualityReport) -> dict:
    created = getattr(row, "created_at", None)
    return {
        "id": int(row.id),
        "supplier_id": int(row.supplier_id),
        "product_id": int(row.product_id),
        "order_id": int(row.order_id),
        "allocation_id": int(row.allocation_id) if row.allocation_id is not None else None,
        "file_url": row.file_url,
        "file_urls": file_urls_from_row(row),
        "report_no": row.report_no,
        "status": row.status,
        "created_at": created.isoformat() if created else None,
    }


def periodic_quality_report_to_dict(row) -> dict:
    created = getattr(row, "created_at", None)
    reviewed_at = getattr(row, "reviewed_at", None)
    return {
        "id": int(row.id),
        "provider_id": int(row.provider_id),
        "product_id": int(row.product_id),
        "revision_of_id": (
            int(row.revision_of_id) if getattr(row, "revision_of_id", None) is not None else None
        ),
        "version": int(getattr(row, "version", 1) or 1),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "file_url": row.file_url,
        "file_urls": file_urls_from_row(row),
        "report_no": row.report_no,
        "status": row.status,
        "reviewed_by": int(row.reviewed_by) if row.reviewed_by is not None else None,
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "reject_reason": row.reject_reason,
        "created_at": created.isoformat() if created else None,
    }
