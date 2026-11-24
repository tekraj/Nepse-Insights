from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketCorporateAction(Base):
    """Cash dividends, bonus shares and right shares announced per fiscal
    year, from merolagani's company page history (nepse-service
    CompanyFundamentalsWorkflow replaces a company's rows on every fetch).

    Fiscal years are Nepali (e.g. '082-083' = 2025/26). merolagani lists
    some fiscal years twice (e.g. a 0.00% row next to the real one); `seq`
    keeps both, in page order.
    """

    __tablename__ = "market_corporate_action"
    __table_args__ = {"comment": "Cash dividend / bonus / right share history per equity and fiscal year (merolagani)."}

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    action_type: Mapped[str] = mapped_column(Text, primary_key=True, comment="cash_dividend, bonus or right.")
    fiscal_year: Mapped[str] = mapped_column(Text, primary_key=True, comment="Nepali fiscal year, e.g. '082-083'.")
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Order among same-year entries (0 = first listed).")
    value_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Cash dividend / bonus as % of paid-up value; right shares as % (ratio)."
    )
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
