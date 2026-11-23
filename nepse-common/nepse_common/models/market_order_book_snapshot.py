from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketOrderBookSnapshot(Base):
    """One row per (security, scrape) snapshot of the bid/ask order book
    ("market depth") from nepalstock.com.np's per-security market-depth
    endpoint. Plain-insert timeseries, like the other *_snapshot tables.

    The bid/ask levels themselves are stored as JSONB (buy_levels /
    sell_levels, each NEPSE's list of {orderBookOrderPrice, quantity,
    orderCount} dicts) rather than normalized into a separate levels table,
    because the ladder is always read/written as a whole unit, never queried
    level-by-level."""

    __tablename__ = "market_order_book_snapshot"
    __table_args__ = (
        Index("idx_market_order_book_snapshot_scraped_at", "scraped_at"),
        Index("idx_market_order_book_snapshot_symbol", "symbol"),
        {"comment": "Live order-book (market depth) snapshots, up to 5 bid/ask levels, for the most liquid securities."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    total_buy_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Shares on all bid orders.")
    total_sell_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Shares on all ask orders.")
    buy_levels: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="Bid ladder as returned by NEPSE.")
    sell_levels: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="Ask ladder as returned by NEPSE.")
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
