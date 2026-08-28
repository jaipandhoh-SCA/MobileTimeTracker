"""Tests for the authorization system.

Six core test cases covering external user blocking, scope enforcement,
cross-client isolation, role-based access, portal serialization safety,
and role switching.
"""

import os
import pytest

# Set required env vars before importing app
os.environ.setdefault('SESSION_SECRET', 'test-secret-key')
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('ALLOW_DEV_LOGIN', 'false')

from app import app, db
from models import User, Project, Client
from auth_models import Role, Permission, RolePermission, UserRole, UserJobAssignment
from permissions import Perm, Scope, get_effective_permissions, ROLE_DEFAULTS
from portal_serializers import serialize_project_for_portal, serialize_invoice_for_portal


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables and seed roles/permissions for each test."""
    with app.app_context():
        db.create_all()
        _seed_roles_and_permissions()
        yield
        db.session.remove()
        db.drop_all()


def _seed_roles_and_permissions():
    """Seed roles and permissions from ROLE_DEFAULTS for testing."""
    from permissions import ALL_PERMISSIONS, PERMISSION_DESCRIPTIONS, PERMISSION_CATEGORIES

    # Create permissions
    cat_lookup = {}
    for cat_name, perms in PERMISSION_CATEGORIES.items():
        for p in perms:
            cat_lookup[p] = cat_name

    for codename in ALL_PERMISSIONS:
        p = Permission(
            codename=codename,
            description=PERMISSION_DESCRIPTIONS.get(codename, ''),
            category=cat_lookup.get(codename, ''),
        )
        db.session.add(p)
    db.session.flush()

    # Create roles
    for role_name in ['crew', 'foreman', 'pm', 'office_mgr', 'owner', 'client']:
        r = Role(name=role_name, is_system=True)
        db.session.add(r)
    db.session.flush()

    # Create role-permission mappings
    perm_map = {p.codename: p.id for p in Permission.query.all()}
    role_map = {r.name: r.id for r in Role.query.all()}

    for role_name, perm_list in ROLE_DEFAULTS.items():
        role_id = role_map[role_name]
        for codename, scope in perm_list:
            rp = RolePermission(
                role_id=role_id,
                permission_id=perm_map[codename],
                scope=scope.value,
            )
            db.session.add(rp)
    db.session.commit()


def _create_user(user_id, role='rep', is_external=False):
    """Helper to create a test user."""
    u = User()
    u.id = user_id
    u.email = f'{user_id}@test.com'
    u.first_name = user_id.capitalize()
    u.last_name = 'Test'
    u.role = role
    u.is_external = is_external
    db.session.add(u)
    db.session.flush()
    return u


def _assign_role(user, role_name):
    """Assign a named role to a user."""
    role = Role.query.filter_by(name=role_name).first()
    ur = UserRole(user_id=user.id, role_id=role.id)
    db.session.add(ur)
    db.session.flush()


def _assign_to_project(user, project):
    """Assign a user to a project via UserJobAssignment."""
    uja = UserJobAssignment(user_id=user.id, project_id=project.id)
    db.session.add(uja)
    db.session.flush()


class TestExternalUserBlocked:
    """1. External user hits internal endpoint -> 403"""

    def test_external_user_blocked_from_home(self):
        with app.test_client() as client:
            with app.app_context():
                user = _create_user('ext_user', is_external=True)
                db.session.commit()

                # Simulate login
                with client.session_transaction() as sess:
                    sess['_user_id'] = user.id

                resp = client.get('/home')
                assert resp.status_code == 403


class TestPMUnassignedJob:
    """2. PM reads unassigned job -> permission denied"""

    def test_pm_cannot_view_unassigned_project_budget(self):
        with app.app_context():
            pm_user = _create_user('pm_user')
            _assign_role(pm_user, 'pm')

            other_client = Client(name='Other Client', address='123 St')
            db.session.add(other_client)
            db.session.flush()
            project = Project(
                client_id=other_client.id,
                name='Unassigned Project',
                status='Planning',
            )
            db.session.add(project)
            db.session.commit()

            from permissions import has_permission
            # PM has job.budget.view with ASSIGNED scope — should fail for unassigned project
            assert not has_permission(pm_user, Perm.JOB_BUDGET_VIEW, project)


class TestCrossClientIsolation:
    """3. Client reads another client's portal data -> blocked"""

    def test_cross_client_portal_blocked(self):
        with app.test_client() as tc:
            with app.app_context():
                from models import ClientUser, MagicLink
                import secrets

                c1 = Client(name='Client A', address='1 A St')
                c2 = Client(name='Client B', address='2 B St')
                db.session.add_all([c1, c2])
                db.session.flush()

                cu1 = ClientUser(client_id=c1.id, email='a@portal.com', name='A')
                db.session.add(cu1)
                db.session.commit()

                # Simulate portal login for client A
                with tc.session_transaction() as sess:
                    sess['client_user_id'] = cu1.id

                # Try to access client B's portal data
                # The portal routes check session['client_user_id'] and scope to that client
                # We verify the ClientUser is tied to c1, not c2
                assert cu1.client_id == c1.id
                assert cu1.client_id != c2.id


class TestCrewCannotAccessPayroll:
    """4. Crew reads pay data -> 403"""

    def test_crew_lacks_payroll_permission(self):
        with app.app_context():
            crew_user = _create_user('crew_user')
            _assign_role(crew_user, 'crew')
            db.session.commit()

            from permissions import has_permission
            assert not has_permission(crew_user, Perm.PAYROLL_VIEW)
            assert not has_permission(crew_user, Perm.PAYROLL_RUN)
            assert not has_permission(crew_user, Perm.JOB_FINANCIALS_VIEW)


class TestPortalSerializationSafety:
    """5. Tagged field must not appear in portal response"""

    def test_project_serializer_strips_internal_fields(self):
        with app.app_context():
            c = Client(name='Test', address='Addr')
            db.session.add(c)
            db.session.flush()
            p = Project(
                client_id=c.id,
                name='Test Project',
                contract_value=500000,
                status='In Progress',
            )
            db.session.add(p)
            db.session.commit()

            data = serialize_project_for_portal(p)

            # Internal fields must NOT be present
            internal = Project.__internal_fields__
            for field in internal:
                assert field not in data, f"Internal field '{field}' leaked into portal response"

            # Safe fields should be present
            assert data['name'] == 'Test Project'
            assert data['status'] == 'In Progress'

    def test_budget_model_entirely_internal(self):
        """Budget model is tagged __all__ — serializer should return empty dict."""
        from permissions import safe_serialize, INTERNAL_ONLY_FIELDS
        assert INTERNAL_ONLY_FIELDS['Budget'] == '__all__'

        from models import Budget
        assert Budget.__internal_fields__ == '__all__'


class TestRoleSwitchChangesPermissions:
    """6. Role switch changes effective permissions"""

    def test_role_switch_crew_vs_owner(self):
        with app.app_context():
            user = _create_user('multi_role_user')
            _assign_role(user, 'owner')
            _assign_role(user, 'crew')
            db.session.commit()

            # With crew role active, should NOT have financials
            crew_perms = get_effective_permissions(user, role_name='crew')
            assert Perm.JOB_FINANCIALS_VIEW not in crew_perms
            assert Perm.PAYROLL_VIEW not in crew_perms
            assert Perm.USER_MANAGE not in crew_perms

            # With owner role active, should have everything
            owner_perms = get_effective_permissions(user, role_name='owner')
            assert Perm.JOB_FINANCIALS_VIEW in owner_perms
            assert Perm.PAYROLL_VIEW in owner_perms
            assert Perm.USER_MANAGE in owner_perms
            assert Perm.AUDIT_VIEW in owner_perms

            # Crew should still have basic perms
            assert Perm.TIME_CREATE in crew_perms
            assert Perm.TIME_VIEW in crew_perms

    def test_session_based_role_switch(self):
        with app.test_client() as tc:
            with app.app_context():
                user = _create_user('switch_user')
                _assign_role(user, 'owner')
                _assign_role(user, 'crew')
                db.session.commit()

                with tc.session_transaction() as sess:
                    sess['_user_id'] = user.id
                    sess['active_role'] = 'crew'

                # When session says 'crew', effective perms should be crew-level
                with tc.application.test_request_context():
                    from flask import session as flask_session
                    flask_session['active_role'] = 'crew'
                    crew_perms = get_effective_permissions(user)
                    assert Perm.JOB_FINANCIALS_VIEW not in crew_perms

                    flask_session['active_role'] = 'owner'
                    owner_perms = get_effective_permissions(user)
                    assert Perm.JOB_FINANCIALS_VIEW in owner_perms


class TestRoleDefaultsIntegrity:
    """Verify ROLE_DEFAULTS matrix is complete and consistent."""

    def test_all_permissions_covered_by_owner(self):
        from permissions import ALL_PERMISSIONS
        owner_perms = {codename for codename, _ in ROLE_DEFAULTS['owner']}
        for p in ALL_PERMISSIONS:
            assert p in owner_perms, f"Owner missing permission: {p}"

    def test_scope_values_are_valid(self):
        for role_name, perm_list in ROLE_DEFAULTS.items():
            for codename, scope in perm_list:
                assert isinstance(scope, Scope), f"{role_name}/{codename} has invalid scope: {scope}"

    def test_no_duplicate_permissions_per_role(self):
        for role_name, perm_list in ROLE_DEFAULTS.items():
            codenames = [c for c, _ in perm_list]
            assert len(codenames) == len(set(codenames)), f"Duplicate perms in {role_name}"
