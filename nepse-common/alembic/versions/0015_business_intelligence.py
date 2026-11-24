"""business-intelligence tables: bi_setting, bi_report, bi_notification

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-23

The business-intelligence service (business-intelligence/) runs four
specialist agents (technical, fundamental, news, quantitative) and a master
agent over the scripts a dashboard user set up:

  bi_setting       one row per script: which analyses run, with which
                   indicator/metric parameters (JSONB maps keyed by the BI
                   feature catalog), refresh cadence, alert thresholds.
  bi_report        the script's current report, ONE row overwritten on each
                   regeneration (no history).
  bi_notification  alerts raised by the automation (append-only, deduped).

The agents only compute: every input comes from the database (prices,
floor sheet, news, and the fundamentals nepse-service scrapes into
market_fundamental_daily / market_corporate_action, revision 0014), and
every result is stored in bi_report.

Purely additive, safe to run while the workers are up.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EMPTY_JSONB = sa.text("'{}'::jsonb")
_TRUE = sa.text("true")


def upgrade() -> None:
    op.create_table(
        "bi_setting",
        sa.Column("symbol", sa.Text(), primary_key=True, comment="Script symbol, as in market_security / market_stock_daily."),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Agents generate and refresh this script's report."),
        sa.Column("horizon", sa.Text(), nullable=False, server_default="medium",
                  comment="Investment horizon the summary targets: short (days-weeks), medium (weeks-months), long (months-years)."),
        sa.Column("risk_profile", sa.Text(), nullable=False, server_default="moderate",
                  comment="Risk appetite the summary targets: conservative, moderate, aggressive."),
        sa.Column("price_basis", sa.Text(), nullable=False, server_default="adjusted",
                  comment="adjusted (bonus/right-adjusted, for indicators and returns) or raw (as traded) prices."),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="365",
                  comment="Calendar days of history shown on the report's charts (indicators warm up on longer history)."),
        sa.Column("refresh_minutes_live", sa.Integer(), nullable=False, server_default="15", comment="Report refresh interval during a live session."),
        sa.Column("refresh_minutes_offhours", sa.Integer(), nullable=False, server_default="240", comment="Report refresh interval outside sessions."),
        sa.Column("technical_enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Technical-analysis agent runs."),
        sa.Column("fundamental_enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Fundamental-analysis agent runs."),
        sa.Column("news_enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="News-analysis agent runs."),
        sa.Column("quant_enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Quantitative/statistical agent runs."),
        sa.Column("technical_features", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSONB,
                  comment="Technical features on, by catalog id -> parameters (indicators, chart types, levels, patterns)."),
        sa.Column("fundamental_features", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSONB,
                  comment="Fundamental features on, by catalog id -> parameters (valuation, dividends, liquidity, sector, brokers)."),
        sa.Column("news_features", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSONB,
                  comment="News features on, by catalog id -> parameters (lookback, sentiment, market-wide news)."),
        sa.Column("quant_features", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSONB,
                  comment="Quantitative features on, by catalog id -> parameters (volatility, VaR, beta, jumps, Monte Carlo, ...)."),
        sa.Column("news_keywords", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]"),
                  comment="Extra terms that identify the script in news (e.g. its Nepali name), besides symbol and company name."),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=_TRUE, comment="The monitor raises notifications for this script."),
        sa.Column("alert_price_change_pct", sa.Numeric(), nullable=False, server_default="3",
                  comment="Notify when the live price moves at least this % from the previous close."),
        sa.Column("alert_volume_spike_ratio", sa.Numeric(), nullable=False, server_default="3",
                  comment="Notify when session volume reaches this multiple of the 20-session average."),
        sa.Column("alert_on_signal_change", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Notify when the report's recommendation changes."),
        sa.Column("alert_on_news", sa.Boolean(), nullable=False, server_default=_TRUE, comment="Notify on new news mentioning the script."),
        sa.Column("llm_summary_enabled", sa.Boolean(), nullable=False, server_default=_TRUE,
                  comment="Claude writes the summary; off = rule-based summary only."),
        sa.Column("custom_instructions", sa.Text(), nullable=True, comment="Free-text guidance for the agents (e.g. position held, what to focus on)."),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last change; a report older than this is regenerated."),
        sa.Column("updated_by", sa.Text(), nullable=True, comment="Dashboard user (email) who last saved the setup."),
        comment="Business-intelligence setup per script: enabled analyses, indicator/metric parameters, refresh cadence, alerts.",
    )

    op.create_table(
        "bi_report",
        sa.Column("symbol", sa.Text(), sa.ForeignKey("bi_setting.symbol", ondelete="CASCADE"), primary_key=True,
                  comment="Script symbol (bi_setting.symbol)."),
        sa.Column("status", sa.Text(), nullable=False, comment="ok, partial (an agent failed; its section carries the error) or failed."),
        sa.Column("recommendation", sa.Text(), nullable=True, comment="strong_buy, buy, hold, sell or strong_sell."),
        sa.Column("score", sa.Numeric(), nullable=True, comment="Combined outlook score, -100 (very bearish) .. +100 (very bullish)."),
        sa.Column("confidence", sa.Numeric(), nullable=True, comment="0..1, how strongly the agents agree and how complete their inputs were."),
        sa.Column("headline", sa.Text(), nullable=True, comment="One-line takeaway."),
        sa.Column("summary", sa.Text(), nullable=True, comment="Overall summary (markdown)."),
        sa.Column("synthesis", postgresql.JSONB(), nullable=False,
                  comment="Master agent output: per-area summaries, bullish/bearish factors, key levels, risks, action plan."),
        sa.Column("sections", postgresql.JSONB(), nullable=False,
                  comment="Agent outputs keyed technical/fundamental/news/quant: summary, score, signals, metrics, chart series."),
        sa.Column("last_price", sa.Numeric(), nullable=True, comment="Price the report was generated at (live last trade or latest close, raw NPR)."),
        sa.Column("data_as_of", sa.DateTime(), nullable=True, comment="Time of the newest market data the report used."),
        sa.Column("input_hash", sa.Text(), nullable=True,
                  comment="Fingerprint of the inputs (latest bar/trade, news, setting); an unchanged fingerprint skips regeneration."),
        sa.Column("llm_used", sa.Boolean(), nullable=False, comment="Claude wrote the synthesis (false = rule-based)."),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("generation_ms", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False, comment="When this version was written (naive NPT)."),
        comment="Current BI report per script (one row, overwritten on each regeneration): agent sections + synthesis.",
    )

    op.create_table(
        "bi_notification",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text(), nullable=True, comment="Script the alert is about; NULL = market-wide."),
        sa.Column("kind", sa.Text(), nullable=False, comment="price_move, volume_spike, news, recommendation_change, signal, report_failed."),
        sa.Column("severity", sa.Text(), nullable=False, comment="info, warning or critical."),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=_EMPTY_JSONB,
                  comment="Event details (prices, article ids, old/new recommendation)."),
        sa.Column("dedupe_key", sa.Text(), nullable=False, comment="Identifies the event; a second alert for the same key is dropped."),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(), nullable=True, comment="When a dashboard user marked it read; NULL = unread."),
        sa.UniqueConstraint("dedupe_key", name="bi_notification_dedupe_key_key"),
        comment="Alerts raised by the BI automation (price moves, volume spikes, news, recommendation changes).",
    )
    op.create_index("idx_bi_notification_created_at", "bi_notification", [sa.text("created_at DESC")])
    op.create_index("idx_bi_notification_symbol_created_at", "bi_notification", ["symbol", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_bi_notification_symbol_created_at", table_name="bi_notification")
    op.drop_index("idx_bi_notification_created_at", table_name="bi_notification")
    op.drop_table("bi_notification")
    op.drop_table("bi_report")
    op.drop_table("bi_setting")
