from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Double, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class MarketTrade(Base):
    """One row per executed trade (NEPSE's "floor sheet"). Unlike the
    snapshot tables, trades have a real natural key (contract_id is unique
    per trading day on NEPSE), so writes upsert on (contract_id, trade_date):
    a scrape that re-fetches overlapping rows never inserts duplicates.

    Broker fields (buyer/seller broker code + name) are NULL in every
    response NEPSE serves while the market is open -- it only publishes them
    after the 15:00 close. The 1-minute intraday scrape therefore stores
    them NULL, and NepseFloorSheetEodSweepWorkflow re-reads the whole day's
    floor sheet after the close and fills them in (and inserts any trades
    the 500-row-per-minute intraday scrape missed). Past sessions are
    completed from merolagani by FloorSheetHistoryBackfillWorkflow; trades
    it inserts have no trade_time, security_id or trade_book_id. Broker
    codes are the closest thing NEPSE exposes to agent-level positions (the
    MFG part of the research)."""

    __tablename__ = "market_trade"
    __table_args__ = (
        UniqueConstraint("contract_id", "trade_date", name="uq_market_trade_contract_id_trade_date"),
        Index("idx_market_trade_scraped_at", "scraped_at"),
        Index("idx_market_trade_symbol", "symbol"),
        Index("idx_market_trade_trade_date", "trade_date"),
        {"comment": "Every executed trade (NEPSE floor sheet) with buyer/seller broker codes."},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="NEPSE contract number, unique per trade_date.")
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    security_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="NEPSE security id (market_security); NULL on merolagani-backfilled trades."
    )
    trade_book_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    buyer_broker_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Buying broker's number (market_broker.broker_code); NULL until after the close."
    )
    seller_broker_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Selling broker's number (market_broker.broker_code); NULL until after the close."
    )
    buyer_broker_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_broker_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Shares traded.")
    price: Mapped[float | None] = mapped_column(Double, nullable=True, comment="Price per share in NPR (NEPSE contractRate).")
    amount: Mapped[float | None] = mapped_column(Double, nullable=True, comment="quantity x price, in NPR.")
    trade_date: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Session date as 'YYYY-MM-DD' text (NEPSE businessDate)."
    )
    trade_time: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Execution time as ISO text, microseconds; NULL on merolagani-backfilled trades."
    )
    scraped_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
