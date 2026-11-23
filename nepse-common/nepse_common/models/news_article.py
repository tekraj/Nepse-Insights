from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class NewsArticle(Base):
    """One row per news article scraped from the ~20 Nepali portals (live
    scrapes and historical backfills), deduplicated by url."""

    __tablename__ = "news_article"
    __table_args__ = (
        Index("idx_news_article_scraped_at", "scraped_at"),
        Index("idx_news_article_source", "source"),
        Index("idx_news_article_portal_tier", "portal_tier"),
        {"comment": "News articles from Nepali portals (live + historical backfill), unique by url."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, comment="Portal key, e.g. 'sharesansar'.")
    portal_tier: Mapped[str] = mapped_column(Text, nullable=False, comment="'finance' or 'general'.")
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    # Incremented by NepseNewsFieldsBackfillTickWorkflow on every claim
    # that does NOT result in a real update (no_new_data / fetch_failed) --
    # a row whose content is genuinely unfixable (e.g. a nepalipaisa
    # article that's only a video embed, no text) would otherwise be
    # re-claimed first forever (lowest id wins ties), permanently blocking
    # every other row behind it. Once this hits
    # nepse_news_fields_backfill_activities.MAX_BACKFILL_ATTEMPTS the row
    # is excluded from future claims.
    fields_backfill_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Failed attempts to repair a missing published_at/body; capped so unfixable rows are skipped.",
    )
