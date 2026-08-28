"""Add client_uuid to TimeEntry and ClientActivity for offline sync dedup

Revision ID: l3f5g6h47i08
Revises: k2e4f5g36h97
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'l3f5g6h47i08'
down_revision = 'k2e4f5g36h97'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('time_entries',
                  sa.Column('client_uuid', sa.String(36), nullable=True))
    op.create_unique_constraint('uq_time_entry_client_uuid', 'time_entries', ['client_uuid'])

    op.add_column('client_activities',
                  sa.Column('client_uuid', sa.String(36), nullable=True))
    op.create_unique_constraint('uq_client_activity_client_uuid', 'client_activities', ['client_uuid'])


def downgrade():
    op.drop_constraint('uq_client_activity_client_uuid', 'client_activities', type_='unique')
    op.drop_column('client_activities', 'client_uuid')

    op.drop_constraint('uq_time_entry_client_uuid', 'time_entries', type_='unique')
    op.drop_column('time_entries', 'client_uuid')
