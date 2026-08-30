from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    DATE,
    TIMESTAMP,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WeeklyCareerInsight(Base):
    __tablename__ = "weekly_career_insights"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_insight_user_week"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(DATE)
    weekly_insight: Mapped[str] = mapped_column(Text)
    next_action: Mapped[str] = mapped_column(Text)
    next_action_path: Mapped[str] = mapped_column(String(100))
    provider_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="CURRENT_TIMESTAMP"
    )
