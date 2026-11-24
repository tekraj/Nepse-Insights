"""company fundamentals: market_fundamental_daily, market_corporate_action

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-23

Fundamentals scraped by nepse-service's CompanyFundamentalsWorkflow from
merolagani's company pages (daily after the close): one row per equity and
session with EPS, P/E, book value, P/BV, dividend, market cap..., and the
company's cash dividend / bonus / right history per fiscal year. Input of
the business-intelligence fundamental agent, and research data in itself
(P/E and P/BV time series).

Purely additive, safe to run while the workers are up.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_fundamental_daily",
        sa.Column("symbol", sa.Text(), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True, comment="Session the figures belong to (merolagani's 'Last Traded On')."),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("market_price", sa.Float(), nullable=True, comment="Price merolagani computed the ratios with (raw NPR)."),
        sa.Column("eps", sa.Float(), nullable=True, comment="Annualised earnings per share of the latest reported quarter (NPR)."),
        sa.Column("eps_period", sa.Text(), nullable=True, comment="Report the EPS comes from, e.g. 'FY:083-084, Q:1' (Nepali fiscal year)."),
        sa.Column("pe_ratio", sa.Float(), nullable=True, comment="market_price / eps."),
        sa.Column("book_value", sa.Float(), nullable=True, comment="Book value per share (NPR)."),
        sa.Column("pbv", sa.Float(), nullable=True, comment="Price / book value."),
        sa.Column("cash_dividend_pct", sa.Float(), nullable=True, comment="Latest cash dividend, % of paid-up value."),
        sa.Column("bonus_pct", sa.Float(), nullable=True, comment="Latest bonus share issue, %."),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True, comment="Market capitalisation (NPR)."),
        sa.Column("paidup_value", sa.Float(), nullable=True, comment="Paid-up value per share (NPR, usually 100)."),
        sa.Column("high_52w", sa.Float(), nullable=True),
        sa.Column("low_52w", sa.Float(), nullable=True),
        sa.Column("avg_120d", sa.Float(), nullable=True, comment="120-day average price."),
        sa.Column("avg_180d", sa.Float(), nullable=True, comment="180-day average price."),
        sa.Column("yield_1y_pct", sa.Float(), nullable=True, comment="merolagani's 1-year yield (price return), %."),
        sa.Column("avg_volume_30d", sa.Float(), nullable=True, comment="30-day average volume (shares)."),
        sa.Column("source", sa.Text(), nullable=False, server_default="merolagani"),
        sa.Column("scraped_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        comment="Company fundamentals per equity and trading day (merolagani): EPS, P/E, book value, P/BV, dividend, market cap.",
    )
    op.create_index("idx_market_fundamental_daily_trade_date", "market_fundamental_daily", ["trade_date"])

    op.create_table(
        "market_corporate_action",
        sa.Column("symbol", sa.Text(), primary_key=True),
        sa.Column("action_type", sa.Text(), primary_key=True, comment="cash_dividend, bonus or right."),
        sa.Column("fiscal_year", sa.Text(), primary_key=True, comment="Nepali fiscal year, e.g. '082-083'."),
        sa.Column("seq", sa.Integer(), primary_key=True, comment="Order among same-year entries (0 = first listed)."),
        sa.Column("value_pct", sa.Float(), nullable=True, comment="Cash dividend / bonus as % of paid-up value; right shares as % (ratio)."),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        comment="Cash dividend / bonus / right share history per equity and fiscal year (merolagani).",
    )


def downgrade() -> None:
    op.drop_table("market_corporate_action")
    op.drop_index("idx_market_fundamental_daily_trade_date", table_name="market_fundamental_daily")
    op.drop_table("market_fundamental_daily")
