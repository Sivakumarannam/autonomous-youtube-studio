"""add chat models for Studio Assistant chatbot

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-02 01:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "chat_sessions" not in existing_tables:
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "chat_messages" not in existing_tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("sources_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_chat_messages_session", "chat_messages", ["session_id"])
        op.create_index("idx_chat_messages_created", "chat_messages", ["created_at"])

    if "chat_unresolved" not in existing_tables:
        op.create_table(
            "chat_unresolved",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("context_snapshot", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", sa.String(200), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
        )

    if "knowledge_docs" not in existing_tables:
        op.create_table(
            "knowledge_docs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("source_type", sa.String(50), nullable=False, server_default="manual"),
            sa.Column("topic_id", sa.String(100), nullable=False, server_default="studio_knowledge"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("knowledge_docs")
    op.drop_table("chat_unresolved")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
