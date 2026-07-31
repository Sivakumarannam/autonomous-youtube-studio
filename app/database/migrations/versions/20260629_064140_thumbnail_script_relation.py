"""thumbnail script relation

Revision ID: a245cfb48e3c
Revises: 45d7c2c90c5a
Create Date: 2026-06-29 06:41:40.480844+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a245cfb48e3c'
down_revision: Union[str, None] = '45d7c2c90c5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
