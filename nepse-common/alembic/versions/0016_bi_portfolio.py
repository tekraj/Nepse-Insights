"""bi_portfolio: latest portfolio optimisation per user; generic-LLM comments

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-23

The BI portfolio agent (budget + horizon + target return -> lowest-risk
allocation with risk analysis) caches each user's latest result here: one
row per user, overwritten by the next run, shown on the Portfolio page until
then.

The agents moved from the Anthropic SDK to a generic OpenAI-compatible
client, so two column comments from 0015 that named Claude are reworded.

Additive (plus comment changes), safe while the workers run.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bi_portfolio",
        sa.Column("user_email", sa.Text(), primary_key=True, comment="Dashboard user (app_user.email / JWT subject)."),
        sa.Column("status", sa.Text(), nullable=False, comment="running, ok or failed."),
        sa.Column("request", postgresql.JSONB(), nullable=False,
                  comment="Budget (NPR), horizon, target return %, risk profile, universe, caps, holdings."),
        sa.Column("result", postgresql.JSONB(), nullable=True,
                  comment="Allocation, share orders, expected return, risk analysis, frontier, narrative."),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("llm_used", sa.Boolean(), nullable=False, server_default=sa.text("false"), comment="The LLM wrote the narrative."),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("generation_ms", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        comment="Latest portfolio optimisation per dashboard user (one row, overwritten): request + result.",
    )
    op.alter_column("bi_setting", "llm_summary_enabled", existing_type=sa.Boolean(), existing_nullable=False,
                    comment="The LLM writes the summary and rates news; off = rule-based only.",
                    existing_comment="Claude writes the summary; off = rule-based summary only.")
    op.alter_column("bi_report", "llm_used", existing_type=sa.Boolean(), existing_nullable=False,
                    comment="The LLM wrote the synthesis (false = rule-based).",
                    existing_comment="Claude wrote the synthesis (false = rule-based).")


def downgrade() -> None:
    op.alter_column("bi_report", "llm_used", existing_type=sa.Boolean(), existing_nullable=False,
                    comment="Claude wrote the synthesis (false = rule-based).",
                    existing_comment="The LLM wrote the synthesis (false = rule-based).")
    op.alter_column("bi_setting", "llm_summary_enabled", existing_type=sa.Boolean(), existing_nullable=False,
                    comment="Claude writes the summary; off = rule-based summary only.",
                    existing_comment="The LLM writes the summary and rates news; off = rule-based only.")
    op.drop_table("bi_portfolio")
