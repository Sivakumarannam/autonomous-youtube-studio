"""restore_voice_table

Revision ID: 1556a22b425e
Revises: f075aeb4928a
Create Date: 2026-07-02 12:52:38.880543+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1556a22b425e'
down_revision: Union[str, None] = 'f075aeb4928a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Recreate enum types that were dropped by the preceding migration,
    # then rebuild the voices table with the corrected schema.
    # checkfirst=True makes this idempotent — safe on any fresh or
    # partially-migrated database.
    bind = op.get_bind()
    sa.Enum(
        'gtts', 'pyttsx3', 'mock', 'google', 'azure', 'elevenlabs',
        name='voiceprovider',
    ).create(bind, checkfirst=True)
    sa.Enum(
        'pending', 'generating', 'complete', 'failed',
        name='voicestatus',
    ).create(bind, checkfirst=True)

    op.create_table(
        'voices',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('script_id', sa.UUID(), nullable=False),
        sa.Column(
            'provider',
            sa.Enum('gtts', 'pyttsx3', 'mock', 'google', 'azure', 'elevenlabs',
                    name='voiceprovider', create_type=False),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'generating', 'complete', 'failed',
                    name='voicestatus', create_type=False),
            nullable=False,
        ),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('speaker', sa.String(length=100), nullable=True),
        sa.Column('audio_path', sa.String(length=500), nullable=True),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('sample_rate', sa.Integer(), nullable=False),
        sa.Column('bitrate', sa.String(length=20), nullable=False),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['script_id'], ['scripts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('script_id'),
    )


def downgrade() -> None:
    op.drop_table('voices')
