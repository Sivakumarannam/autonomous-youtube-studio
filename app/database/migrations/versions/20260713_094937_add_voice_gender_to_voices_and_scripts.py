"""add voice_gender to voices and scripts

Revision ID: 720ba5c1665d
Revises: 9867e4d709e3
Create Date: 2026-07-13 09:49:37.675091+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "720ba5c1665d"
down_revision: Union[str, None] = "9867e4d709e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add to scripts (nullable if existing scripts don't yet have a value)
    op.add_column(
        "scripts",
        sa.Column("voice_gender", sa.String(length=20), nullable=True),
    )

    # Add to voices as nullable first
    op.add_column(
        "voices",
        sa.Column("voice_gender", sa.String(length=20), nullable=True),
    )

    # Populate existing rows
    op.execute("""
        UPDATE voices
        SET voice_gender = 'female'
        WHERE voice_gender IS NULL
    """)

    # Make NOT NULL
    op.alter_column(
        "voices",
        "voice_gender",
        existing_type=sa.String(length=20),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("voices", "voice_gender")
    op.drop_column("scripts", "voice_gender")