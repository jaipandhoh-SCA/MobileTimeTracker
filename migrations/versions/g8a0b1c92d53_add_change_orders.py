"""Add change orders

Revision ID: g8a0b1c92d53
Revises: f7c9d3e85a40
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'g8a0b1c92d53'
down_revision = 'f7c9d3e85a40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'change_orders',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('co_number', sa.String(20), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='Draft'),
        sa.Column('price_to_client', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('share_token', sa.String(64), unique=True, nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('approved_ip', sa.String(45), nullable=True),
        sa.Column('approved_name', sa.String(200), nullable=True),
        sa.Column('approved_email', sa.String(200), nullable=True),
        sa.Column('signature_data', sa.Text, nullable=True),
        sa.Column('billed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('billed_at', sa.DateTime, nullable=True),
        sa.Column('created_by_user_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_co_client', 'change_orders', ['client_id'])
    op.create_index('idx_co_project', 'change_orders', ['project_id'])
    op.create_index('idx_co_token', 'change_orders', ['share_token'])
    op.create_index('idx_co_billed', 'change_orders', ['billed'])

    op.create_table(
        'change_order_items',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('change_order_id', sa.Integer, sa.ForeignKey('change_orders.id'), nullable=False),
        sa.Column('cost_code_id', sa.Integer, sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('cost_type', sa.String(20), nullable=False, server_default='Other'),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('idx_coi_co', 'change_order_items', ['change_order_id'])


def downgrade():
    op.drop_table('change_order_items')
    op.drop_table('change_orders')
