from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class BiReport(Base):
    """The current business-intelligence report of one script, written by
    the BI master agent. ONE row per script, overwritten in place on every
    regeneration (no history): the four agents' sections, the master's
    synthesis (recommendation, summary, key levels, risks) and the series
    the BI page charts.

    Deleting the script's bi_setting deletes its report.
    """

    __tablename__ = "bi_report"
    __table_args__ = {"comment": "Current BI report per script (one row, overwritten on each regeneration): agent sections + synthesis."}

    symbol: Mapped[str] = mapped_column(
        Text, ForeignKey("bi_setting.symbol", ondelete="CASCADE"), primary_key=True, comment="Script symbol (bi_setting.symbol)."
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, comment="ok, partial (an agent failed; its section carries the error) or failed."
    )
    recommendation: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="strong_buy, buy, hold, sell or strong_sell."
    )
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True, comment="Combined outlook score, -100 (very bearish) .. +100 (very bullish).")
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True, comment="0..1, how strongly the agents agree and how complete their inputs were.")
    headline: Mapped[str | None] = mapped_column(Text, nullable=True, comment="One-line takeaway.")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Overall summary (markdown).")
    synthesis: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, comment="Master agent output: per-area summaries, bullish/bearish factors, key levels, risks, action plan."
    )
    sections: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, comment="Agent outputs keyed technical/fundamental/news/quant: summary, score, signals, metrics, chart series."
    )
    last_price: Mapped[float | None] = mapped_column(Numeric, nullable=True, comment="Price the report was generated at (live last trade or latest close, raw NPR).")
    data_as_of: Mapped[datetime | None] = mapped_column(nullable=True, comment="Time of the newest market data the report used.")
    input_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Fingerprint of the inputs (latest bar/trade, news, setting); an unchanged fingerprint skips regeneration."
    )
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="The LLM wrote the synthesis (false = rule-based).")
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(nullable=False, comment="When this version was written (naive NPT).")
