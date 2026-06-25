"""drop FK join_tokens.node_id (allow pre-enrollment rows)

Revision ID: 006
Revises: 005
Create Date: 2026-06-25 12:00:00.000000

Rationale:
  A `join_token` row now exists before the corresponding `nodes` row.
  The Worker enrollment handshake is what creates the `nodes` row.
  Until the Worker connects, only the `join_tokens` row exists (with no
  matching `nodes.id`). The FK constraint is therefore dropped.

  The application guarantees cleanup of orphaned `join_tokens` via
  `JOIN_TOKEN_TTL` (default 1800s) — expired rows are simply never read.

  Other FKs referencing `nodes.id` (worker_tokens, metrics_snapshots,
  action_proposals) are preserved — they only ever point to *real* nodes.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("join_tokens", schema=None) as batch_op:
        batch_op.drop_constraint("fk_join_tokens_node_id_nodes", type_="foreignkey")


def downgrade() -> None:
    with op.batch_alter_table("join_tokens", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_join_tokens_node_id_nodes",
            "nodes",
            ["node_id"],
            ["id"],
            ondelete="CASCADE",
        )
