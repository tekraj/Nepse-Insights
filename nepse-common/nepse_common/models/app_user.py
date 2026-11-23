from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class AppUser(Base):
    """Dashboard login accounts. No signup endpoint -- created only via manage.py create-admin."""

    __tablename__ = "app_user"
    __table_args__ = {"comment": "Dashboard login accounts (created with api-service manage.py create-admin)."}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, comment="bcrypt hash.")
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
