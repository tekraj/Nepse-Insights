from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Float, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketFundamentalDaily(Base):
    """Company fundamentals per equity and trading day, as merolagani's
    company page shows them after that session (nepse-service
    CompanyFundamentalsWorkflow, daily after the close). EPS / book value
    change with quarterly reports; P/E, P/BV, market cap and yield move
    with the price, so the daily rows form their time series.

    merolagani's figures: `eps` is its annualised EPS of the latest
    reported quarter (`eps_period`), `pe_ratio` = market_price / eps.
    """

    __tablename__ = "market_fundamental_daily"
    __table_args__ = (
        Index("idx_market_fundamental_daily_trade_date", "trade_date"),
        {"comment": "Company fundamentals per equity and trading day (merolagani): EPS, P/E, book value, P/BV, dividend, market cap."},
    )

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, comment="Session the figures belong to (merolagani's 'Last Traded On').")
    sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Price merolagani computed the ratios with (raw NPR).")
    eps: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Annualised earnings per share of the latest reported quarter (NPR).")
    eps_period: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Report the EPS comes from, e.g. 'FY:083-084, Q:1' (Nepali fiscal year).")
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, comment="market_price / eps.")
    book_value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Book value per share (NPR).")
    pbv: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Price / book value.")
    cash_dividend_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Latest cash dividend, % of paid-up value.")
    bonus_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Latest bonus share issue, %.")
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Market capitalisation (NPR).")
    paidup_value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Paid-up value per share (NPR, usually 100).")
    high_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_120d: Mapped[float | None] = mapped_column(Float, nullable=True, comment="120-day average price.")
    avg_180d: Mapped[float | None] = mapped_column(Float, nullable=True, comment="180-day average price.")
    yield_1y_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="merolagani's 1-year yield (price return), %.")
    avg_volume_30d: Mapped[float | None] = mapped_column(Float, nullable=True, comment="30-day average volume (shares).")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="merolagani")
    scraped_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
