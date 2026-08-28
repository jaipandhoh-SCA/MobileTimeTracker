"""Add authorization tables, is_external column, seed roles and permissions

Revision ID: k2e4f5g36h97
Revises: j1d3e4f25g86
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'k2e4f5g36h97'
down_revision = 'j1d3e4f25g86'
branch_labels = None
depends_on = None

# --- Seed data ---

ROLES = [
    ('crew', 'Field crew member', True),
    ('foreman', 'Field foreman / lead', True),
    ('pm', 'Project manager', True),
    ('office_mgr', 'Office manager', True),
    ('owner', 'Company owner — full access', True),
    ('client', 'External client user — portal only', True),
]

PERMISSIONS = [
    ('time.create', 'Create time entries', 'Time'),
    ('time.view', 'View time entries', 'Time'),
    ('time.approve', 'Approve/reject time entries', 'Time'),
    ('client.view', 'View clients', 'Clients'),
    ('client.create', 'Create new clients', 'Clients'),
    ('client.edit', 'Edit client details', 'Clients'),
    ('client.assign', 'Assign clients to users', 'Clients'),
    ('client.delete', 'Delete clients', 'Clients'),
    ('job.budget.view', 'View job budgets', 'Job Costing'),
    ('job.cost.view', 'View job costs', 'Job Costing'),
    ('job.financials.view', 'View job financials', 'Job Costing'),
    ('job.financials.export', 'Export job financials', 'Job Costing'),
    ('estimate.view', 'View estimates', 'Estimates'),
    ('estimate.create', 'Create estimates', 'Estimates'),
    ('estimate.send', 'Send estimates to clients', 'Estimates'),
    ('estimate.approve', 'Approve estimates', 'Estimates'),
    ('proposal.view', 'View proposals', 'Proposals'),
    ('proposal.create', 'Create proposals', 'Proposals'),
    ('proposal.send', 'Send proposals to clients', 'Proposals'),
    ('contract.view', 'View contracts', 'Contracts'),
    ('contract.create', 'Create contracts', 'Contracts'),
    ('contract.send', 'Send contracts to clients', 'Contracts'),
    ('changeorder.view', 'View change orders', 'Change Orders'),
    ('changeorder.create', 'Create change orders', 'Change Orders'),
    ('changeorder.send', 'Send change orders to clients', 'Change Orders'),
    ('changeorder.approve', 'Approve change orders', 'Change Orders'),
    ('invoice.view', 'View invoices', 'Invoicing'),
    ('invoice.create', 'Create invoices', 'Invoicing'),
    ('invoice.send', 'Send invoices to clients', 'Invoicing'),
    ('invoice.void', 'Void invoices', 'Invoicing'),
    ('payment.view', 'View payments', 'Invoicing'),
    ('payment.record', 'Record payments', 'Invoicing'),
    ('dailylog.create', 'Create daily logs', 'Daily Logs'),
    ('dailylog.view', 'View daily logs', 'Daily Logs'),
    ('dailylog.approve', 'Approve daily logs', 'Daily Logs'),
    ('schedule.view', 'View schedule', 'Scheduling'),
    ('schedule.edit', 'Edit schedule tasks', 'Scheduling'),
    ('schedule.assign', 'Assign schedule tasks', 'Scheduling'),
    ('document.view', 'View documents', 'Documents'),
    ('document.internal.view', 'View internal documents', 'Documents'),
    ('document.upload', 'Upload documents', 'Documents'),
    ('permit.view', 'View permits', 'Documents'),
    ('permit.edit', 'Edit permits', 'Documents'),
    ('permit.delete', 'Delete permits', 'Documents'),
    ('selection.view', 'View selections', 'Selections & Portal'),
    ('selection.manage', 'Manage selection options', 'Selections & Portal'),
    ('selection.approve', 'Approve client selections', 'Selections & Portal'),
    ('portal.message', 'Send portal messages', 'Selections & Portal'),
    ('portal.user.manage', 'Manage portal users', 'Selections & Portal'),
    ('user.manage', 'Manage users and roles', 'Admin'),
    ('settings.manage', 'Manage app settings', 'Admin'),
    ('integration.manage', 'Manage integrations', 'Admin'),
    ('payroll.view', 'View payroll data', 'Admin'),
    ('payroll.run', 'Run payroll', 'Admin'),
    ('report.view', 'View reports', 'Admin'),
    ('audit.view', 'View audit logs', 'Admin'),
]

# Role -> [(perm_codename, scope), ...]
ROLE_PERMS = {
    'crew': [
        ('time.create', 'SELF'), ('time.view', 'SELF'),
        ('client.view', 'ASSIGNED'),
        ('dailylog.create', 'SELF'), ('dailylog.view', 'SELF'),
        ('schedule.view', 'ASSIGNED'), ('document.view', 'ASSIGNED'),
    ],
    'foreman': [
        ('time.create', 'SELF'), ('time.view', 'ASSIGNED'), ('time.approve', 'ASSIGNED'),
        ('client.view', 'ASSIGNED'),
        ('estimate.view', 'ASSIGNED'),
        ('changeorder.view', 'ASSIGNED'),
        ('dailylog.create', 'SELF'), ('dailylog.view', 'ASSIGNED'), ('dailylog.approve', 'ASSIGNED'),
        ('schedule.view', 'ASSIGNED'), ('schedule.edit', 'ASSIGNED'),
        ('document.view', 'ASSIGNED'), ('document.upload', 'ASSIGNED'),
    ],
    'pm': [
        ('time.create', 'SELF'), ('time.view', 'ALL'),
        ('client.view', 'ASSIGNED'), ('client.create', 'ALL'), ('client.edit', 'ASSIGNED'),
        ('job.budget.view', 'ASSIGNED'), ('job.cost.view', 'ASSIGNED'),
        ('job.financials.view', 'ALL'), ('job.financials.export', 'ALL'),
        ('estimate.view', 'ASSIGNED'), ('estimate.create', 'ALL'), ('estimate.send', 'ALL'),
        ('proposal.view', 'ASSIGNED'), ('proposal.create', 'ALL'), ('proposal.send', 'ALL'),
        ('contract.view', 'ASSIGNED'),
        ('changeorder.view', 'ASSIGNED'), ('changeorder.create', 'ALL'), ('changeorder.send', 'ALL'),
        ('dailylog.create', 'SELF'), ('dailylog.view', 'ASSIGNED'),
        ('schedule.view', 'ASSIGNED'), ('schedule.edit', 'ASSIGNED'), ('schedule.assign', 'ALL'),
        ('document.view', 'ASSIGNED'), ('document.internal.view', 'ALL'), ('document.upload', 'ALL'),
        ('permit.view', 'ASSIGNED'), ('permit.edit', 'ASSIGNED'),
        ('selection.view', 'ASSIGNED'), ('selection.approve', 'ASSIGNED'),
        ('portal.message', 'ASSIGNED'),
        ('report.view', 'ALL'),
    ],
    'office_mgr': [
        ('time.view', 'ALL'), ('time.approve', 'ALL'),
        ('client.view', 'ALL'), ('client.create', 'ALL'), ('client.edit', 'ALL'), ('client.assign', 'ALL'),
        ('job.budget.view', 'ALL'), ('job.cost.view', 'ALL'),
        ('job.financials.view', 'ALL'), ('job.financials.export', 'ALL'),
        ('estimate.view', 'ALL'), ('estimate.create', 'ALL'),
        ('proposal.view', 'ALL'),
        ('contract.view', 'ALL'),
        ('changeorder.view', 'ALL'),
        ('invoice.view', 'ALL'), ('invoice.create', 'ALL'), ('invoice.send', 'ALL'),
        ('payment.view', 'ALL'), ('payment.record', 'ALL'),
        ('dailylog.view', 'ALL'),
        ('schedule.view', 'ALL'),
        ('document.view', 'ALL'), ('document.internal.view', 'ALL'), ('document.upload', 'ALL'),
        ('permit.view', 'ALL'),
        ('selection.view', 'ALL'), ('selection.manage', 'ALL'),
        ('portal.message', 'ALL'), ('portal.user.manage', 'ALL'),
        ('settings.manage', 'ALL'),
        ('payroll.view', 'ALL'),
        ('report.view', 'ALL'),
    ],
    'owner': None,  # Gets ALL permissions with ALL scope
}


def upgrade():
    # --- Create tables ---
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('is_system', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )

    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('codename', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
    )

    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id'), nullable=False),
        sa.Column('permission_id', sa.Integer, sa.ForeignKey('permissions.id'), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False, server_default='ALL'),
        sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )

    op.create_table(
        'user_roles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id'), nullable=False),
        sa.Column('assigned_at', sa.DateTime, nullable=True),
        sa.Column('assigned_by', sa.String, sa.ForeignKey('users.id'), nullable=True),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )
    op.create_index('idx_userrole_user', 'user_roles', ['user_id'])

    op.create_table(
        'user_permission_grants',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('permission_id', sa.Integer, sa.ForeignKey('permissions.id'), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False, server_default='ALL'),
        sa.UniqueConstraint('user_id', 'permission_id', name='uq_user_perm_grant'),
    )
    op.create_index('idx_upg_user', 'user_permission_grants', ['user_id'])

    op.create_table(
        'user_job_assignments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('assigned_at', sa.DateTime, nullable=True),
        sa.Column('assigned_by', sa.String, sa.ForeignKey('users.id'), nullable=True),
        sa.UniqueConstraint('user_id', 'project_id', name='uq_user_job'),
    )
    op.create_index('idx_uja_user', 'user_job_assignments', ['user_id'])
    op.create_index('idx_uja_project', 'user_job_assignments', ['project_id'])

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('timestamp', sa.DateTime, nullable=False),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.String(100), nullable=True),
        sa.Column('detail', sa.JSON, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('success', sa.Boolean, nullable=False, server_default='true'),
    )
    op.create_index('idx_audit_user', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_entity', 'audit_logs', ['entity_type', 'entity_id'])

    # Add is_external to users
    op.add_column('users', sa.Column('is_external', sa.Boolean, nullable=False, server_default='false'))

    # --- Seed data ---
    conn = op.get_bind()

    # Seed roles
    for name, desc, is_system in ROLES:
        conn.execute(
            sa.text("INSERT INTO roles (name, description, is_system) VALUES (:n, :d, :s)"),
            {'n': name, 'd': desc, 's': is_system},
        )

    # Seed permissions
    for codename, desc, category in PERMISSIONS:
        conn.execute(
            sa.text("INSERT INTO permissions (codename, description, category) VALUES (:c, :d, :cat)"),
            {'c': codename, 'd': desc, 'cat': category},
        )

    # Seed role-permission mappings
    for role_name, perms_list in ROLE_PERMS.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM roles WHERE name = :n"), {'n': role_name}
        ).fetchone()
        role_id = role_row[0]

        if perms_list is None:
            # Owner: all permissions with ALL scope
            all_perms = conn.execute(sa.text("SELECT id FROM permissions")).fetchall()
            for (perm_id,) in all_perms:
                conn.execute(
                    sa.text("INSERT INTO role_permissions (role_id, permission_id, scope) VALUES (:r, :p, :s)"),
                    {'r': role_id, 'p': perm_id, 's': 'ALL'},
                )
        else:
            for codename, scope in perms_list:
                perm_row = conn.execute(
                    sa.text("SELECT id FROM permissions WHERE codename = :c"), {'c': codename}
                ).fetchone()
                if perm_row:
                    conn.execute(
                        sa.text("INSERT INTO role_permissions (role_id, permission_id, scope) VALUES (:r, :p, :s)"),
                        {'r': role_id, 'p': perm_row[0], 's': scope},
                    )


def downgrade():
    op.drop_index('idx_audit_entity', table_name='audit_logs')
    op.drop_index('idx_audit_timestamp', table_name='audit_logs')
    op.drop_index('idx_audit_user', table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index('idx_uja_project', table_name='user_job_assignments')
    op.drop_index('idx_uja_user', table_name='user_job_assignments')
    op.drop_table('user_job_assignments')

    op.drop_index('idx_upg_user', table_name='user_permission_grants')
    op.drop_table('user_permission_grants')

    op.drop_index('idx_userrole_user', table_name='user_roles')
    op.drop_table('user_roles')

    op.drop_table('role_permissions')
    op.drop_table('permissions')
    op.drop_table('roles')

    op.drop_column('users', 'is_external')
