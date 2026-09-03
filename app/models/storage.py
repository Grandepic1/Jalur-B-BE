from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StorageDeletionJob(Base):
    __tablename__ = "storage_deletion_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_path: Mapped[str] = mapped_column(String(500), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    not_before: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="CURRENT_TIMESTAMP"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="CURRENT_TIMESTAMP"
    )
