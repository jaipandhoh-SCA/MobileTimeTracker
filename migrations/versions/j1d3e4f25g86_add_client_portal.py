"""Add client portal tables

Revision ID: j1d3e4f25g86
Revises: i0c2d3e14f75
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'j1d3e4f25g86'
down_revision = 'i0c2d3e14f75'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'client_users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('email', sa.String(200), unique=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_login', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_cuser_client', 'client_users', ['client_id'])
    op.create_index('idx_cuser_email', 'client_users', ['email'])

    op.create_table(
        'magic_links',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('client_user_id', sa.Integer, sa.ForeignKey('client_users.id'), nullable=False),
        sa.Column('token', sa.String(64), unique=True, nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('used', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_magic_token', 'magic_links', ['token'])

    op.create_table(
        'selection_categories',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )

    op.create_table(
        'selection_options',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('category_id', sa.Integer, sa.ForeignKey('selection_categories.id'), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('image_key', sa.String(500), nullable=True),
        sa.Column('price_delta', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('cost_code_id', sa.Integer, sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )
    op.create_index('idx_selopt_category', 'selection_options', ['category_id'])

    op.create_table(
        'client_selections',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('category_id', sa.Integer, sa.ForeignKey('selection_categories.id'), nullable=False),
        sa.Column('option_id', sa.Integer, sa.ForeignKey('selection_options.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='Pending'),
        sa.Column('change_order_id', sa.Integer, sa.ForeignKey('change_orders.id'), nullable=True),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('selected_at', sa.DateTime, nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
    )
    op.create_unique_constraint('uq_client_selection_category', 'client_selections', ['client_id', 'category_id'])
    op.create_index('idx_csel_client', 'client_selections', ['client_id'])

    op.create_table(
        'portal_messages',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('sender_type', sa.String(10), nullable=False),
        sa.Column('sender_name', sa.String(200), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('is_read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_pmsg_client', 'portal_messages', ['client_id'])
    op.create_index('idx_pmsg_unread', 'portal_messages', ['client_id', 'sender_type', 'is_read'])


def downgrade():
    op.drop_table('portal_messages')
    op.drop_table('client_selections')
    op.drop_table('selection_options')
    op.drop_table('selection_categories')
    op.drop_table('magic_links')
    op.drop_table('client_users')
