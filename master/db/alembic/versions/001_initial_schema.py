"""initial schema

Revision ID: 001
Revises: None
Create Date: 2026-05-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nodes
    op.create_table(
        'nodes',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('hostname', sa.String(), nullable=True),
        sa.Column('machine_id', sa.String(), nullable=True),
        sa.Column('arch', sa.String(), nullable=True),
        sa.Column('os', sa.String(), nullable=True),
        sa.Column('public_key', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('ip_prefix', sa.String(), nullable=True),
        sa.Column('last_heartbeat', sa.Float(), nullable=True),
        sa.Column('enrolled_at', sa.Float(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_nodes_state', 'nodes', ['state'])

    # join_tokens
    op.create_table(
        'join_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('node_id', sa.String(), sa.ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('payload_b64', sa.String(), nullable=False),
        sa.Column('consumed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_join_tokens_node_id', 'join_tokens', ['node_id'])
    op.create_index('idx_join_tokens_consumed', 'join_tokens', ['consumed', 'expires_at'])

    # worker_tokens
    op.create_table(
        'worker_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('node_id', sa.String(), sa.ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('issued_at', sa.Float(), nullable=False),
        sa.Column('rotation_due', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('revoked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('revoked_at', sa.Float(), nullable=True),
        sa.Column('revoked_by', sa.String(), nullable=True)
    )
    op.create_index('idx_worker_tokens_node_id', 'worker_tokens', ['node_id'])
    op.create_index('idx_worker_tokens_hash', 'worker_tokens', ['token_hash'])

    # users
    op.create_table(
        'users',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('username', sa.String(), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.Column('last_login', sa.Float(), nullable=True)
    )

    # audit_log
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('sequence', sa.Integer(), nullable=False, unique=True),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=True),
        sa.Column('details_json', sa.String(), nullable=False, server_default='{}'),
        sa.Column('previous_hash', sa.String(), nullable=False),
        sa.Column('entry_hash', sa.String(), nullable=False, unique=True)
    )
    op.create_index('idx_audit_log_sequence', 'audit_log', ['sequence'])
    op.create_index('idx_audit_log_node_id', 'audit_log', ['node_id'])
    op.create_index('idx_audit_log_user_id', 'audit_log', ['user_id'])

    # metrics_snapshots
    op.create_table(
        'metrics_snapshots',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('node_id', sa.String(), sa.ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('collected_at', sa.Float(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=False, server_default='0'),
        sa.Column('cpu_load_1m', sa.Float(), nullable=True),
        sa.Column('cpu_load_5m', sa.Float(), nullable=True),
        sa.Column('cpu_load_15m', sa.Float(), nullable=True),
        sa.Column('cpu_cores', sa.Integer(), nullable=True),
        sa.Column('mem_total_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mem_used_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mem_percent', sa.Float(), nullable=False, server_default='0'),
        sa.Column('swap_total_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('swap_used_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('disk_total_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('disk_used_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('disk_percent', sa.Float(), nullable=False, server_default='0'),
        sa.Column('uptime_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('processes', sa.Integer(), nullable=True)
    )
    op.create_index('idx_metrics_snapshots_node_time', 'metrics_snapshots', ['node_id', 'collected_at'])

    # action_proposals
    op.create_table(
        'action_proposals',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('node_id', sa.String(), sa.ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('params_json', sa.String(), nullable=False, server_default='{}'),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column('risk_level', sa.String(), nullable=False, server_default='MEDIUM'),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('rejected_by', sa.String(), nullable=True),
        sa.Column('rejection_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.Column('executed_at', sa.Float(), nullable=True),
        sa.Column('result_json', sa.String(), nullable=True)
    )
    op.create_index('idx_proposals_status', 'action_proposals', ['status'])
    op.create_index('idx_proposals_node', 'action_proposals', ['node_id'])


def downgrade() -> None:
    op.drop_table('action_proposals')
    op.drop_table('metrics_snapshots')
    op.drop_table('audit_log')
    op.drop_table('users')
    op.drop_table('worker_tokens')
    op.drop_table('join_tokens')
    op.drop_table('nodes')
