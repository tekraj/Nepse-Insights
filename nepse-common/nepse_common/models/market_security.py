from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketSecurity(Base):
    """Security master from nepalstock.com.np's /api/nots/company/list:
    every listed, suspended and delisted security with its sector and
    instrument type. Used to map stocks to sectors (TDA point-cloud
    grouping), to pick the equity universe for history backfills, and to
    keep delisted/merged names in that universe (avoids survivorship bias
    in crash backtests).
    """

    __tablename__ = "market_security"
    __table_args__ = (
        Index("idx_market_security_symbol", "symbol"),
        {"comment": "Security master: every listed, suspended and delisted NEPSE security with sector and type."},
    )

    security_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False, comment="NEPSE's security id."
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    security_name: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Name of the instrument, e.g. '11% KBL Debenture 2089'."
    )
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Issuing company.")
    sector_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    instrument_type: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Equity, Mutual Funds, debentures, ...")
    listing_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="'A' active, 'S' suspended, 'D' delisted (as reported by NEPSE)."
    )
    updated_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), onupdate=func.now())
