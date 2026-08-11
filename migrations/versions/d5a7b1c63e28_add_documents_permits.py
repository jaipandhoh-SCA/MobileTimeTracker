"""Add documents, document_versions, permits tables

Revision ID: d5a7b1c63e28
Revises: c4f3e0a52d16
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd5a7b1c63e28'
down_revision: Union[str, None] = 'c4f3e0a52d16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('folder', sa.String(30), nullable=False, server_default='other'),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('current_version_id', sa.Integer(), nullable=True),
        sa.Column('is_superseded', sa.Boolean(), server_default='false'),
        sa.Column('superseded_by_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('visibility', sa.String(20), nullable=False, server_default='team'),
        sa.Column('uploaded_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_doc_client_folder', 'documents', ['client_id', 'folder'])

    op.create_table('document_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('change_note', sa.String(500), nullable=True),
        sa.Column('uploaded_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('document_id', 'version_number', name='uq_doc_version'),
    )
    op.create_index('idx_docver_doc', 'document_versions', ['document_id'])

    op.create_table('permits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('permit_type', sa.String(50), nullable=False),
        sa.Column('jurisdiction', sa.String(200), nullable=True),
        sa.Column('permit_number', sa.String(100), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='Not Started'),
        sa.Column('submitted_date', sa.Date(), nullable=True),
        sa.Column('approved_date', sa.Date(), nullable=True),
        sa.Column('issued_date', sa.Date(), nullable=True),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('corrections_due_date', sa.Date(), nullable=True),
        sa.Column('corrections_note', sa.Text(), nullable=True),
        sa.Column('fee_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('fee_paid', sa.Boolean(), server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_permit_client', 'permits', ['client_id'])
    op.create_index('idx_permit_status', 'permits', ['status'])


def downgrade() -> None:
    op.drop_table('permits')
    op.drop_table('document_versions')
    op.drop_table('documents')
