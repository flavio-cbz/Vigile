from __future__ import annotations

"""add refresh tokens

Revision ID: 002
Revises: 001
Create Date: 2026-05-21 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("issued_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.Float(), nullable=True),
    )
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_table("refresh_tokens")
