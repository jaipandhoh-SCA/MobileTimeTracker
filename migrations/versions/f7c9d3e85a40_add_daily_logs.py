"""Add daily logs with photos

Revision ID: f7c9d3e85a40
Revises: e6b8c2d74f39
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7c9d3e85a40'
down_revision = 'e6b8c2d74f39'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('daily_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='Draft'),
        sa.Column('crew_count', sa.Integer(), nullable=True),
        sa.Column('crew_names', sa.Text(), nullable=True),
        sa.Column('hours_regular', sa.Numeric(5, 2), nullable=True, server_default='0'),
        sa.Column('hours_overtime', sa.Numeric(5, 2), nullable=True, server_default='0'),
        sa.Column('work_completed', sa.Text(), nullable=True),
        sa.Column('weather_condition', sa.String(30), nullable=True),
        sa.Column('weather_temp_f', sa.Integer(), nullable=True),
        sa.Column('weather_notes', sa.String(300), nullable=True),
        sa.Column('delays', sa.Text(), nullable=True),
        sa.Column('safety_incidents', sa.Text(), nullable=True),
        sa.Column('visitors', sa.Text(), nullable=True),
        sa.Column('materials_delivered', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('client_uuid', sa.String(36), nullable=True, unique=True),
        sa.UniqueConstraint('client_id', 'log_date', 'created_by_user_id',
                            name='uq_daily_log_client_date_user'),
    )
    op.create_index('idx_daily_log_client', 'daily_logs', ['client_id', 'log_date'])
    op.create_index('idx_daily_log_date', 'daily_logs', ['log_date'])

    op.create_table('daily_log_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('daily_log_id', sa.Integer(), sa.ForeignKey('daily_logs.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('caption', sa.String(500), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('uploaded_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_dlp_log', 'daily_log_photos', ['daily_log_id'])
    op.create_index('idx_dlp_client', 'daily_log_photos', ['client_id'])


def downgrade():
    op.drop_table('daily_log_photos')
    op.drop_table('daily_logs')
