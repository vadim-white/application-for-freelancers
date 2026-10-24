from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    field_validator,
    model_validator,
)

from .models import UserRole

# EmailStr приводит к нижнему регистру только домен: без этого User1@… и user1@… — два аккаунта
LowerEmailStr = Annotated[EmailStr, AfterValidator(str.lower)]


class UserBase(BaseModel):
    email: LowerEmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_length_check(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot be longer than 72 bytes")
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserRead(UserBase):
    id: int
    is_active: bool
    role: str
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def serialize_role(cls, v):
        if hasattr(v, "value"):
            return v.value
        return v


class UserList(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int


class UserAdminUpdate(BaseModel):
    # merge-patch: нет поля — не трогать, null — 422;
    # неизвестное поле — 422, иначе опечатка молча ничего не меняет
    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def no_null(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class UserAuth(BaseModel):
    email: LowerEmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_length_check(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot be longer than 72 bytes")
        return v


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str
