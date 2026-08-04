from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from ulid import ULID

from app.database import metadata


class Base(DeclarativeBase):
    metadata = metadata


class TimeStampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class ULIDMixin:
    """Primary key as ULID string (26 chars, lexicographically sortable)."""

    id: Mapped[str] = mapped_column(
        String(26),
        primary_key=True,
        default=lambda: str(ULID()),
    )
