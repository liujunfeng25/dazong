from pydantic import BaseModel, Field, field_validator


class ComplaintIn(BaseModel):
    order_id: int = Field(..., gt=0, description="投诉关联订单 ID")
    reason: str = Field(..., min_length=1, max_length=500, description="投诉原因（最长 500 字）")
    image_urls: list[str] = Field(default_factory=list, description="投诉图片 URL 数组（最多 5 张）")

    @field_validator("image_urls")
    @classmethod
    def _limit_images(cls, v: list[str]) -> list[str]:
        cleaned = [str(x).strip() for x in (v or []) if str(x).strip()]
        if len(cleaned) > 5:
            raise ValueError("最多上传 5 张图片")
        return cleaned

    @field_validator("reason")
    @classmethod
    def _trim_reason(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("投诉原因不能为空")
        return s
