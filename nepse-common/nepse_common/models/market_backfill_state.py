from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketBackfillState(Base):
    """Resume point per (dataset, item_key) for the market-data history
    backfills in nepse-service (research_data_activities.py and the
    floor-sheet history backfill), so a worker restart or a weekly re-run
    continues where the last one stopped instead of re-downloading years of
    data.

    dataset values:
      "intraday"           -- item_key = symbol: intraday ticks.
                              oldest_covered / newest_covered bound the
                              window already fetched; exhausted = walked back
                              to INTRADAY_BACKFILL_START_DATE.
      "daily_full_refresh" -- item_key "*": last_run_at of the last complete
                              merolagani daily-history refresh (raw +
                              adjusted) across all equities.
      "floorsheet_history" -- item_key = session date 'YYYY-MM-DD':
                              exhausted once that session's trades were
                              completed from merolagani; rows_written =
                              merolagani's listed trade count.
    """

    __tablename__ = "market_backfill_state"
    __table_args__ = {"comment": "Resume cursors of the market-data history backfills (intraday ticks, daily refresh, floor sheet)."}

    dataset: Mapped[str] = mapped_column(Text, primary_key=True)
    item_key: Mapped[str] = mapped_column(
        Text, primary_key=True, comment="Symbol (intraday), '*' (daily_full_refresh) or session date (floorsheet_history)."
    )
    oldest_covered: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    newest_covered: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exhausted: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    rows_written: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(server_default=func.now(), onupdate=func.now())
