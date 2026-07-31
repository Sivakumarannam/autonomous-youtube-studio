"""add_retry_columns

Adds retry_count, max_retries, next_retry_at to pipeline_runs and uploads.

These are plain Integer/DateTime columns — NO enum types are created or
referenced, so there is no risk of the DuplicateObjectError that occurred
in Phase 2's migration (which arose from calling enum.create() AND having
create_table() also try to create the same enum type).

Isolation guarantee: server_default="0" on retry_count means every new row
starts at zero regardless of history for the same topic/channel/video.

Revision ID: 20260704_000000
Revises: 20260703_000000
Create Date: 2026-07-04 00:00:00.000000+00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "20260704_000000"
down_revision: str = "20260703_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # pipeline_runs — three plain columns, no enum involvement
    # ------------------------------------------------------------------
    op.add_column(
        "pipeline_runs",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "pipeline_runs",
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "pipeline_runs",
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # uploads — same three columns
    # ------------------------------------------------------------------
    op.add_column(
        "uploads",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "uploads",
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "uploads",
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "next_retry_at")
    op.drop_column("pipeline_runs", "max_retries")
    op.drop_column("pipeline_runs", "retry_count")

    op.drop_column("uploads", "next_retry_at")
    op.drop_column("uploads", "max_retries")
    op.drop_column("uploads", "retry_count")
