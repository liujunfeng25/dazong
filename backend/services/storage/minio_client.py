from uuid import uuid4

from fastapi import UploadFile
from minio import Minio

from config import settings


def _get_client() -> Minio:
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    return client


async def upload_quality_file(file: UploadFile) -> str:
    client = _get_client()
    object_name = f"quality/{uuid4().hex}_{file.filename}"
    data = await file.read()
    from io import BytesIO

    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=file.content_type or "application/octet-stream",
    )
    return f"{settings.minio_public_base_url}/{object_name}"


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
    return f"{settings.minio_public_base_url}/{object_name}"


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
    return f"{settings.minio_public_base_url}/{object_name}"
