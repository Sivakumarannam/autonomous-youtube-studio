"""add instagram fields to uploads

Adds instagram_scheduled_at, instagram_posted, instagram_posted_at,
and instagram_media_id columns to the uploads table for 24-hour
delayed Instagram Reels cross-posting.

Revision ID: b3c4d5e6f7a8
Revises: 720ba5c1665d
Create Date: 2026-07-18 00:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "720ba5c1665d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("uploads")}

    if "instagram_scheduled_at" not in existing:
        op.add_column("uploads", sa.Column("instagram_scheduled_at", sa.DateTime(timezone=True), nullable=True))
    if "instagram_posted" not in existing:
        op.add_column("uploads", sa.Column("instagram_posted", sa.Boolean(), nullable=False, server_default="false"))
    if "instagram_posted_at" not in existing:
        op.add_column("uploads", sa.Column("instagram_posted_at", sa.DateTime(timezone=True), nullable=True))
    if "instagram_media_id" not in existing:
        op.add_column("uploads", sa.Column("instagram_media_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("uploads", "instagram_media_id")
    op.drop_column("uploads", "instagram_posted_at")
    op.drop_column("uploads", "instagram_posted")
    op.drop_column("uploads", "instagram_scheduled_at")
