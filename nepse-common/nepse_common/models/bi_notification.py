from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class BiNotification(Base):
    """One alert raised by the BI automation (price move, volume spike,
    new news, recommendation change, ...), shown in the dashboard's
    notification bell. Append-only; dedupe_key makes each event notify
    once (e.g. one price-move alert per script, session and threshold step).
    """

    __tablename__ = "bi_notification"
    __table_args__ = (
        Index("idx_bi_notification_created_at", text("created_at DESC")),
        Index("idx_bi_notification_symbol_created_at", "symbol", text("created_at DESC")),
        {"comment": "Alerts raised by the BI automation (price moves, volume spikes, news, recommendation changes)."},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Script the alert is about; NULL = market-wide.")
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, comment="price_move, volume_spike, news, recommendation_change, signal, report_failed."
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False, comment="info, warning or critical.")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Event details (prices, article ids, old/new recommendation).")
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, comment="Identifies the event; a second alert for the same key is dropped.")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="When a dashboard user marked it read; NULL = unread.")
