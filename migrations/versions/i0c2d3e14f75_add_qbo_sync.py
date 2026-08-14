"""Add QBO sync tables (tokens, mappings, sync log)

Revision ID: i0c2d3e14f75
Revises: h9b1c2d03e64
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'i0c2d3e14f75'
down_revision = 'h9b1c2d03e64'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'qbo_tokens',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('realm_id', sa.String(50), nullable=False),
        sa.Column('access_token', sa.Text, nullable=False),
        sa.Column('refresh_token', sa.Text, nullable=False),
        sa.Column('access_token_expires_at', sa.DateTime, nullable=False),
        sa.Column('refresh_token_expires_at', sa.DateTime, nullable=True),
        sa.Column('company_name', sa.String(200), nullable=True),
        sa.Column('connected_at', sa.DateTime, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )

    op.create_table(
        'qbo_mappings',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('local_id', sa.String(50), nullable=False),
        sa.Column('qbo_id', sa.String(50), nullable=True),
        sa.Column('qbo_sync_token', sa.String(20), nullable=True),
        sa.Column('qbo_name', sa.String(300), nullable=True),
        sa.Column('extra', sa.Text, nullable=True),
        sa.Column('last_synced_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_unique_constraint('uq_qbo_mapping', 'qbo_mappings', ['entity_type', 'local_id'])
    op.create_index('idx_qbo_map_type', 'qbo_mappings', ['entity_type'])
    op.create_index('idx_qbo_map_qbo_id', 'qbo_mappings', ['qbo_id'])

    op.create_table(
        'qbo_sync_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', sa.String(50), nullable=True),
        sa.Column('qbo_id', sa.String(50), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('detail', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_qbo_log_time', 'qbo_sync_logs', ['created_at'])
    op.create_index('idx_qbo_log_type', 'qbo_sync_logs', ['entity_type', 'status'])


def downgrade():
    op.drop_table('qbo_sync_logs')
    op.drop_table('qbo_mappings')
    op.drop_table('qbo_tokens')
