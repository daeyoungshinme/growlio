import uuid

from pydantic import BaseModel, Field


class AccountDeleteRequest(BaseModel):
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    needs_password_reset: bool

    model_config = {"from_attributes": True}
