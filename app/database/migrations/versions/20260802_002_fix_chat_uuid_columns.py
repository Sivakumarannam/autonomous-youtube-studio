"""fix chat table UUID column types for PostgreSQL

The previous migration created id/session_id columns as VARCHAR(36) but
SQLAlchemy's UUID(as_uuid=True) model type causes asyncpg to cast query
parameters to ::UUID, which PostgreSQL refuses when the column is VARCHAR.
This migration drops and recreates the four chat tables with native UUID
columns on PostgreSQL. On SQLite there is no UUID type and text is fine —
no-op there.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-02 02:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_pg():
        return  # SQLite stores UUIDs as text — already works, nothing to do

    # Drop in reverse-FK order
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("chat_unresolved")
    op.drop_table("knowledge_docs")

    # Recreate with native UUID columns
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_chat_messages_session", "chat_messages", ["session_id"])
    op.create_index("idx_chat_messages_created", "chat_messages", ["created_at"])

    op.create_table(
        "chat_unresolved",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(200), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )

    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("topic_id", sa.String(100), nullable=False, server_default="studio_knowledge"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if not _is_pg():
        return
    op.drop_table("knowledge_docs")
    op.drop_table("chat_unresolved")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
