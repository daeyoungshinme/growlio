import uuid

from pydantic import BaseModel, Field


class SyncProfileRequest(BaseModel):
    display_name: str | None = None


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
