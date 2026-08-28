"""Authorization middleware and decorators.

Provides route-level guards and audit logging for the authorization system.
Existing @require_login and @require_supervisor decorators remain functional
for backward compatibility.
"""

from functools import wraps
from flask import abort, request, session
from flask_login import current_user
from permissions import has_permission, get_effective_permissions


def require_internal(f):
    """Reject external (is_external=True) users with 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            session['next_url'] = request.url
            return redirect(url_for('google_auth.login'))
        if getattr(current_user, 'is_external', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def require_external(f):
    """Only allow external users (portal namespace)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        if not getattr(current_user, 'is_external', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def require_perm(perm_codename, get_resource=None):
    """Check a single permission + scope against the current user.

    Args:
        perm_codename: Permission codename string (e.g. 'client.view')
        get_resource: Optional callable(**kwargs) -> resource for scope check
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                session['next_url'] = request.url
                return redirect(url_for('google_auth.login'))

            resource = get_resource(**kwargs) if get_resource else None
            if not has_permission(current_user, perm_codename, resource):
                log_auth_event(
                    action='permission_denied',
                    entity_type='route',
                    entity_id=request.endpoint,
                    detail={'permission': perm_codename},
                    success=False,
                )
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_any_perm(*perm_codenames):
    """Require at least one of the listed permissions (OR check)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                session['next_url'] = request.url
                return redirect(url_for('google_auth.login'))

            for perm in perm_codenames:
                if has_permission(current_user, perm):
                    return f(*args, **kwargs)

            log_auth_event(
                action='permission_denied',
                entity_type='route',
                entity_id=request.endpoint,
                detail={'permissions': list(perm_codenames), 'check': 'any'},
                success=False,
            )
            abort(403)
        return decorated
    return decorator


def require_all_perms(*perm_codenames):
    """Require all listed permissions (AND check)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                session['next_url'] = request.url
                return redirect(url_for('google_auth.login'))

            for perm in perm_codenames:
                if not has_permission(current_user, perm):
                    log_auth_event(
                        action='permission_denied',
                        entity_type='route',
                        entity_id=request.endpoint,
                        detail={'permissions': list(perm_codenames), 'missing': perm, 'check': 'all'},
                        success=False,
                    )
                    abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def register_external_firewall(app):
    """Register a before_request handler that blocks external users from
    internal routes. Call this once during app startup."""

    @app.before_request
    def _external_user_firewall():
        if not current_user.is_authenticated:
            return  # Let individual route decorators handle auth

        if not getattr(current_user, 'is_external', False):
            return  # Internal user — no restriction

        path = request.path
        allowed_prefixes = ('/portal/', '/api/portal/', '/static/', '/logout')
        if not any(path.startswith(p) for p in allowed_prefixes):
            abort(403)


def log_auth_event(action, entity_type=None, entity_id=None, detail=None, success=True):
    """Write an AuditLog entry for authorization-related events."""
    from app import db
    from auth_models import AuditLog

    user_id = None
    if current_user and current_user.is_authenticated:
        user_id = current_user.id

    ip = request.remote_addr if request else None

    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail,
        ip_address=ip,
        success=success,
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
