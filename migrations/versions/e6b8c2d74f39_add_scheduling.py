"""Add project scheduling: phases, tasks, dependencies, assignments, notifications

Revision ID: e6b8c2d74f39
Revises: d5a7b1c63e28
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6b8c2d74f39'
down_revision = 'd5a7b1c63e28'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('schedule_phases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('color', sa.String(7), server_default='#6366f1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_phase_project', 'schedule_phases', ['project_id'])

    op.create_table('schedule_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('phase_id', sa.Integer(), sa.ForeignKey('schedule_phases.id'), nullable=True),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='Not Started'),
        sa.Column('priority', sa.String(10), nullable=False, server_default='Medium'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_task_project', 'schedule_tasks', ['project_id'])
    op.create_index('idx_task_phase', 'schedule_tasks', ['phase_id'])
    op.create_index('idx_task_dates', 'schedule_tasks', ['start_date', 'end_date'])
    op.create_index('idx_task_status', 'schedule_tasks', ['status'])

    op.create_table('task_dependencies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('schedule_tasks.id'), nullable=False),
        sa.Column('depends_on_id', sa.Integer(), sa.ForeignKey('schedule_tasks.id'), nullable=False),
        sa.Column('dependency_type', sa.String(5), nullable=False, server_default='FS'),
        sa.UniqueConstraint('task_id', 'depends_on_id', name='uq_task_dep'),
    )

    op.create_table('task_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('schedule_tasks.id'), nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('sub_name', sa.String(200), nullable=True),
        sa.Column('role', sa.String(50), nullable=True),
    )
    op.create_index('idx_assignment_user', 'task_assignments', ['user_id'])

    op.create_table('notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('link', sa.String(500), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_notif_user_read', 'notifications', ['user_id', 'is_read'])

    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('task_assigned', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('task_changed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('task_reminder', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )


def downgrade():
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
    op.drop_table('task_assignments')
    op.drop_table('task_dependencies')
    op.drop_table('schedule_tasks')
    op.drop_table('schedule_phases')
