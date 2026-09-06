from __future__ import annotations

"""create disk_scans_cache table

Revision ID: 010
Revises: 009
Create Date: 2026-09-02 00:00:00.000000

Rationale:
  Multi-path disk scan cache indexed by (node_id, path).
  Avoids bloat on the nodes table and allows independent partition scan caching.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disk_scans_cache",
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("scan_json", sa.Text(), nullable=False),
        sa.Column("scanned_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("node_id", "path"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_disk_scans_cache_node", "disk_scans_cache", ["node_id"])


def downgrade() -> None:
    op.drop_index("idx_disk_scans_cache_node", table_name="disk_scans_cache")
    op.drop_table("disk_scans_cache")
