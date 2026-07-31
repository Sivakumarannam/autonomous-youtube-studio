"""add_seo_gate_score_to_scripts

Adds the deterministic SEO gate score column to the scripts table.
This column is written by the rule-based SeoScoringService (no LLM)
and is distinct from SEOAgentService's LLM-assessed overall_seo_score,
which is stored only in agent_logs and never in the scripts table.

Revision ID: a1b2c3d4e5f6
Revises: f075aeb4928a
Create Date: 2026-07-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '20260706_000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scripts',
        sa.Column(
            'seo_gate_score',
            sa.Float(),
            nullable=False,
            server_default='0.0',
        ),
    )


def downgrade() -> None:
    op.drop_column('scripts', 'seo_gate_score')
