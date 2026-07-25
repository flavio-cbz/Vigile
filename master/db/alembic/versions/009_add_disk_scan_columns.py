from __future__ import annotations

"""add disk scan cache columns to nodes

Revision ID: 009
Revises: 008
Create Date: 2026-07-18 00:00:00.000000

Rationale:
  Cache disk scan results per node to avoid repeated full disk scans.
  cached_disk_scan_json holds the serialized scan payload.
  cached_disk_scan_at holds the UNIX timestamp of the last scan.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cached_disk_scan_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cached_disk_scan_at", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("nodes", schema=None) as batch_op:
        batch_op.drop_column("cached_disk_scan_at")
        batch_op.drop_column("cached_disk_scan_json")
