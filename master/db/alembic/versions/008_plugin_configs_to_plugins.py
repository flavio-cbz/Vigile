"""migrate plugin_configs to plugins table

Revision ID: 008
Revises: 007
Create Date: 2026-07-17 12:00:00.000000

Rationale:
  The legacy plugin_configs table was renamed to plugins in migrations.py
  run_migrations(). This Alembic revision is a historical stub: the actual
  DDL (INSERT...SELECT, DROP TABLE, ADD COLUMN) is performed idempotently
  by the raw-SQL migration runner at startup.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
