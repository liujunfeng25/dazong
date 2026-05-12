from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    company_name: str


class UserMe(BaseModel):
    id: int
    username: str
    role: str
    company_name: str
    status: str
    address: Optional[str] = None
    lng: Optional[float] = None
    lat: Optional[float] = None
    canteen_id: Optional[int] = None
    canteen_name: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class SimpleMessageResponse(BaseModel):
    message: str
