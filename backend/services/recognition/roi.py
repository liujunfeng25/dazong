from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image, ImageFilter, ImageStat

from config import settings
from services.storage.minio_client import get_minio_client


ALLOWED_ROTATIONS = {0, 90, 180, 270}


@dataclass(frozen=True)
class CropResult:
    data: bytes
    width: int
    height: int
    quality_status: str
    quality_score: float
    quality_reason: str | None


def normalize_roi(value: dict) -> dict:
    try:
        x = float(value.get("x"))
        y = float(value.get("y"))
        width = float(value.get("width"))
        height = float(value.get("height"))
        rotation = int(value.get("rotation") or 0)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("ROI 坐标格式不正确") from exc
    if rotation not in ALLOWED_ROTATIONS:
        raise ValueError("ROI 旋转角度仅支持 0/90/180/270")
    if min(x, y) < 0 or width <= 0 or height <= 0:
        raise ValueError("ROI 坐标必须为正数")
    if x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("ROI 超出图片边界")
    if width < 0.05 or height < 0.05:
        raise ValueError("ROI 区域过小")
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "width": round(width, 6),
        "height": round(height, 6),
        "rotation": rotation,
    }


def profile_roi(profile) -> dict:
    return normalize_roi(
        {
            "x": profile.x,
            "y": profile.y,
            "width": profile.width,
            "height": profile.height,
            "rotation": profile.rotation,
        }
    )


def crop_image_bytes(data: bytes, roi: dict) -> CropResult:
    normalized = normalize_roi(roi)
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("图片无法解析") from exc

    rotation = normalized["rotation"]
    if rotation:
        image = image.rotate(-rotation, expand=True)

    image_width, image_height = image.size
    left = round(normalized["x"] * image_width)
    top = round(normalized["y"] * image_height)
    right = round((normalized["x"] + normalized["width"]) * image_width)
    bottom = round((normalized["y"] + normalized["height"]) * image_height)
    if right <= left or bottom <= top:
        raise ValueError("ROI 裁剪区域为空")

    cropped = image.crop((left, top, min(right, image_width), min(bottom, image_height)))
    width, height = cropped.size
    quality_status, quality_score, quality_reason = assess_crop_quality(cropped)
    output = io.BytesIO()
    cropped.save(output, format="JPEG", quality=92, optimize=True)
    return CropResult(
        data=output.getvalue(),
        width=width,
        height=height,
        quality_status=quality_status,
        quality_score=quality_score,
        quality_reason=quality_reason,
    )


def assess_crop_quality(image: Image.Image) -> tuple[str, float, str | None]:
    width, height = image.size
    if width < 96 or height < 96:
        return "failed", 0.0, "裁剪分辨率低于 96×96"

    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = float(stat.mean[0])
    contrast = float(stat.stddev[0])
    edge_mean = float(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0])
    if brightness < 12:
        return "failed", 0.05, "画面过暗"
    if brightness > 248:
        return "failed", 0.05, "画面过曝"
    if contrast < 6:
        return "failed", 0.1, "画面内容过少或对比度不足"
    if edge_mean < 2:
        return "failed", 0.2, "画面疑似模糊"

    score = min(1.0, max(0.3, (contrast / 64.0) * 0.55 + (edge_mean / 32.0) * 0.45))
    return "passed", round(score, 4), None


def _minio_object_name(url: str) -> str | None:
    raw = str(url or "").strip()
    proxy_prefix = "/api/system/files/minio/"
    if raw.startswith(proxy_prefix):
        return unquote(raw[len(proxy_prefix) :]).lstrip("/")

    parsed = urlparse(raw)
    if parsed.path.startswith(proxy_prefix):
        return unquote(parsed.path[len(proxy_prefix) :]).lstrip("/")
    public_base = str(settings.minio_public_base_url or "").rstrip("/")
    if public_base and raw.startswith(public_base + "/"):
        path = unquote(raw[len(public_base) + 1 :]).lstrip("/")
        bucket_prefix = f"{str(settings.minio_bucket).strip('/')}/"
        return path[len(bucket_prefix) :] if path.startswith(bucket_prefix) else path
    return None


def _download_minio_object(object_name: str) -> bytes:
    response = get_minio_client().get_object(settings.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def download_image_bytes(url: str) -> bytes:
    object_name = _minio_object_name(url)
    if object_name:
        return await asyncio.to_thread(_download_minio_object, object_name)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        if not response.content:
            raise ValueError("图片内容为空")
        return response.content
