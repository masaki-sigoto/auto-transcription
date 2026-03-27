from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    name: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str | None
    avatar_url: str | None
    plan: str
    usage_minutes_month: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UsageStats(BaseModel):
    used_minutes: int
    limit_minutes: int
    plan: str
    reset_date: datetime
