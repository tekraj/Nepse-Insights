from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class NewsBackfillUrl(Base):
    """One row per candidate article URL discovered from a portal's sitemap
    (or other bulk-discovery mechanism), acting as the work queue for the
    per-portal 1-request-per-minute historical news backfill tickers.

    status values: "pending" (discovered, not yet fetched, or reset for
    retry after a transient failure or a stale claim), "processing"
    (claimed by a ticker, fetch in flight -- see claimed_at), "inserted"
    (fetched, published_at fell in range, written to news_article),
    "out_of_range" (fetched, published_at outside [2021-01-01, 2026-06-29]
    or missing), "failed" (fetch/parse error that exhausted its retry
    attempts -- terminal, not retried further; see attempt_count /
    MAX_FETCH_ATTEMPTS in the sitemap/cursor backfill activities).
    """

    __tablename__ = "news_backfill_url"
    __table_args__ = (
        UniqueConstraint("source", "url", name="uq_news_backfill_url_source_url"),
        Index("idx_news_backfill_url_source_status", "source", "status"),
        Index("idx_news_backfill_url_source_status_rank", "source", "status", "discovery_rank"),
        {"comment": "Work queue of discovered article URLs for the historical news backfill."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, comment="Portal key, as in news_article.source.")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="pending",
        comment="pending / processing / inserted / out_of_range / failed.",
    )
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    # Coarse "how old is this URL likely to be" signal captured at discovery
    # time, higher = likely older, used to claim probably-older URLs first.
    # Only meaningful for portals whose sitemap chunks are reliably ordered
    # by age (karobardaily's post-sitemapN.xml files: N=1 is newest, higher
    # N is older, confirmed reaching back to 2020 at N~408). 0/NULL for
    # portals with no such reliable signal (myrepublica's bulk sitemap
    # files aren't cleanly date-ordered; sharesansar doesn't use this table
    # column at all, its own listing-page date is used directly instead).
    discovery_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="Higher = probably older; claimed first."
    )
