from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncCursor(Base):
    """High-water mark for an external poll, keyed by source name."""

    __tablename__ = "sync_cursors"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
