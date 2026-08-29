"""Add user admin columns (is_active on users, auth_role_name on authorized_users)

Revision ID: o6i8j9k70l31
Revises: n5h7i8j69k20
Create Date: 2026-08-28

Additive migration — no backup required.
"""
from alembic import op
import sqlalchemy as sa

revision = 'o6i8j9k70l31'
down_revision = 'n5h7i8j69k20'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('authorized_users', sa.Column('auth_role_name', sa.String(50), nullable=True))


def downgrade():
    op.drop_column('authorized_users', 'auth_role_name')
    op.drop_column('users', 'is_active')
