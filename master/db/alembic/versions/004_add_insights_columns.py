"""add insights columns

Revision ID: 004
Revises: 003
Create Date: 2026-05-25 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("insight_profile", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("insight_profile_generated_at", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("cached_services_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cached_containers_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_column("insight_profile")
        batch_op.drop_column("insight_profile_generated_at")
        batch_op.drop_column("cached_services_json")
        batch_op.drop_column("cached_containers_json")
