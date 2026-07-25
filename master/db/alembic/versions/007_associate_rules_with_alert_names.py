from __future__ import annotations

"""associate rules with alert names

Revision ID: 007
Revises: 006
Create Date: 2026-07-17 00:00:00.000000

Rationale:
  Rules are associated with alert names instead of raw thresholds.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We can perform any database operations if needed, but since it's sqlite and we manage dynamic schema changes in migrations.py, this can be empty or print.
    pass


def downgrade() -> None:
    pass
