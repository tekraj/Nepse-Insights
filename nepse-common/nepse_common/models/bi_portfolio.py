from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nepse_common.db.base import Base


class BiPortfolio(Base):
    """A dashboard user's latest portfolio optimisation (BI portfolio agent):
    the request (budget, horizon, target return, risk profile, holdings) and
    the result (allocation, share orders, risk analysis). ONE row per user,
    overwritten by each new run; the Portfolio page shows it until the user
    runs a new optimisation."""

    __tablename__ = "bi_portfolio"
    __table_args__ = {"comment": "Latest portfolio optimisation per dashboard user (one row, overwritten): request + result."}

    user_email: Mapped[str] = mapped_column(Text, primary_key=True, comment="Dashboard user (app_user.email / JWT subject).")
    status: Mapped[str] = mapped_column(Text, nullable=False, comment="running, ok or failed.")
    request: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, comment="Budget (NPR), horizon, target return %, risk profile, universe, caps, holdings."
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Allocation, share orders, expected return, risk analysis, frontier, narrative."
    )
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", comment="The LLM wrote the narrative.")
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
