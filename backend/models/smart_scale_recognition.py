from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SmartScaleRecognitionCategory(Base, TimestampMixin):
    __tablename__ = "smart_scale_recognition_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SmartScaleRecognitionSample(Base, TimestampMixin):
    __tablename__ = "smart_scale_recognition_samples"
    # source=receiving 时按 (category_id, order_id, line_index) 唯一，用于幂等批量导入
    __table_args__ = (
        UniqueConstraint(
            "category_id", "order_id", "line_index", name="uq_ssr_samples_cat_order_line"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("smart_scale_recognition_categories.id"), nullable=False, index=True
    )
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cropped_image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    angle: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 旧的客户端直方图特征，新真训练不再读取；保留以兼容旧数据
    feature_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # 新增：来源 & 收货导入回溯字段
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual|receiving
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    roi_profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("smart_scale_recognition_roi_profiles.id"), nullable=True
    )
    roi_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    roi_override_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", index=True
    )
    quality_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", index=True
    )
    quality_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SmartScaleRecognitionRoiProfile(Base, TimestampMixin):
    __tablename__ = "smart_scale_recognition_roi_profiles"
    __table_args__ = (
        UniqueConstraint("device_id", "version", name="uq_ssr_roi_device_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference_image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class SmartScaleRecognitionPackage(Base, TimestampMixin):
    """旧版直方图发布包（向后兼容；新真训练流程不再使用）。"""
    __tablename__ = "smart_scale_recognition_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SmartScaleRecognitionTrainTask(Base, TimestampMixin):
    """PyTorch 真训练任务 = 任务 + 训练产物（model.pt + class_mapping）合一记录。"""
    __tablename__ = "smart_scale_recognition_train_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|preparing|running|done|error|cancelled
    epochs: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    # 训练时类别快照：[{category_id, product_id, product_name, sample_count}]
    classes_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # idx -> "cat_{category_id}" （与 train.py 的 ImageFolder 类别同步）
    class_mapping_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {val_acc, train_acc, loss}
    roi_versions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_deployed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
