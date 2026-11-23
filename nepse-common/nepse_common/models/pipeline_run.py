from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class PipelineRun(Base):
    """One row per Temporal workflow run (scrapes, sweeps, backfills) --
    what the dashboard's Logs page reads, and the first place to look when a
    dataset stops growing."""

    __tablename__ = "pipeline_run"
    __table_args__ = (
        Index("idx_pipeline_run_started_at", text("started_at DESC")),
        Index("idx_pipeline_run_status", "status"),
        {"comment": "One row per workflow run: status, counts, timing. Read by the dashboard's Logs page."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, comment="'success' or 'failed'.")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    articles_found: Mapped[int | None] = mapped_column(
        Integer, server_default="0", comment="News runs: articles scraped."
    )
    articles_inserted: Mapped[int | None] = mapped_column(
        Integer, server_default="0", comment="News runs: articles newly inserted."
    )
    records_written: Mapped[int | None] = mapped_column(
        Integer, server_default="0", comment="Market runs: rows written."
    )
    source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="What the run used or was: the job's feed (e.g. 'nepalstock_today_price'), the index "
        "fallback that answered, or 'none' (news runs, skipped index runs).",
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
