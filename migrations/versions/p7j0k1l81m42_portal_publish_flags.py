"""Add portal publish flags: client_visible on photos, client_label/description
on schedule phases, deadline/late_impact on selection categories

Revision ID: p7j0k1l81m42
Revises: o6i8j9k70l31
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'p7j0k1l81m42'
down_revision = 'o6i8j9k70l31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('daily_log_photos',
                  sa.Column('client_visible', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('schedule_phases',
                  sa.Column('client_label', sa.String(200), nullable=True))
    op.add_column('schedule_phases',
                  sa.Column('client_description', sa.Text(), nullable=True))
    op.add_column('selection_categories',
                  sa.Column('deadline', sa.Date(), nullable=True))
    op.add_column('selection_categories',
                  sa.Column('late_impact', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('selection_categories', 'late_impact')
    op.drop_column('selection_categories', 'deadline')
    op.drop_column('schedule_phases', 'client_description')
    op.drop_column('schedule_phases', 'client_label')
    op.drop_column('daily_log_photos', 'client_visible')
