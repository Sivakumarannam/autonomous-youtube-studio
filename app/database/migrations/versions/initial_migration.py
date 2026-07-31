"""Initial migration — create all Phase 1 tables.

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000 UTC
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # users                                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(500), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "editor", "viewer", name="userrole"),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ------------------------------------------------------------------ #
    # channels                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("niche", sa.String(255), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column(
            "content_type",
            sa.Enum("shorts", "long", "both", name="contenttype"),
            nullable=False,
            server_default="both",
        ),
        sa.Column(
            "aspect_ratio",
            sa.Enum("9:16", "16:9", name="aspectratio"),
            nullable=False,
            server_default="16:9",
        ),
        sa.Column("target_duration", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("upload_schedule", sa.String(100), nullable=False, server_default="daily"),
        sa.Column("youtube_channel_id", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "paused", "inactive", name="channelstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("config", sa.Text(), nullable=True),
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
    op.create_index("ix_channels_name", "channels", ["name"])
    op.create_index("ix_channels_status", "channels", ["status"])

    # ------------------------------------------------------------------ #
    # topics                                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "google_trends",
                "youtube_trends",
                "reddit",
                "news",
                "manual",
                "feedback",
                name="topicsource",
            ),
            nullable=False,
            server_default="google_trends",
        ),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "researching",
                "scripting",
                "producing",
                "uploading",
                "published",
                "rejected",
                "failed",
                name="topicstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("content_type", sa.String(50), nullable=False, server_default="long"),
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
    op.create_index("ix_topics_channel_id", "topics", ["channel_id"])
    op.create_index("ix_topics_status", "topics", ["status"])
    op.create_index("ix_topics_score", "topics", ["score"])

    # ------------------------------------------------------------------ #
    # research                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "research",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_facts", sa.Text(), nullable=True),
        sa.Column("references", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "complete", "failed", name="researchstatus"),
            nullable=False,
            server_default="pending",
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
    op.create_index("ix_research_topic_id", "research", ["topic_id"])
    op.create_index("ix_research_status", "research", ["status"])

    # ------------------------------------------------------------------ #
    # scripts                                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "scripts",
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
        sa.Column(
            "script_type",
            sa.Enum("short", "long", name="scripttype"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_duration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("seo_title", sa.String(500), nullable=True),
        sa.Column("seo_description", sa.Text(), nullable=True),
        sa.Column("seo_tags", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "approved", "rejected", "producing", "complete",
                name="scriptstatus",
            ),
            nullable=False,
            server_default="draft",
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
    op.create_index("ix_scripts_topic_id", "scripts", ["topic_id"])
    op.create_index("ix_scripts_channel_id", "scripts", ["channel_id"])
    op.create_index("ix_scripts_status", "scripts", ["status"])
    op.create_index("ix_scripts_script_type", "scripts", ["script_type"])


    
    # ------------------------------------------------------------------ #
    # storyboards                                                           #
    # ------------------------------------------------------------------ #

    op.create_table(
        "storyboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("scenes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_storyboards_script_id",
        "storyboards",
        ["script_id"],
    )

    # ------------------------------------------------------------------ #
    # quality_reports                                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        "quality_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("grammar_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fact_consistency_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("retention_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("seo_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("uniqueness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("readability_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "status",
            sa.Enum("passed", "failed", "needs_review", name="qualitystatus"),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_quality_reports_script_id", "quality_reports", ["script_id"])

    # ------------------------------------------------------------------ #
    # videos                                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("audio_path", sa.String(500), nullable=True),
        sa.Column("video_path", sa.String(500), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=False, server_default="1920x1080"),
        sa.Column("duration", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("pending", "generating", "complete", "failed", name="videostatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
    op.create_index("ix_videos_script_id", "videos", ["script_id"])
    op.create_index("ix_videos_status", "videos", ["status"])

    # ------------------------------------------------------------------ #
    # thumbnails                                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "thumbnails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("concept", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "generating", "complete", "failed", name="thumbnailstatus"),
            nullable=False,
            server_default="pending",
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

    # ------------------------------------------------------------------ #
    # uploads                                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("youtube_video_id", sa.String(100), nullable=True),
        sa.Column("youtube_url", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("privacy_status", sa.String(20), nullable=False, server_default="public"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "uploading", "published", "failed", "scheduled",
                name="uploadstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("response_data", sa.Text(), nullable=True),
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
    op.create_index("ix_uploads_youtube_video_id", "uploads", ["youtube_video_id"])
    op.create_index("ix_uploads_status", "uploads", ["status"])

    # ------------------------------------------------------------------ #
    # analytics                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watch_time_minutes", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("average_view_duration", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("average_view_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subscribers_lost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_analytics_upload_id", "analytics", ["upload_id"])
    op.create_index("ix_analytics_snapshot_date", "analytics", ["snapshot_date"])

    # ------------------------------------------------------------------ #
    # agent_logs                                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column(
            "level",
            sa.Enum("debug", "info", "warning", "error", "critical", name="agentloglevel"),
            nullable=False,
            server_default="info",
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("execution_time", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_agent_logs_agent_name", "agent_logs", ["agent_name"])
    op.create_index("ix_agent_logs_level", "agent_logs", ["level"])
    op.create_index("ix_agent_logs_created_at", "agent_logs", ["created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("agent_logs")
    op.drop_table("analytics")
    op.drop_table("uploads")
    op.drop_table("thumbnails")
    op.drop_table("videos")
    op.drop_table("quality_reports")
    op.drop_table("scripts")
    op.drop_table("research")
    op.drop_table("topics")
    op.drop_table("channels")
    op.drop_table("users")

    # Drop custom enum types
    for enum_name in (
        "agentloglevel",
        "uploadstatus",
        "thumbnailstatus",
        "videostatus",
        "qualitystatus",
        "scriptstatus",
        "scripttype",
        "researchstatus",
        "topicstatus",
        "topicsource",
        "channelstatus",
        "aspectratio",
        "contenttype",
        "userrole",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")