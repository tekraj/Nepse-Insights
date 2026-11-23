from __future__ import annotations

from datetime import datetime

from sqlalchemy import Double, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketIndexSnapshot(Base):
    """One row per (index, live scrape): the index value NEPSE showed at that
    moment. Plain-insert timeseries -- every scrape is a new row.

    Mixed granularity: one 15:00 close per trading day from the CSV import
    (2021-01-17 .. 2026-06-29), irregular ticks 2026-06-29 .. 09-14, then one
    row per minute during market hours. The dashboard reads it; research code
    should use market_index_daily / market_intraday_tick instead."""

    __tablename__ = "market_index_snapshot"
    __table_args__ = (
        Index("idx_market_index_snapshot_scraped_at", "scraped_at"),
        Index("idx_market_index_snapshot_index_name", "index_name"),
        {"comment": "Live index values, one row per index per scrape (1-minute during market hours since 2026-09-15)."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    index_name: Mapped[str] = mapped_column(Text, nullable=False)
    index_value: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Index level in points at scrape time.")
    point_change: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="Change in points vs the previous session's close."
    )
    percent_change: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="Change in % vs the previous session's close."
    )
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), comment="Scrape time, naive NPT.")
