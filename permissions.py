"""Permission constants, scope enum, role defaults, and authorization helpers."""

from enum import Enum
from functools import wraps
from flask import abort, session
from flask_login import current_user


class Scope(Enum):
    ALL = 'ALL'
    ASSIGNED = 'ASSIGNED'
    SELF = 'SELF'


class Perm:
    # Time
    TIME_CREATE = 'time.create'
    TIME_VIEW = 'time.view'
    TIME_APPROVE = 'time.approve'

    # Clients
    CLIENT_VIEW = 'client.view'
    CLIENT_CREATE = 'client.create'
    CLIENT_EDIT = 'client.edit'
    CLIENT_ASSIGN = 'client.assign'
    CLIENT_DELETE = 'client.delete'

    # Job Costing
    JOB_BUDGET_VIEW = 'job.budget.view'
    JOB_COST_VIEW = 'job.cost.view'
    JOB_FINANCIALS_VIEW = 'job.financials.view'
    JOB_FINANCIALS_EXPORT = 'job.financials.export'

    # Estimates
    ESTIMATE_VIEW = 'estimate.view'
    ESTIMATE_CREATE = 'estimate.create'
    ESTIMATE_SEND = 'estimate.send'
    ESTIMATE_APPROVE = 'estimate.approve'

    # Proposals & Contracts
    PROPOSAL_VIEW = 'proposal.view'
    PROPOSAL_CREATE = 'proposal.create'
    PROPOSAL_SEND = 'proposal.send'
    CONTRACT_VIEW = 'contract.view'
    CONTRACT_CREATE = 'contract.create'
    CONTRACT_SEND = 'contract.send'

    # Change Orders
    CHANGEORDER_VIEW = 'changeorder.view'
    CHANGEORDER_CREATE = 'changeorder.create'
    CHANGEORDER_SEND = 'changeorder.send'
    CHANGEORDER_APPROVE = 'changeorder.approve'

    # Invoicing
    INVOICE_VIEW = 'invoice.view'
    INVOICE_CREATE = 'invoice.create'
    INVOICE_SEND = 'invoice.send'
    INVOICE_VOID = 'invoice.void'
    PAYMENT_VIEW = 'payment.view'
    PAYMENT_RECORD = 'payment.record'

    # Daily Logs
    DAILYLOG_CREATE = 'dailylog.create'
    DAILYLOG_VIEW = 'dailylog.view'
    DAILYLOG_APPROVE = 'dailylog.approve'

    # Scheduling
    SCHEDULE_VIEW = 'schedule.view'
    SCHEDULE_EDIT = 'schedule.edit'
    SCHEDULE_ASSIGN = 'schedule.assign'

    # Documents
    DOCUMENT_VIEW = 'document.view'
    DOCUMENT_INTERNAL_VIEW = 'document.internal.view'
    DOCUMENT_UPLOAD = 'document.upload'
    PERMIT_VIEW = 'permit.view'
    PERMIT_EDIT = 'permit.edit'
    PERMIT_DELETE = 'permit.delete'

    # Selections & Portal
    SELECTION_VIEW = 'selection.view'
    SELECTION_MANAGE = 'selection.manage'
    SELECTION_APPROVE = 'selection.approve'
    PORTAL_MESSAGE = 'portal.message'
    PORTAL_USER_MANAGE = 'portal.user.manage'

    # Admin
    USER_MANAGE = 'user.manage'
    SETTINGS_MANAGE = 'settings.manage'
    INTEGRATION_MANAGE = 'integration.manage'
    PAYROLL_VIEW = 'payroll.view'
    PAYROLL_RUN = 'payroll.run'
    REPORT_VIEW = 'report.view'
    AUDIT_VIEW = 'audit.view'


ALL_PERMISSIONS = [
    v for k, v in vars(Perm).items()
    if not k.startswith('_') and isinstance(v, str)
]

# Permission descriptions keyed by codename
PERMISSION_DESCRIPTIONS = {
    Perm.TIME_CREATE: 'Create time entries',
    Perm.TIME_VIEW: 'View time entries',
    Perm.TIME_APPROVE: 'Approve/reject time entries',
    Perm.CLIENT_VIEW: 'View clients',
    Perm.CLIENT_CREATE: 'Create new clients',
    Perm.CLIENT_EDIT: 'Edit client details',
    Perm.CLIENT_ASSIGN: 'Assign clients to users',
    Perm.CLIENT_DELETE: 'Delete clients',
    Perm.JOB_BUDGET_VIEW: 'View job budgets',
    Perm.JOB_COST_VIEW: 'View job costs',
    Perm.JOB_FINANCIALS_VIEW: 'View job financials',
    Perm.JOB_FINANCIALS_EXPORT: 'Export job financials',
    Perm.ESTIMATE_VIEW: 'View estimates',
    Perm.ESTIMATE_CREATE: 'Create estimates',
    Perm.ESTIMATE_SEND: 'Send estimates to clients',
    Perm.ESTIMATE_APPROVE: 'Approve estimates',
    Perm.PROPOSAL_VIEW: 'View proposals',
    Perm.PROPOSAL_CREATE: 'Create proposals',
    Perm.PROPOSAL_SEND: 'Send proposals to clients',
    Perm.CONTRACT_VIEW: 'View contracts',
    Perm.CONTRACT_CREATE: 'Create contracts',
    Perm.CONTRACT_SEND: 'Send contracts to clients',
    Perm.CHANGEORDER_VIEW: 'View change orders',
    Perm.CHANGEORDER_CREATE: 'Create change orders',
    Perm.CHANGEORDER_SEND: 'Send change orders to clients',
    Perm.CHANGEORDER_APPROVE: 'Approve change orders',
    Perm.INVOICE_VIEW: 'View invoices',
    Perm.INVOICE_CREATE: 'Create invoices',
    Perm.INVOICE_SEND: 'Send invoices to clients',
    Perm.INVOICE_VOID: 'Void invoices',
    Perm.PAYMENT_VIEW: 'View payments',
    Perm.PAYMENT_RECORD: 'Record payments',
    Perm.DAILYLOG_CREATE: 'Create daily logs',
    Perm.DAILYLOG_VIEW: 'View daily logs',
    Perm.DAILYLOG_APPROVE: 'Approve daily logs',
    Perm.SCHEDULE_VIEW: 'View schedule',
    Perm.SCHEDULE_EDIT: 'Edit schedule tasks',
    Perm.SCHEDULE_ASSIGN: 'Assign schedule tasks',
    Perm.DOCUMENT_VIEW: 'View documents',
    Perm.DOCUMENT_INTERNAL_VIEW: 'View internal documents',
    Perm.DOCUMENT_UPLOAD: 'Upload documents',
    Perm.PERMIT_VIEW: 'View permits',
    Perm.PERMIT_EDIT: 'Edit permits',
    Perm.PERMIT_DELETE: 'Delete permits',
    Perm.SELECTION_VIEW: 'View selections',
    Perm.SELECTION_MANAGE: 'Manage selection options',
    Perm.SELECTION_APPROVE: 'Approve client selections',
    Perm.PORTAL_MESSAGE: 'Send portal messages',
    Perm.PORTAL_USER_MANAGE: 'Manage portal users',
    Perm.USER_MANAGE: 'Manage users and roles',
    Perm.SETTINGS_MANAGE: 'Manage app settings',
    Perm.INTEGRATION_MANAGE: 'Manage integrations',
    Perm.PAYROLL_VIEW: 'View payroll data',
    Perm.PAYROLL_RUN: 'Run payroll',
    Perm.REPORT_VIEW: 'View reports',
    Perm.AUDIT_VIEW: 'View audit logs',
}

# Permission categories for grouping in UI
PERMISSION_CATEGORIES = {
    'Time': [Perm.TIME_CREATE, Perm.TIME_VIEW, Perm.TIME_APPROVE],
    'Clients': [Perm.CLIENT_VIEW, Perm.CLIENT_CREATE, Perm.CLIENT_EDIT, Perm.CLIENT_ASSIGN, Perm.CLIENT_DELETE],
    'Job Costing': [Perm.JOB_BUDGET_VIEW, Perm.JOB_COST_VIEW, Perm.JOB_FINANCIALS_VIEW, Perm.JOB_FINANCIALS_EXPORT],
    'Estimates': [Perm.ESTIMATE_VIEW, Perm.ESTIMATE_CREATE, Perm.ESTIMATE_SEND, Perm.ESTIMATE_APPROVE],
    'Proposals': [Perm.PROPOSAL_VIEW, Perm.PROPOSAL_CREATE, Perm.PROPOSAL_SEND],
    'Contracts': [Perm.CONTRACT_VIEW, Perm.CONTRACT_CREATE, Perm.CONTRACT_SEND],
    'Change Orders': [Perm.CHANGEORDER_VIEW, Perm.CHANGEORDER_CREATE, Perm.CHANGEORDER_SEND, Perm.CHANGEORDER_APPROVE],
    'Invoicing': [Perm.INVOICE_VIEW, Perm.INVOICE_CREATE, Perm.INVOICE_SEND, Perm.INVOICE_VOID, Perm.PAYMENT_VIEW, Perm.PAYMENT_RECORD],
    'Daily Logs': [Perm.DAILYLOG_CREATE, Perm.DAILYLOG_VIEW, Perm.DAILYLOG_APPROVE],
    'Scheduling': [Perm.SCHEDULE_VIEW, Perm.SCHEDULE_EDIT, Perm.SCHEDULE_ASSIGN],
    'Documents': [Perm.DOCUMENT_VIEW, Perm.DOCUMENT_INTERNAL_VIEW, Perm.DOCUMENT_UPLOAD, Perm.PERMIT_VIEW, Perm.PERMIT_EDIT, Perm.PERMIT_DELETE],
    'Selections & Portal': [Perm.SELECTION_VIEW, Perm.SELECTION_MANAGE, Perm.SELECTION_APPROVE, Perm.PORTAL_MESSAGE, Perm.PORTAL_USER_MANAGE],
    'Admin': [Perm.USER_MANAGE, Perm.SETTINGS_MANAGE, Perm.INTEGRATION_MANAGE, Perm.PAYROLL_VIEW, Perm.PAYROLL_RUN, Perm.REPORT_VIEW, Perm.AUDIT_VIEW],
}

# --- Role -> Permission + Scope matrix ---
S = Scope
ROLE_DEFAULTS = {
    'crew': [
        (Perm.TIME_CREATE, S.SELF),
        (Perm.TIME_VIEW, S.SELF),
        (Perm.CLIENT_VIEW, S.ASSIGNED),
        (Perm.DAILYLOG_CREATE, S.SELF),
        (Perm.DAILYLOG_VIEW, S.SELF),
        (Perm.SCHEDULE_VIEW, S.ASSIGNED),
        (Perm.DOCUMENT_VIEW, S.ASSIGNED),
    ],
    'foreman': [
        (Perm.TIME_CREATE, S.SELF),
        (Perm.TIME_VIEW, S.ASSIGNED),
        (Perm.TIME_APPROVE, S.ASSIGNED),
        (Perm.CLIENT_VIEW, S.ASSIGNED),
        (Perm.ESTIMATE_VIEW, S.ASSIGNED),
        (Perm.CHANGEORDER_VIEW, S.ASSIGNED),
        (Perm.DAILYLOG_CREATE, S.SELF),
        (Perm.DAILYLOG_VIEW, S.ASSIGNED),
        (Perm.DAILYLOG_APPROVE, S.ASSIGNED),
        (Perm.SCHEDULE_VIEW, S.ASSIGNED),
        (Perm.SCHEDULE_EDIT, S.ASSIGNED),
        (Perm.DOCUMENT_VIEW, S.ASSIGNED),
        (Perm.DOCUMENT_UPLOAD, S.ASSIGNED),
    ],
    'pm': [
        (Perm.TIME_CREATE, S.SELF),
        (Perm.TIME_VIEW, S.ALL),
        (Perm.CLIENT_VIEW, S.ASSIGNED),
        (Perm.CLIENT_CREATE, S.ALL),
        (Perm.CLIENT_EDIT, S.ASSIGNED),
        (Perm.JOB_BUDGET_VIEW, S.ASSIGNED),
        (Perm.JOB_COST_VIEW, S.ASSIGNED),
        (Perm.JOB_FINANCIALS_VIEW, S.ALL),
        (Perm.JOB_FINANCIALS_EXPORT, S.ALL),
        (Perm.ESTIMATE_VIEW, S.ASSIGNED),
        (Perm.ESTIMATE_CREATE, S.ALL),
        (Perm.ESTIMATE_SEND, S.ALL),
        (Perm.PROPOSAL_VIEW, S.ASSIGNED),
        (Perm.PROPOSAL_CREATE, S.ALL),
        (Perm.PROPOSAL_SEND, S.ALL),
        (Perm.CONTRACT_VIEW, S.ASSIGNED),
        (Perm.CHANGEORDER_VIEW, S.ASSIGNED),
        (Perm.CHANGEORDER_CREATE, S.ALL),
        (Perm.CHANGEORDER_SEND, S.ALL),
        (Perm.DAILYLOG_CREATE, S.SELF),
        (Perm.DAILYLOG_VIEW, S.ASSIGNED),
        (Perm.SCHEDULE_VIEW, S.ASSIGNED),
        (Perm.SCHEDULE_EDIT, S.ASSIGNED),
        (Perm.SCHEDULE_ASSIGN, S.ALL),
        (Perm.DOCUMENT_VIEW, S.ASSIGNED),
        (Perm.DOCUMENT_INTERNAL_VIEW, S.ALL),
        (Perm.DOCUMENT_UPLOAD, S.ALL),
        (Perm.PERMIT_VIEW, S.ASSIGNED),
        (Perm.PERMIT_EDIT, S.ASSIGNED),
        (Perm.SELECTION_VIEW, S.ASSIGNED),
        (Perm.SELECTION_APPROVE, S.ASSIGNED),
        (Perm.PORTAL_MESSAGE, S.ASSIGNED),
        (Perm.REPORT_VIEW, S.ALL),
    ],
    'office_mgr': [
        (Perm.TIME_VIEW, S.ALL),
        (Perm.TIME_APPROVE, S.ALL),
        (Perm.CLIENT_VIEW, S.ALL),
        (Perm.CLIENT_CREATE, S.ALL),
        (Perm.CLIENT_EDIT, S.ALL),
        (Perm.CLIENT_ASSIGN, S.ALL),
        (Perm.JOB_BUDGET_VIEW, S.ALL),
        (Perm.JOB_COST_VIEW, S.ALL),
        (Perm.JOB_FINANCIALS_VIEW, S.ALL),
        (Perm.JOB_FINANCIALS_EXPORT, S.ALL),
        (Perm.ESTIMATE_VIEW, S.ALL),
        (Perm.ESTIMATE_CREATE, S.ALL),
        (Perm.PROPOSAL_VIEW, S.ALL),
        (Perm.CONTRACT_VIEW, S.ALL),
        (Perm.CHANGEORDER_VIEW, S.ALL),
        (Perm.INVOICE_VIEW, S.ALL),
        (Perm.INVOICE_CREATE, S.ALL),
        (Perm.INVOICE_SEND, S.ALL),
        (Perm.PAYMENT_VIEW, S.ALL),
        (Perm.PAYMENT_RECORD, S.ALL),
        (Perm.DAILYLOG_VIEW, S.ALL),
        (Perm.SCHEDULE_VIEW, S.ALL),
        (Perm.DOCUMENT_VIEW, S.ALL),
        (Perm.DOCUMENT_INTERNAL_VIEW, S.ALL),
        (Perm.DOCUMENT_UPLOAD, S.ALL),
        (Perm.PERMIT_VIEW, S.ALL),
        (Perm.SELECTION_VIEW, S.ALL),
        (Perm.SELECTION_MANAGE, S.ALL),
        (Perm.PORTAL_MESSAGE, S.ALL),
        (Perm.PORTAL_USER_MANAGE, S.ALL),
        (Perm.SETTINGS_MANAGE, S.ALL),
        (Perm.PAYROLL_VIEW, S.ALL),
        (Perm.REPORT_VIEW, S.ALL),
    ],
    'owner': [
        (p, S.ALL) for p in ALL_PERMISSIONS
    ],
}

# Internal-only fields per model — these must NEVER appear in portal serializations
INTERNAL_ONLY_FIELDS = {
    'Project': {
        'contract_value', 'total_budget', 'total_actual',
        'total_committed', 'cost_to_complete', 'budget_used_pct',
    },
    'EstimateLineItem': {
        'labor_pct', 'material_pct', 'waste_pct',
        'unit_cost', 'labor_amount', 'material_amount',
    },
    'CostEntry': '__all__',
    'Budget': '__all__',
    'Invoice': {'stripe_payment_intent_id', 'stripe_session_id'},
    'User': {'hourly_rate', 'burden_multiplier'},
    'AssemblyItem': {'unit_cost', 'labor_pct', 'material_pct', 'waste_pct'},
}


def _get_user_job_project_ids(user):
    """Return set of project_ids the user is assigned to via UserJobAssignment."""
    from auth_models import UserJobAssignment
    rows = UserJobAssignment.query.filter_by(user_id=user.id).all()
    return {r.project_id for r in rows}


def get_effective_permissions(user, role_name=None):
    """Return dict of {perm_codename: Scope} for a user.

    Merges role-based permissions with individual grants.
    If role_name is provided, only that role's permissions are used.
    Otherwise uses session['active_role'] or all assigned roles.
    Individual grants always override role-based scope (wider wins).
    """
    from auth_models import UserRole, RolePermission, UserPermissionGrant, Role, Permission

    result = {}

    # Determine which roles to load
    if role_name:
        role_names = [role_name]
    else:
        try:
            active = session.get('active_role')
        except RuntimeError:
            active = None
        if active:
            role_names = [active]
        else:
            # All assigned roles
            user_roles = UserRole.query.filter_by(user_id=user.id).all()
            role_ids = [ur.role_id for ur in user_roles]
            if role_ids:
                roles = Role.query.filter(Role.id.in_(role_ids)).all()
                role_names = [r.name for r in roles]
            else:
                role_names = []

    # Load role-based permissions
    if role_names:
        roles = Role.query.filter(Role.name.in_(role_names)).all()
        role_ids = [r.id for r in roles]
        if role_ids:
            rps = (
                RolePermission.query
                .join(Permission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role_id.in_(role_ids))
                .all()
            )
            for rp in rps:
                perm = Permission.query.get(rp.permission_id)
                scope = Scope(rp.scope)
                # Keep the widest scope if same perm from multiple roles
                if perm.codename not in result or _scope_rank(scope) > _scope_rank(result[perm.codename]):
                    result[perm.codename] = scope

    # Layer on individual grants (always widen, never narrow)
    grants = (
        UserPermissionGrant.query
        .join(Permission, UserPermissionGrant.permission_id == Permission.id)
        .filter(UserPermissionGrant.user_id == user.id)
        .all()
    )
    for g in grants:
        perm = Permission.query.get(g.permission_id)
        scope = Scope(g.scope)
        if perm.codename not in result or _scope_rank(scope) > _scope_rank(result[perm.codename]):
            result[perm.codename] = scope

    return result


def _scope_rank(scope):
    """Higher rank = wider access."""
    return {Scope.SELF: 0, Scope.ASSIGNED: 1, Scope.ALL: 2}[scope]


def _get_resource_project_id(resource):
    """Extract project_id from a resource object."""
    if resource is None:
        return None
    if hasattr(resource, 'project_id'):
        return resource.project_id
    if hasattr(resource, 'id') and resource.__class__.__name__ == 'Project':
        return resource.id
    if hasattr(resource, 'client_id'):
        # For client-level resources, check if there's a default project
        return None  # Caller should handle client-level scoping separately
    return None


def _get_resource_user_id(resource):
    """Extract the owner user_id from a resource for SELF scope checks."""
    if resource is None:
        return None
    for attr in ('user_id', 'created_by_user_id'):
        if hasattr(resource, attr):
            return getattr(resource, attr)
    return None


def has_permission(user, perm, resource=None):
    """Check if user has a specific permission, respecting scope.

    Args:
        user: User model instance
        perm: Permission codename string (e.g. Perm.CLIENT_VIEW)
        resource: Optional resource object for scope checking

    Returns:
        bool
    """
    if not user or not user.is_authenticated:
        return False

    if getattr(user, 'is_external', False):
        return False

    effective = get_effective_permissions(user)

    if perm not in effective:
        return False

    scope = effective[perm]

    if scope == Scope.ALL:
        return True

    if scope == Scope.SELF:
        if resource is None:
            return True  # No resource to check against — allow (guard at query level)
        owner_id = _get_resource_user_id(resource)
        return owner_id == user.id

    if scope == Scope.ASSIGNED:
        if resource is None:
            return True  # No resource to check — allow (guard at query level)
        project_id = _get_resource_project_id(resource)
        if project_id is None:
            # Check client-level assignment
            client_id = getattr(resource, 'client_id', None) or getattr(resource, 'id', None)
            if client_id and resource.__class__.__name__ == 'Client':
                return resource.assigned_to_user_id == user.id
            return False
        assigned_ids = _get_user_job_project_ids(user)
        return project_id in assigned_ids

    return False


def require_permission(perm, get_resource=None):
    """Decorator factory for route-level permission checks.

    Args:
        perm: Permission codename string
        get_resource: Optional callable that takes **kwargs and returns
                      the resource object for scope checking
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                session['next_url'] = request.url
                return redirect(url_for('google_auth.login'))

            resource = get_resource(**kwargs) if get_resource else None
            if not has_permission(current_user, perm, resource):
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def safe_serialize(obj, allowed_fields):
    """Serialize an object, stripping any internal-only fields.

    Args:
        obj: Model instance or dict
        allowed_fields: List of field names to include

    Returns:
        dict with only allowed (non-internal) fields
    """
    model_name = obj.__class__.__name__ if not isinstance(obj, dict) else None
    internal = set()
    if model_name and model_name in INTERNAL_ONLY_FIELDS:
        marker = INTERNAL_ONLY_FIELDS[model_name]
        if marker == '__all__':
            return {}
        internal = marker

    result = {}
    for field in allowed_fields:
        if field in internal:
            continue
        if isinstance(obj, dict):
            result[field] = obj.get(field)
        else:
            result[field] = getattr(obj, field, None)
    return result
