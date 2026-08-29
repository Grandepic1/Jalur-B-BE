from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ─── SQLAlchemy Model ────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    # The column name is retained for migration compatibility; only password hashes are stored.
    password: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=false())
    token_version: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )


Index("uq_users_email_lower", func.lower(User.email), unique=True)
Index("uq_users_username_lower", func.lower(User.username), unique=True)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str = Field(..., max_length=50)
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=255)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    email_verified: bool

    model_config = ConfigDict(from_attributes=True)
