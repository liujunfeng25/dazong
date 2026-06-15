from typing import Literal

from pydantic import BaseModel, Field


class CameraPtzIn(BaseModel):
    """萤石云台：direction 0-上 1-下 2-左 3-右 8-放大 9-缩小 等（见开放平台文档）。"""

    action: Literal["start", "stop"]
    direction: int = Field(ge=0, le=11)
    speed: int = Field(default=1, ge=1, le=2)
