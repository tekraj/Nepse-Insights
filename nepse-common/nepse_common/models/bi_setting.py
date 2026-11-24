from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class BiSetting(Base):
    """Business-intelligence setup for one NEPSE script (stock): which
    analyses the agents run for it, with which indicators/metrics and
    parameters, how often its report refreshes, and which events raise
    notifications. Edited on the dashboard's BI Setup page (api-service ->
    gRPC -> business-intelligence), read by the BI agents.

    The four agents each read their own on/off switch (*_enabled) and their
    own feature map (*_features). A feature map is keyed by the feature ids
    of the BI service's feature catalog (business-intelligence/catalog.py,
    served to the page by the GetCatalog RPC) and holds that feature's
    parameters, e.g. technical_features =
    {"rsi": {"period": 14, "overbought": 70, "oversold": 30},
     "macd": {"fast": 12, "slow": 26, "signal": 9}, "candlestick": {}}.
    A feature absent from the map is off. The catalog validates and fills
    defaults on every save, so the maps only ever hold known ids and typed
    parameters -- adding a feature needs no migration.
    """

    __tablename__ = "bi_setting"
    __table_args__ = {
        "comment": "Business-intelligence setup per script: enabled analyses, indicator/metric parameters, refresh cadence, alerts."
    }

    symbol: Mapped[str] = mapped_column(Text, primary_key=True, comment="Script symbol, as in market_security / market_stock_daily.")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Agents generate and refresh this script's report.")

    # How the summary is framed.
    horizon: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="medium", comment="Investment horizon the summary targets: short (days-weeks), medium (weeks-months), long (months-years)."
    )
    risk_profile: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="moderate", comment="Risk appetite the summary targets: conservative, moderate, aggressive."
    )
    price_basis: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="adjusted", comment="adjusted (bonus/right-adjusted, for indicators and returns) or raw (as traded) prices."
    )
    lookback_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="365", comment="Calendar days of history shown on the report's charts (indicators warm up on longer history)."
    )

    # Refresh cadence (minutes) while a session is live / outside sessions.
    refresh_minutes_live: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15", comment="Report refresh interval during a live session.")
    refresh_minutes_offhours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="240", comment="Report refresh interval outside sessions.")

    # The four specialist agents.
    technical_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Technical-analysis agent runs.")
    fundamental_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Fundamental-analysis agent runs.")
    news_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="News-analysis agent runs.")
    quant_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Quantitative/statistical agent runs.")
    technical_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Technical features on, by catalog id -> parameters (indicators, chart types, levels, patterns)."
    )
    fundamental_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Fundamental features on, by catalog id -> parameters (valuation, dividends, liquidity, sector, brokers)."
    )
    news_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="News features on, by catalog id -> parameters (lookback, sentiment, market-wide news)."
    )
    quant_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Quantitative features on, by catalog id -> parameters (volatility, VaR, beta, jumps, Monte Carlo, ...)."
    )
    news_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"), comment="Extra terms that identify the script in news (e.g. its Nepali name), besides symbol and company name."
    )

    # Notifications.
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="The monitor raises notifications for this script.")
    alert_price_change_pct: Mapped[float] = mapped_column(
        Numeric, nullable=False, server_default="3", comment="Notify when the live price moves at least this % from the previous close."
    )
    alert_volume_spike_ratio: Mapped[float] = mapped_column(
        Numeric, nullable=False, server_default="3", comment="Notify when session volume reaches this multiple of the 20-session average."
    )
    alert_on_signal_change: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Notify when the report's recommendation changes.")
    alert_on_news: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Notify on new news mentioning the script.")

    # Summary.
    llm_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), comment="The LLM writes the summary and rates news; off = rule-based only."
    )
    custom_instructions: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Free-text guidance for the agents (e.g. position held, what to focus on)."
    )

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), comment="Last change; a report older than this is regenerated.")
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Dashboard user (email) who last saved the setup.")
