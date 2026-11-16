from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class NepseBroker(Base):
    """Broker (member) master from nepalstock.com.np's /api/nots/member:
    every trading member with its current registered name, keyed by the
    member code that nepse_floorsheet stores as buyer/seller_member_id.

    The names are NEPSE's *current* ones -- a firm that renamed shows its
    new name for old sessions too. Fills nepse_floorsheet's broker name
    columns for sessions NEPSE no longer serves (merolagani's history has
    member codes only).

    active_status: "A" active, "SUSPEND" suspended (as reported by NEPSE).
    """

    __tablename__ = "nepse_broker"

    member_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_name: Mapped[str] = mapped_column(Text, nullable=False)
    active_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    membership_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_dealer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    nepse_member_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), onupdate=func.now())
