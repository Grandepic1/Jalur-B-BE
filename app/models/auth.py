from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import UserResponse


class OAuthLoginCode(Base):
    __tablename__ = "oauth_login_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship()  # noqa: F821


class AuthTokenPurpose(str, PyEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class AuthActionToken(Base):
    __tablename__ = "auth_action_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(SAEnum(AuthTokenPurpose))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    target_email: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship()  # noqa: F821


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., max_length=255)


class GoogleCodeExchange(BaseModel):
    code: str = Field(..., min_length=20, max_length=255)


class TokenActionRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=255)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)


class ResetPasswordRequest(TokenActionRequest):
    password: str = Field(..., min_length=8, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str | None = Field(None, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=255)


class UsernameUpdateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(character.isalnum() or character in "_.-" for character in value):
            raise ValueError("username may contain letters, numbers, underscores, dots, and hyphens")
        return value


class EmailChangeRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    current_password: str = Field(..., max_length=255)

    model_config = ConfigDict(extra="forbid")


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(..., max_length=255)

    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    message: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    next_path: str
    user: UserResponse
