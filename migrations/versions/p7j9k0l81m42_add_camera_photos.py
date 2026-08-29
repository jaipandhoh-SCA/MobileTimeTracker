"""Add camera-first photo capture: job_photos + field_issues tables

Revision ID: p7j9k0l81m42
Revises: o6i8j9k70l31
Create Date: 2026-08-28

Additive migration — no backup required.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p7j9k0l81m42'
down_revision = 'o6i8j9k70l31'
branch_labels = None
depends_on = None


def upgrade():
    # -- field_issues (must exist before job_photos FK) --
    op.create_table(
        'field_issues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='Open'),
        sa.Column('priority', sa.String(10), nullable=False, server_default='Medium'),
        sa.Column('reported_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assigned_to_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('client_uuid', sa.String(36), nullable=True, unique=True),
    )
    op.create_index('idx_fi_client_status', 'field_issues', ['client_id', 'status'])
    op.create_index('idx_fi_assigned_status', 'field_issues', ['assigned_to_user_id', 'status'])

    # -- job_photos --
    op.create_table(
        'job_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('field_issue_id', sa.Integer(), sa.ForeignKey('field_issues.id'), nullable=True),
        sa.Column('batch_uuid', sa.String(36), nullable=True),
        sa.Column('category', sa.String(30), nullable=False, server_default='uncategorized'),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('caption', sa.String(500), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('taken_at', sa.DateTime(), nullable=False),
        sa.Column('uploaded_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('media_uuid', sa.String(36), nullable=True, unique=True),
    )
    op.create_index('idx_jp_client_taken', 'job_photos', ['client_id', 'taken_at'])
    op.create_index('idx_jp_batch', 'job_photos', ['batch_uuid'])
    op.create_index('idx_jp_client_cat', 'job_photos', ['client_id', 'category'])
    op.create_index('idx_jp_issue', 'job_photos', ['field_issue_id'])


def downgrade():
    op.drop_table('job_photos')
    op.drop_table('field_issues')
