from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketBroker(Base):
    """Broker (NEPSE "member") master from nepalstock.com.np's
    /api/nots/member: every trading member with its current registered name,
    keyed by the broker number that market_trade stores as
    buyer/seller_broker_code.

    The names are NEPSE's *current* ones -- a firm that renamed shows its
    new name for old sessions too. Fills market_trade's broker name columns
    for sessions NEPSE no longer serves (merolagani's history has broker
    codes only).
    """

    __tablename__ = "market_broker"
    __table_args__ = {"comment": "Broker master: NEPSE trading members by broker number, with current official name."}

    broker_code: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False, comment="Broker number (NEPSE memberCode), as in market_trade."
    )
    broker_name: Mapped[str] = mapped_column(Text, nullable=False, comment="Current official name.")
    active_status: Mapped[str | None] = mapped_column(Text, nullable=True, comment="'A' active, 'SUSPEND' suspended.")
    membership_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_dealer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    nepse_internal_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="NEPSE's internal row id for the member -- not the broker number."
    )
    updated_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), onupdate=func.now())
