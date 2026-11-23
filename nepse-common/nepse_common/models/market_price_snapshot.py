from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Double, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketPriceSnapshot(Base):
    """One row per (security, live scrape): every traded security's
    running session statistics from nepalstock.com.np's today-price
    endpoint. Plain-insert timeseries -- every scrape is a new row.

    close is NULL in every intraday snapshot (NEPSE only sets closePrice
    after the session ends); use last_traded_price intraday, and
    market_stock_daily for official daily closes. last_traded_price and
    volume are NULL before 2026-09-23."""

    __tablename__ = "market_price_snapshot"
    __table_args__ = (
        Index("idx_market_price_snapshot_scraped_at", "scraped_at"),
        Index("idx_market_price_snapshot_symbol", "symbol"),
        {"comment": "Live per-minute snapshot of every traded security's session-to-date prices and volume."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="NEPSE security id (market_security).")
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    security_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    open: Mapped[float | None] = mapped_column(Double, nullable=True)
    high: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Session high so far.")
    low: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Session low so far.")
    close: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="Official close; NULL intraday (NEPSE sets it after the session)."
    )
    previous_close: Mapped[float | None] = mapped_column(Double, nullable=True)
    last_traded_price: Mapped[float | None] = mapped_column(Double, nullable=True, comment="LTP at scrape time.")
    percent_change: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="last_traded_price vs previous_close, in %."
    )
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Shares traded so far this session.")
    turnover: Mapped[float | None] = mapped_column(Double, nullable=True, comment="NPR traded so far this session.")
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Trades so far this session.")
    average_traded_price: Mapped[float | None] = mapped_column(
        Double, nullable=True, comment="Volume-weighted average traded price so far this session."
    )
    # Unlike scraped_at, tells a fresh price apart from a stale one carried
    # over from an earlier minute (needed to correct non-synchronous trading
    # when estimating intraday correlations).
    last_traded_at: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="Time of this security's most recent trade (NEPSE lastUpdatedTime)."
    )
    trade_date: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Session date as 'YYYY-MM-DD' text (NEPSE businessDate)."
    )
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), comment="Scrape time, naive NPT.")
