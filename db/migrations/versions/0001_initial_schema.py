"""Initial schema — the eight tables from GP-plan §5.2.

Additions beyond the plan (see docs/DECISIONS.md, INF-04 and INF-05):
- execution_runs.graph_snapshot: the graph as it was when Run was pressed.
- execution_logs.node_id references that snapshot (not agent_nodes); agent_type and
  position_order are copied onto the log row so history survives workflow edits.
- agent_nodes.agent_type is text, not an enum, so a new agent needs no migration (AT-12).

Revision ID: 0001
Revises: 
Create Date: 2026-09-14 21:50:40.009249
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('credentials',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('encrypted_payload', sa.LargeBinary(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_credentials_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credentials'))
    )
    op.create_index(op.f('ix_credentials_user_id'), 'credentials', ['user_id'], unique=False)
    op.create_table('workflows',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('graph_definition', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='draft', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_workflows_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflows'))
    )
    op.create_index(op.f('ix_workflows_user_id'), 'workflows', ['user_id'], unique=False)
    op.create_table('agent_nodes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workflow_id', sa.Uuid(), nullable=False),
    sa.Column('agent_type', sa.String(length=64), nullable=False),
    sa.Column('configuration', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('position_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], name=op.f('fk_agent_nodes_workflow_id_workflows'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_nodes')),
    sa.UniqueConstraint('workflow_id', 'position_order', name='uq_agent_nodes_workflow_position')
    )
    op.create_index(op.f('ix_agent_nodes_workflow_id'), 'agent_nodes', ['workflow_id'], unique=False)
    op.create_table('execution_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workflow_id', sa.Uuid(), nullable=False),
    sa.Column('triggered_by', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'awaiting_approval', 'succeeded', 'failed', 'cancelled', name='run_status'), server_default='queued', nullable=False),
    sa.Column('graph_snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('total_nodes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('failed_nodes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], name=op.f('fk_execution_runs_triggered_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], name=op.f('fk_execution_runs_workflow_id_workflows'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_runs'))
    )
    op.create_index(op.f('ix_execution_runs_workflow_id'), 'execution_runs', ['workflow_id'], unique=False)
    op.create_table('execution_logs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('workflow_id', sa.Uuid(), nullable=False),
    sa.Column('node_id', sa.Uuid(), nullable=False),
    sa.Column('agent_type', sa.String(length=64), nullable=False),
    sa.Column('position_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'retrying', 'awaiting_approval', 'success', 'failed', 'skipped', name='node_status'), server_default='pending', nullable=False),
    sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.CheckConstraint('retry_count >= 0 AND retry_count <= 3', name=op.f('ck_execution_logs_retry_count_range')),
    sa.ForeignKeyConstraint(['run_id'], ['execution_runs.id'], name=op.f('fk_execution_logs_run_id_execution_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], name=op.f('fk_execution_logs_workflow_id_workflows'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_logs')),
    sa.UniqueConstraint('run_id', 'node_id', name='uq_execution_logs_run_node')
    )
    op.create_index('ix_execution_logs_run_started', 'execution_logs', ['run_id', 'started_at'], unique=False)
    op.create_index(op.f('ix_execution_logs_status'), 'execution_logs', ['status'], unique=False)
    op.create_table('agent_outputs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('log_id', sa.Uuid(), nullable=False),
    sa.Column('output_type', sa.Enum('text', 'file', 'url', name='output_type'), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('content_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('storage_path', sa.Text(), nullable=True),
    sa.Column('mime_type', sa.String(length=127), nullable=True),
    sa.Column('bytes', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['log_id'], ['execution_logs.id'], name=op.f('fk_agent_outputs_log_id_execution_logs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_outputs'))
    )
    op.create_index(op.f('ix_agent_outputs_log_id'), 'agent_outputs', ['log_id'], unique=False)
    op.create_table('approvals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('log_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.Enum('approve', 'reject', name='approval_decision'), nullable=False),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_approvals_decided_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['log_id'], ['execution_logs.id'], name=op.f('fk_approvals_log_id_execution_logs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approvals'))
    )
    op.create_index(op.f('ix_approvals_log_id'), 'approvals', ['log_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_approvals_log_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_agent_outputs_log_id'), table_name='agent_outputs')
    op.drop_table('agent_outputs')
    op.drop_index(op.f('ix_execution_logs_status'), table_name='execution_logs')
    op.drop_index('ix_execution_logs_run_started', table_name='execution_logs')
    op.drop_table('execution_logs')
    op.drop_index(op.f('ix_execution_runs_workflow_id'), table_name='execution_runs')
    op.drop_table('execution_runs')
    op.drop_index(op.f('ix_agent_nodes_workflow_id'), table_name='agent_nodes')
    op.drop_table('agent_nodes')
    op.drop_index(op.f('ix_workflows_user_id'), table_name='workflows')
    op.drop_table('workflows')
    op.drop_index(op.f('ix_credentials_user_id'), table_name='credentials')
    op.drop_table('credentials')
    op.drop_table('users')
    for enum_name in ('approval_decision', 'output_type', 'node_status', 'run_status'):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
