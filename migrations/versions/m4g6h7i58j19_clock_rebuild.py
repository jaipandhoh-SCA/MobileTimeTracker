"""Add GPS and job fields for clock rebuild

Revision ID: m4g6h7i58j19
Revises: l3f5g6h47i08
Create Date: 2026-08-28 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'm4g6h7i58j19'
down_revision = 'l3f5g6h47i08'
branch_labels = None
depends_on = None


def upgrade():
    # Client — jobsite GPS
    op.add_column('clients', sa.Column('jobsite_latitude', sa.Float(), nullable=True))
    op.add_column('clients', sa.Column('jobsite_longitude', sa.Float(), nullable=True))

    # ActiveClock — job context at clock-in
    op.add_column('active_clocks', sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True))
    op.add_column('active_clocks', sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True))
    op.add_column('active_clocks', sa.Column('clock_in_lat', sa.Float(), nullable=True))
    op.add_column('active_clocks', sa.Column('clock_in_lng', sa.Float(), nullable=True))
    op.add_column('active_clocks', sa.Column('notes', sa.Text(), nullable=True))

    # TimeEntry — GPS audit trail
    op.add_column('time_entries', sa.Column('clock_in_lat', sa.Float(), nullable=True))
    op.add_column('time_entries', sa.Column('clock_in_lng', sa.Float(), nullable=True))
    op.add_column('time_entries', sa.Column('clock_out_lat', sa.Float(), nullable=True))
    op.add_column('time_entries', sa.Column('clock_out_lng', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('time_entries', 'clock_out_lng')
    op.drop_column('time_entries', 'clock_out_lat')
    op.drop_column('time_entries', 'clock_in_lng')
    op.drop_column('time_entries', 'clock_in_lat')

    op.drop_column('active_clocks', 'notes')
    op.drop_column('active_clocks', 'clock_in_lng')
    op.drop_column('active_clocks', 'clock_in_lat')
    op.drop_column('active_clocks', 'cost_code_id')
    op.drop_column('active_clocks', 'client_id')

    op.drop_column('clients', 'jobsite_longitude')
    op.drop_column('clients', 'jobsite_latitude')
