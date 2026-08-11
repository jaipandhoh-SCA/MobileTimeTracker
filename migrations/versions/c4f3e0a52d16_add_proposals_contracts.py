"""add proposals, contracts, draw schedule

Revision ID: c4f3e0a52d16
Revises: b3e2d9f41c05
Create Date: 2026-08-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4f3e0a52d16'
down_revision: Union[str, None] = 'b3e2d9f41c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('proposals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='Draft'),
        sa.Column('share_token', sa.String(64), unique=True, nullable=False),
        sa.Column('cover_note', sa.Text(), nullable=True),
        sa.Column('scope_text', sa.Text(), nullable=True),
        sa.Column('exclusions_text', sa.Text(), nullable=True),
        sa.Column('validity_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('viewed_at', sa.DateTime(), nullable=True),
        sa.Column('viewed_ip', sa.String(45), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_ip', sa.String(45), nullable=True),
        sa.Column('accepted_name', sa.String(200), nullable=True),
        sa.Column('pdf_storage_key', sa.String(500), nullable=True),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_proposal_client', 'proposals', ['client_id'])
    op.create_index('idx_proposal_token', 'proposals', ['share_token'])

    op.create_table('contracts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('proposal_id', sa.Integer(), sa.ForeignKey('proposals.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('estimate_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='Draft'),
        sa.Column('share_token', sa.String(64), unique=True, nullable=False),
        sa.Column('contract_number', sa.String(50), nullable=False),
        sa.Column('scope_text', sa.Text(), nullable=True),
        sa.Column('terms_text', sa.Text(), nullable=True),
        sa.Column('total_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('signed_ip', sa.String(45), nullable=True),
        sa.Column('signed_name', sa.String(200), nullable=True),
        sa.Column('signed_email', sa.String(200), nullable=True),
        sa.Column('signature_data', sa.Text(), nullable=True),
        sa.Column('pdf_storage_key', sa.String(500), nullable=True),
        sa.Column('signed_pdf_key', sa.String(500), nullable=True),
        sa.Column('pandadoc_id', sa.String(100), nullable=True),
        sa.Column('pandadoc_status', sa.String(50), nullable=True),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_contract_client', 'contracts', ['client_id'])
    op.create_index('idx_contract_token', 'contracts', ['share_token'])

    op.create_table('draw_schedule_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('milestone', sa.String(200), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('pct_of_total', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('paid_amount', sa.Numeric(12, 2), nullable=True),
    )
    op.create_index('idx_draw_contract', 'draw_schedule_items', ['contract_id'])


def downgrade() -> None:
    op.drop_table('draw_schedule_items')
    op.drop_table('contracts')
    op.drop_table('proposals')
