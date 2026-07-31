"""add_channel_automation

Phase 6: fully autonomous, indefinite channel-level automation.

Adds:
  - channels.timezone (String(50), default 'UTC') — anchors "what day is
    it for this channel" to the channel's own local day, not server time.
  - channels.is_archived (Boolean, default false) — soft-delete flag for
    the Channel Automation "Delete" action; no related rows are removed.
  - automationstatus enum + channel_automations table (one row per
    channel), tracking Start/Pause/Delete state and the day-counting
    fields that drive the Shorts-only -> Shorts+Long transition.

Revision ID: 20260706_000000
Revises: 20260704_000000
Create Date: 2026-07-06 00:00:00.000000+00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "20260706_000000"
down_revision: str = "20260704_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. channels.timezone / channels.is_archived
    #    Plain column additions — no enum types involved.
    # ------------------------------------------------------------------
    op.add_column(
        "channels",
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="UTC",
        ),
    )
    op.add_column(
        "channels",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ------------------------------------------------------------------
    # 2. automationstatus enum + channel_automations table
    #    NOTE: no standalone .create() call here — same rationale as
    #    pipelinestatus in 20260703_000000: op.create_table() creates any
    #    enum type referenced by its columns as part of the table DDL.
    #    Pre-creating it separately causes a DuplicateObjectError.
    # ------------------------------------------------------------------
    op.create_table(
        "channel_automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "automation_status",
            sa.Enum(
                "stopped", "running", "paused",
                name="automationstatus",
            ),
            nullable=False,
            server_default="stopped",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cumulative_active_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_run_date", sa.Date(), nullable=True),
        sa.Column("last_long_pipeline_date", sa.Date(), nullable=True),
        sa.Column(
            "long_video_interval_days",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_channel_automations_channel_id",
        "channel_automations",
        ["channel_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_channel_automations_channel_id",
        "channel_automations",
        type_="unique",
    )
    op.drop_table("channel_automations")
    op.execute("DROP TYPE IF EXISTS automationstatus")
    op.drop_column("channels", "is_archived")
    op.drop_column("channels", "timezone")