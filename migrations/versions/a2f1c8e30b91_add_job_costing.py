"""add job costing: projects, cost_codes, budgets, cost_entries + time entry approval

Revision ID: a2f1c8e30b91
Revises: 08301d725404
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f1c8e30b91'
down_revision: Union[str, Sequence[str], None] = '08301d725404'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- projects ---
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('contract_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='Planning'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_project_client', 'projects', ['client_id'])

    # --- cost_codes ---
    op.create_table(
        'cost_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True),
        sa.Column('code', sa.String(20), unique=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('default_cost_type', sa.String(20), nullable=False, server_default='Other'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )

    # --- budgets ---
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=False),
        sa.Column('cost_type', sa.String(20), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('project_id', 'cost_code_id', 'cost_type', name='uq_budget_project_code_type'),
    )
    op.create_index('idx_budget_project', 'budgets', ['project_id'])

    # --- cost_entries ---
    op.create_table(
        'cost_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=False),
        sa.Column('cost_type', sa.String(20), nullable=False, server_default='Labor'),
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('time_entry_id', sa.Integer(), sa.ForeignKey('time_entries.id'), unique=True, nullable=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('raw_hours', sa.Numeric(5, 2), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(8, 2), nullable=True),
        sa.Column('burden_multiplier', sa.Numeric(5, 4), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('source_ref_type', sa.String(50), nullable=True),
        sa.Column('source_ref_id', sa.Integer(), nullable=True),
        sa.Column('committed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_cost_entry_project', 'cost_entries', ['project_id', 'cost_code_id'])
    op.create_index('idx_cost_entry_date', 'cost_entries', ['project_id', 'entry_date'])
    op.create_index('idx_cost_entry_source', 'cost_entries', ['source_ref_type', 'source_ref_id'])

    # --- Seed ADU cost-code template ---
    cost_codes = sa.table(
        'cost_codes',
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('default_cost_type', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    seed = [
        ('01',   'Site Work',              'Subcontractor', 100),
        ('02',   'Foundation',             'Subcontractor', 200),
        ('03',   'Framing',               'Labor',         300),
        ('03.1', 'Lumber',                'Material',      310),
        ('04',   'Plumbing',              'Subcontractor', 400),
        ('05',   'Electrical',            'Subcontractor', 500),
        ('06',   'HVAC',                  'Subcontractor', 600),
        ('07',   'Insulation & Drywall',  'Subcontractor', 700),
        ('08',   'Roofing',              'Subcontractor', 800),
        ('09',   'Exterior Finishes',     'Material',      900),
        ('10',   'Interior Finishes',     'Material',      1000),
        ('10.1', 'Flooring',             'Material',      1010),
        ('10.2', 'Cabinets & Counters',  'Material',      1020),
        ('10.3', 'Paint',                'Material',      1030),
        ('11',   'Windows & Doors',       'Material',      1100),
        ('12',   'Permits & Fees',        'Other',         1200),
        ('13',   'Design & Engineering',  'Subcontractor', 1300),
        ('14',   'Utilities & Connections','Subcontractor', 1400),
        ('15',   'General Conditions',    'Other',         1500),
        ('16',   'Cleanup & Final',       'Labor',         1600),
        ('17',   'Contingency',           'Other',         1700),
    ]
    op.bulk_insert(cost_codes, [
        {'code': code, 'name': name, 'default_cost_type': ct, 'sort_order': so, 'is_active': True}
        for code, name, ct, so in seed
    ])

    # Set parent_id for sub-codes
    op.execute(
        "UPDATE cost_codes SET parent_id = (SELECT id FROM cost_codes p WHERE p.code = '03') "
        "WHERE code = '03.1'"
    )
    op.execute(
        "UPDATE cost_codes SET parent_id = (SELECT id FROM cost_codes p WHERE p.code = '10') "
        "WHERE code LIKE '10.%'"
    )

    # --- Create a default project for every existing client ---
    op.execute(
        "INSERT INTO projects (client_id, name, contract_value, status, is_default, created_at, updated_at) "
        "SELECT id, name, final_contract_value, 'Planning', true, NOW(), NOW() "
        "FROM clients"
    )

    # --- Add columns to time_entries ---
    op.add_column('time_entries', sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=True))
    op.add_column('time_entries', sa.Column('status', sa.String(20), nullable=False, server_default='pending'))
    op.add_column('time_entries', sa.Column('rejection_reason', sa.Text(), nullable=True))
    op.add_column('time_entries', sa.Column('approved_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('time_entries', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.create_index('idx_te_status', 'time_entries', ['status', 'date'])

    # --- Add burden_multiplier to users ---
    op.add_column('users', sa.Column('burden_multiplier', sa.Numeric(5, 4), nullable=True))

    # --- Seed default burden multiplier ---
    op.execute(
        "INSERT INTO app_settings (key, value) VALUES ('labor_burden_multiplier', '1.25') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_column('users', 'burden_multiplier')
    op.drop_index('idx_te_status', table_name='time_entries')
    op.drop_column('time_entries', 'approved_at')
    op.drop_column('time_entries', 'approved_by_user_id')
    op.drop_column('time_entries', 'rejection_reason')
    op.drop_column('time_entries', 'status')
    op.drop_column('time_entries', 'cost_code_id')
    op.drop_table('cost_entries')
    op.drop_table('budgets')
    op.drop_table('cost_codes')
    op.drop_table('projects')
