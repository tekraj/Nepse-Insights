from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Double, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketSectorSnapshot(Base):
    """One row per (sector, scrape): session-to-date trading totals per
    sector from nepalstock.com.np's sectorwise endpoint. Plain-insert
    timeseries, like the other *_snapshot tables. Empty before 2026-10-15."""

    __tablename__ = "market_sector_snapshot"
    __table_args__ = (
        Index("idx_market_sector_snapshot_scraped_at", "scraped_at"),
        Index("idx_market_sector_snapshot_sector_name", "sector_name"),
        {"comment": "Live per-minute session-to-date turnover, volume and trade count per sector."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sector_name: Mapped[str] = mapped_column(Text, nullable=False)
    turnover: Mapped[float | None] = mapped_column(Double, nullable=True, comment="NPR traded so far this session.")
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Shares traded so far this session.")
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Trades so far this session.")
    traded_security_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Securities of the sector that traded this session."
    )
    trade_date: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Session date as 'YYYY-MM-DD' text (NEPSE businessDate)."
    )
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
