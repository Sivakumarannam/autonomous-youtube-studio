"""add_pipeline_and_publish_status

Adds:
  - publishstatus enum + uploads.publish_status column (default 'draft')
  - pipelinestatus enum + pipeline_runs table

Revision ID: 20260703_000000
Revises: 1556a22b425e
Create Date: 2026-07-03 00:00:00.000000+00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "20260703_000000"
down_revision: str = "1556a22b425e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. publishstatus enum + uploads.publish_status column
    #    ALTER TABLE ADD COLUMN cannot create an enum type inline, so we
    #    must create the type explicitly first, then reference it with
    #    create_type=False on the column definition.
    # ------------------------------------------------------------------
    publish_enum = sa.Enum(
        "draft", "approved", "scheduled", "rejected",
        name="publishstatus",
    )
    publish_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "uploads",
        sa.Column(
            "publish_status",
            sa.Enum(
                "draft", "approved", "scheduled", "rejected",
                name="publishstatus",
                create_type=False,  # already created above
            ),
            nullable=False,
            server_default="draft",
        ),
    )

    # ------------------------------------------------------------------
    # 2. pipelinestatus enum + pipeline_runs table
    #    NOTE: no standalone .create() call here. op.create_table() creates
    #    any enum type referenced by its columns as part of the table DDL.
    #    Pre-creating it separately (as with publishstatus above) causes a
    #    DuplicateObjectError here, because create_table() does NOT accept
    #    create_type=False the way ADD COLUMN does — it always attempts to
    #    create the type. Let create_table() own the type creation.
    # ------------------------------------------------------------------
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("script_type", sa.String(10), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "failed", "complete",
                name="pipelinestatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("current_stage", sa.String(50), nullable=True),
        sa.Column("failed_stage", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploads.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index("ix_pipeline_runs_topic_id", "pipeline_runs", ["topic_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("ix_pipeline_runs_created_at", "pipeline_runs", ["created_at"])

    # Composite index for the Scheduler's hot query:
    # WHERE publish_status = 'scheduled' AND scheduled_at <= now()
    op.create_index(
        "ix_uploads_publish_status_scheduled_at",
        "uploads",
        ["publish_status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_created_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_topic_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.execute("DROP TYPE IF EXISTS pipelinestatus")
    op.drop_index("ix_uploads_publish_status_scheduled_at", table_name="uploads")
    op.drop_column("uploads", "publish_status")
    op.execute("DROP TYPE IF EXISTS publishstatus")