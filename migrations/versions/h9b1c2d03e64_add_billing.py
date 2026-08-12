"""Add invoices, invoice_line_items, payments tables and contract retainage

Revision ID: h9b1c2d03e64
Revises: g8a0b1c92d53
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'h9b1c2d03e64'
down_revision = 'g8a0b1c92d53'
branch_labels = None
depends_on = None


def upgrade():
    # Add retainage to contracts
    op.add_column('contracts', sa.Column('retainage_pct', sa.Numeric(5, 2),
                  nullable=False, server_default='0'))

    op.create_table('invoices',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('contract_id', sa.Integer, sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('invoice_number', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='Draft'),
        sa.Column('share_token', sa.String(64), unique=True, nullable=False),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('retainage_pct', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('retainage_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('total_due', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('amount_paid', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('balance_due', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('issued_date', sa.Date, nullable=True),
        sa.Column('due_date', sa.Date, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('stripe_payment_intent_id', sa.String(200), nullable=True),
        sa.Column('stripe_payment_url', sa.String(500), nullable=True),
        sa.Column('created_by_user_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_inv_contract', 'invoices', ['contract_id'])
    op.create_index('idx_inv_client', 'invoices', ['client_id'])
    op.create_index('idx_inv_token', 'invoices', ['share_token'])
    op.create_index('idx_inv_status', 'invoices', ['status'])

    op.create_table('invoice_line_items',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('invoice_id', sa.Integer, sa.ForeignKey('invoices.id'), nullable=False),
        sa.Column('source_type', sa.String(20), nullable=False, server_default='draw'),
        sa.Column('draw_item_id', sa.Integer, sa.ForeignKey('draw_schedule_items.id'), nullable=True),
        sa.Column('change_order_id', sa.Integer, sa.ForeignKey('change_orders.id'), nullable=True),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('pct_complete', sa.Numeric(5, 2), nullable=True),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('idx_ili_invoice', 'invoice_line_items', ['invoice_id'])

    op.create_table('payments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('invoice_id', sa.Integer, sa.ForeignKey('invoices.id'), nullable=False),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('method', sa.String(20), nullable=False, server_default='other'),
        sa.Column('status', sa.String(20), nullable=False, server_default='succeeded'),
        sa.Column('reference', sa.String(200), nullable=True),
        sa.Column('stripe_payment_intent_id', sa.String(200), nullable=True),
        sa.Column('stripe_charge_id', sa.String(200), nullable=True),
        sa.Column('is_deposit', sa.Boolean, server_default='false'),
        sa.Column('received_date', sa.Date, nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('recorded_by_user_id', sa.String, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_pmt_invoice', 'payments', ['invoice_id'])
    op.create_index('idx_pmt_client', 'payments', ['client_id'])
    op.create_index('idx_pmt_stripe', 'payments', ['stripe_payment_intent_id'])


def downgrade():
    op.drop_table('payments')
    op.drop_table('invoice_line_items')
    op.drop_table('invoices')
    op.drop_column('contracts', 'retainage_pct')
