"""add group and disabled columns

Revision ID: 005
Revises: 004
Create Date: 2026-06-19 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("node_group", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("disabled", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("idx_nodes_group", "nodes", ["node_group"], if_not_exists=True)
    op.create_index("idx_nodes_disabled", "nodes", ["disabled"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_nodes_disabled", table_name="nodes")
    op.drop_index("idx_nodes_group", table_name="nodes")
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_column("disabled")
        batch_op.drop_column("node_group")
