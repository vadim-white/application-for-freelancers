from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class UserBase(BaseModel):
    email: EmailStr
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

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def serialize_role(cls, v):
        if hasattr(v, "value"):
            return v.value
        return v


class UserAuth(BaseModel):
    email: EmailStr
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
