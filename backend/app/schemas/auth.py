import uuid

from pydantic import BaseModel, Field


class SyncProfileRequest(BaseModel):
    # users.display_name은 String(100) — 상한이 없으면 긴 이름이 DB 오류(500)로 끝났다
    display_name: str | None = Field(default=None, max_length=100)


class FindAccountRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class FindAccountResponse(BaseModel):
    message: str


class AccountDeleteRequest(BaseModel):
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    needs_password_reset: bool

    model_config = {"from_attributes": True}
