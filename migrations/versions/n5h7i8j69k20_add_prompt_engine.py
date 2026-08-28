"""Add prompt engine tables and notification preference columns

Revision ID: n5h7i8j69k20
Revises: m4g6h7i58j19
Create Date: 2026-08-28 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'n5h7i8j69k20'
down_revision = 'm4g6h7i58j19'
branch_labels = None
depends_on = None


def upgrade():
    # New table: prompt_dismissals
    op.create_table(
        'prompt_dismissals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rule_key', sa.String(50), nullable=False),
        sa.Column('dismissed_date', sa.Date(), nullable=False),
        sa.Column('dismissed_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        'idx_pd_user_rule_date',
        'prompt_dismissals',
        ['user_id', 'rule_key', 'dismissed_date'],
    )

    # Extend notification_preferences with smart prompt columns
    with op.batch_alter_table('notification_preferences') as batch_op:
        batch_op.add_column(sa.Column('prompt_notifications_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('prompt_geo_clock_in', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('prompt_long_clock', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('prompt_no_daily_log', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('prompt_geo_left_clocked', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('prompt_unattached_photos', sa.Boolean(), server_default=sa.text('true'), nullable=False))
        batch_op.add_column(sa.Column('work_start_hour', sa.Integer(), server_default=sa.text('6'), nullable=False))
        batch_op.add_column(sa.Column('work_end_hour', sa.Integer(), server_default=sa.text('19'), nullable=False))


def downgrade():
    with op.batch_alter_table('notification_preferences') as batch_op:
        batch_op.drop_column('work_end_hour')
        batch_op.drop_column('work_start_hour')
        batch_op.drop_column('prompt_unattached_photos')
        batch_op.drop_column('prompt_geo_left_clocked')
        batch_op.drop_column('prompt_no_daily_log')
        batch_op.drop_column('prompt_long_clock')
        batch_op.drop_column('prompt_geo_clock_in')
        batch_op.drop_column('prompt_notifications_enabled')

    op.drop_index('idx_pd_user_rule_date', table_name='prompt_dismissals')
    op.drop_table('prompt_dismissals')
