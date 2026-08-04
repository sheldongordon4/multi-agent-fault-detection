from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base, TimeStampMixin, ULIDMixin


class Notification(Base, ULIDMixin, TimeStampMixin):
    """
    Operator-facing incident alert. MAFD has no user accounts, so notifications
    are broadcast to every connected dashboard rather than scoped to a user.
    """

    __tablename__ = "notifications"

    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Optional incident context for filtering / deep-linking in the UI.
    incident_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    bus_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
