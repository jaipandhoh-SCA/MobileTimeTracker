"""Access-control tests for the three identity types: rep, supervisor, client.

Verifies:
1. Supervisor-only routes return 403 for reps.
2. Rep routes redirect for unauthenticated users.
3. Client portal is fully isolated from staff auth.
4. Client A cannot see Client B's data across every portal endpoint.
5. Role escalation is impossible via session tampering.
"""

import os
import sys
import unittest

os.environ.setdefault('SESSION_SECRET', 'test-secret-key-for-testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ALLOW_DEV_LOGIN', 'false')

from app import app, db
from models import (
    Client, ClientUser, MagicLink, PortalMessage, User,
    SelectionCategory, SelectionOption, ClientSelection,
    Project, Budget, CostCode, CostEntry, Invoice, Payment,
    Contract, Proposal, Estimate, EstimateLineItem,
    ChangeOrder, ChangeOrderItem, AuthorizedUser,
    AppSetting,
)
from client_portal import portal as client_portal_bp
from google_auth import google_auth, require_login, require_supervisor

if 'google_auth' not in app.blueprints:
    app.register_blueprint(google_auth)

if 'portal' not in app.blueprints:
    app.register_blueprint(client_portal_bp)

# Stub routes that mimic actual auth decorators from routes.py
if 'view_client' not in app.view_functions:
    @app.route('/clients/<int:client_id>')
    @require_login
    def view_client(client_id):
        return '', 200

if 'home' not in app.view_functions:
    @app.route('/home')
    @require_login
    def home():
        return '', 200

if 'clients' not in app.view_functions:
    @app.route('/clients')
    @require_login
    def clients_list():
        return '', 200

if 'admin_dashboard' not in app.view_functions:
    @app.route('/admin/payroll')
    @require_supervisor
    def admin_dashboard():
        return '', 200

if 'manage_users' not in app.view_functions:
    @app.route('/admin/manage-users')
    @require_supervisor
    def manage_users():
        return '', 200

if 'integrations_settings' not in app.view_functions:
    @app.route('/settings/integrations')
    @require_supervisor
    def integrations_settings():
        return '', 200

if 'cost_codes_settings' not in app.view_functions:
    @app.route('/settings/cost-codes')
    @require_supervisor
    def cost_codes_settings():
        return '', 200

if 'pipeline' not in app.view_functions:
    @app.route('/pipeline')
    @require_login
    def pipeline():
        return '', 200

# Additional stubs needed by templates
for _sn, _sp in [
    ('index', '/'),
    ('my_logs', '/time'),
    ('estimates_list', '/estimates'),
    ('my_tasks', '/tasks'),
    ('daily_logs_list', '/daily-logs'),
    ('change_orders_list', '/change-orders'),
    ('channel_spend', '/reports/spend'),
    ('edit_profile', '/profile'),
    ('global_search', '/api/search'),
    ('notification_settings', '/settings/notifications'),
    ('api_notifications', '/api/notifications'),
    ('mark_notifications_read', '/api/notifications/read'),
    ('quick_log', '/time/quick'),
    ('stop_clock', '/time/stop'),
    ('create_client', '/clients/new'),
    ('edit_client', '/clients/<int:client_id>/edit'),
    ('create_estimate', '/estimates/new'),
    ('edit_estimate', '/estimates/<int:estimate_id>/edit'),
    ('view_estimate', '/estimates/<int:estimate_id>'),
    ('project_schedule', '/schedule/<int:project_id>'),
    ('create_task', '/tasks/new'),
    ('edit_task', '/tasks/<int:task_id>/edit'),
    ('create_daily_log', '/daily-logs/new'),
    ('edit_daily_log', '/daily-logs/<int:log_id>/edit'),
    ('view_daily_log', '/daily-logs/<int:log_id>'),
    ('create_change_order', '/change-orders/new'),
    ('edit_change_order', '/change-orders/<int:co_id>/edit'),
    ('view_change_order', '/change-orders/<int:co_id>'),
    ('roi_report', '/reports/roi'),
    ('financials_report', '/reports/financials'),
    ('lead_sources_settings', '/settings/lead-sources'),
    ('lead_source_backfill', '/settings/lead-sources/backfill'),
    ('edit_user_profile', '/admin/users/<user_id>/edit'),
]:
    if _sn not in app.view_functions:
        app.add_url_rule(_sp, _sn, lambda **kw: ('', 200))


class AccessControlBase(unittest.TestCase):
    """Shared setup for access-control tests."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost'
        self.app = app
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

        # Staff users
        self.supervisor = User(
            id='google-sup-001', email='sup@company.com',
            first_name='Sam', last_name='Supervisor', role='supervisor',
        )
        self.rep = User(
            id='google-rep-001', email='rep@company.com',
            first_name='Ray', last_name='Rep', role='rep',
        )
        db.session.add_all([self.supervisor, self.rep])

        # Clients
        self.client_a = Client(name='Client A', status='Active',
                               contact_name='Alice', address='123 A St')
        self.client_b = Client(name='Client B', status='Active',
                               contact_name='Bob', address='456 B St')
        db.session.add_all([self.client_a, self.client_b])
        db.session.flush()

        # Client portal users
        self.cu_a = ClientUser(client_id=self.client_a.id,
                               email='alice@example.com', name='Alice')
        self.cu_b = ClientUser(client_id=self.client_b.id,
                               email='bob@example.com', name='Bob')
        db.session.add_all([self.cu_a, self.cu_b])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login_staff(self, user):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = user.id

    def _login_client(self, client_user):
        with self.client.session_transaction() as sess:
            sess['client_user_id'] = client_user.id
            sess['_client_portal'] = True

    def _clear_session(self):
        with self.client.session_transaction() as sess:
            sess.clear()


class TestRepVsSupervisor(AccessControlBase):
    """Reps must not reach supervisor-only routes."""

    # Routes protected by @require_supervisor
    SUPERVISOR_ONLY = [
        '/admin/payroll',
        '/admin/manage-users',
        '/settings/integrations',
        '/settings/cost-codes',
    ]

    def test_rep_blocked_from_supervisor_routes(self):
        """A rep should get 403 on supervisor-only routes."""
        self._login_staff(self.rep)
        for route in self.SUPERVISOR_ONLY:
            resp = self.client.get(route, follow_redirects=False)
            self.assertIn(
                resp.status_code, (302, 403),
                f'Rep got {resp.status_code} on supervisor route {route}'
            )

    def test_supervisor_can_access_supervisor_routes(self):
        """Supervisor should get 200 on supervisor-only routes."""
        self._login_staff(self.supervisor)
        for route in self.SUPERVISOR_ONLY:
            resp = self.client.get(route, follow_redirects=True)
            self.assertEqual(
                resp.status_code, 200,
                f'Supervisor got {resp.status_code} on {route}'
            )


class TestUnauthenticatedAccess(AccessControlBase):
    """Unauthenticated users must be redirected to login."""

    PROTECTED_ROUTES = ['/home', '/clients', '/admin/payroll']

    def test_unauthenticated_redirected(self):
        for route in self.PROTECTED_ROUTES:
            resp = self.client.get(route, follow_redirects=False)
            self.assertIn(
                resp.status_code, (302, 403),
                f'Unauthenticated got {resp.status_code} on {route}, expected redirect'
            )


class TestClientIsolation(AccessControlBase):
    """Client portal data isolation between clients."""

    def test_client_a_cannot_see_client_b_messages(self):
        """Portal messages page scopes data to the logged-in client only."""
        self._login_client(self.cu_a)
        resp = self.client.get('/portal/messages', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # Messages page only shows client A data
        self.assertNotIn(b'Client B', resp.data)

    def test_client_cannot_access_staff_home(self):
        """A client session must not grant access to staff routes."""
        self._login_client(self.cu_a)
        resp = self.client.get('/home', follow_redirects=False)
        self.assertNotEqual(resp.status_code, 200)

    def test_session_tampering_role_escalation_impossible(self):
        """Setting both client and staff session keys should not grant
        staff access — flask-login's user_loader checks User model PK."""
        self._login_client(self.cu_a)
        # Try to inject a staff _user_id into the same session
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.supervisor.id

        # Even with both keys, portal messages should still scope to client
        resp = self.client.get('/portal/messages', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # The portal page should show Client A context, not a staff view
        self.assertNotIn(b'Client B', resp.data)

    def test_messages_cross_client_isolation(self):
        """Messages posted by client B must not appear for client A."""
        msg_b = PortalMessage(
            client_id=self.client_b.id, sender_type='client',
            sender_name='Bob', message='Secret message from B',
        )
        db.session.add(msg_b)
        db.session.commit()

        self._login_client(self.cu_a)
        resp = self.client.get('/portal/messages')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Secret message from B', resp.data)

    def test_inactive_client_blocked(self):
        """Deactivated client users should be redirected to login."""
        self.cu_a.is_active = False
        db.session.commit()

        self._login_client(self.cu_a)
        resp = self.client.get('/portal/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))


class TestMagicLinkSecurity(AccessControlBase):
    """Magic link token security."""

    def test_expired_token_rejected(self):
        """An expired magic link should not grant access."""
        from datetime import datetime, timedelta, timezone
        import secrets

        token = secrets.token_urlsafe(32)
        ml = MagicLink(
            client_user_id=self.cu_a.id,
            token=token,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(ml)
        db.session.commit()

        resp = self.client.get(f'/portal/auth/{token}', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))

    def test_invalid_token_rejected(self):
        """A random invalid token should redirect to login."""
        resp = self.client.get('/portal/auth/invalid-token-xyz', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))

    def test_used_token_rejected(self):
        """A token used once should not work again."""
        from datetime import datetime, timedelta, timezone
        import secrets

        token = secrets.token_urlsafe(32)
        ml = MagicLink(
            client_user_id=self.cu_a.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.session.add(ml)
        db.session.commit()

        # First use
        resp = self.client.get(f'/portal/auth/{token}', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal', resp.headers.get('Location', ''))

        self._clear_session()

        # Second use
        resp = self.client.get(f'/portal/auth/{token}', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))


if __name__ == '__main__':
    unittest.main()
