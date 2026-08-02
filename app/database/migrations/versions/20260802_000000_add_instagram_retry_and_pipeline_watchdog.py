"""add instagram retry cap columns to uploads

Adds instagram_retry_count and instagram_failed_permanently to the uploads
table so the Instagram cross-post scheduler can enforce a hard 3-attempt cap
and stop retrying permanently failed posts (audit gap A fix).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-02 00:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("uploads")}

    if "instagram_retry_count" not in existing:
        op.add_column(
            "uploads",
            sa.Column(
                "instagram_retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "instagram_failed_permanently" not in existing:
        op.add_column(
            "uploads",
            sa.Column(
                "instagram_failed_permanently",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    op.drop_column("uploads", "instagram_failed_permanently")
    op.drop_column("uploads", "instagram_retry_count")
