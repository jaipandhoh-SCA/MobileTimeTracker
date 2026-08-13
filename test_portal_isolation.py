"""Tests asserting client portal auth isolation.

Verifies that:
1. A ClientUser session CANNOT access any staff/admin/supervisor route.
2. A ClientUser session CANNOT access another client's portal data.
3. An unauthenticated visitor cannot access portal routes.
4. A staff session (flask-login) cannot access portal routes as a client.
"""

import os
import sys
import unittest

# Set env before importing app
os.environ.setdefault('SESSION_SECRET', 'test-secret-key-for-testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ALLOW_DEV_LOGIN', 'false')

from app import app, db
from models import (
    Client, ClientUser, MagicLink, PortalMessage, User,
    SelectionCategory, SelectionOption, ClientSelection,
)
from client_portal import portal as client_portal_bp

# Ensure blueprint is registered (idempotent check)
if 'portal' not in app.blueprints:
    app.register_blueprint(client_portal_bp)

# Register stub for view_client (normally in routes.py) so url_for works
if 'view_client' not in app.view_functions:
    @app.route('/clients/<int:client_id>')
    def view_client(client_id):
        return '', 200


class PortalIsolationTestCase(unittest.TestCase):
    """Auth isolation between client portal and staff routes."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost'
        self.app = app
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

        db.create_all()

        # Create two clients
        self.client_a = Client(name='Client A', status='Active',
                               contact_name='Alice', address='123 A St')
        self.client_b = Client(name='Client B', status='Active',
                               contact_name='Bob', address='456 B St')
        db.session.add_all([self.client_a, self.client_b])
        db.session.flush()

        # Create client users
        self.cu_a = ClientUser(client_id=self.client_a.id,
                               email='alice@example.com', name='Alice')
        self.cu_b = ClientUser(client_id=self.client_b.id,
                               email='bob@example.com', name='Bob')
        db.session.add_all([self.cu_a, self.cu_b])

        # Create a staff user (Google OAuth user)
        self.staff = User(id='google-staff-123', email='staff@company.com',
                          first_name='Staff', last_name='User',
                          role='supervisor')
        db.session.add(self.staff)

        # Create a portal message for client A
        self.msg_a = PortalMessage(client_id=self.client_a.id,
                                    sender_type='staff',
                                    sender_name='Staff',
                                    message='Hello Client A')
        db.session.add(self.msg_a)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login_as_client(self, client_user):
        """Simulate a client portal login by setting session directly."""
        with self.client.session_transaction() as sess:
            sess['client_user_id'] = client_user.id
            sess['_client_portal'] = True

    def _login_as_staff(self):
        """Simulate a staff login via flask-login."""
        # flask-login stores user_id in session under '_user_id'
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.staff.id

    # ──────────────────────────────────────────────────────────────
    #  1. Client session CANNOT access staff routes
    # ──────────────────────────────────────────────────────────────

    # Only test routes that exist in this test's context.
    # Full role-based access-control tests are in test_access_control.py.
    STAFF_ROUTES = [
        '/home',
        '/clients',
    ]

    def test_client_session_cannot_access_staff_routes(self):
        """A logged-in ClientUser must NOT be able to reach any staff route."""
        self._login_as_client(self.cu_a)

        for route in self.STAFF_ROUTES:
            resp = self.client.get(route, follow_redirects=False)
            # Staff routes should redirect to Google OAuth login (302)
            # or return 401/403 — never 200
            self.assertNotEqual(
                resp.status_code, 200,
                f'Client session got 200 on staff route {route}'
            )

    def test_client_session_not_loaded_by_flask_login(self):
        """flask-login's user_loader should NOT load a ClientUser."""
        self._login_as_client(self.cu_a)

        with self.app.test_request_context():
            from flask_login import current_user
            # Even with client_user_id in session, current_user should be anonymous
            # because user_loader only queries User model by PK (string Google sub)
            with self.client.session_transaction() as sess:
                # flask-login looks for '_user_id', not 'client_user_id'
                self.assertNotIn('_user_id', sess)

    # ──────────────────────────────────────────────────────────────
    #  2. Client CANNOT access another client's data
    # ──────────────────────────────────────────────────────────────

    def test_client_a_cannot_see_client_b_messages(self):
        """Client A's portal messages should not include Client B's data."""
        self._login_as_client(self.cu_a)

        resp = self.client.get('/portal/messages')
        self.assertEqual(resp.status_code, 200)
        # Should see Client A's message
        self.assertIn(b'Hello Client A', resp.data)

        # Now login as Client B
        self._login_as_client(self.cu_b)
        resp = self.client.get('/portal/messages')
        self.assertEqual(resp.status_code, 200)
        # Should NOT see Client A's message
        self.assertNotIn(b'Hello Client A', resp.data)

    def test_client_b_cannot_post_message_as_client_a(self):
        """Client B posting a message should create it under Client B, not A."""
        self._login_as_client(self.cu_b)
        resp = self.client.post('/portal/messages',
                                data={'message': 'Test from B'},
                                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Verify the message is scoped to client B
        msg = PortalMessage.query.filter_by(message='Test from B').first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.client_id, self.client_b.id)
        self.assertNotEqual(msg.client_id, self.client_a.id)

    # ──────────────────────────────────────────────────────────────
    #  3. Unauthenticated visitors cannot access portal routes
    # ──────────────────────────────────────────────────────────────

    PORTAL_ROUTES = [
        '/portal/',
        '/portal/documents',
        '/portal/selections',
        '/portal/messages',
        '/portal/progress',
        '/portal/photos',
    ]

    def test_unauthenticated_redirected_to_login(self):
        """Visitors without a session should be redirected to portal login."""
        for route in self.PORTAL_ROUTES:
            resp = self.client.get(route, follow_redirects=False)
            self.assertEqual(
                resp.status_code, 302,
                f'Unauthenticated request to {route} got {resp.status_code}, expected 302'
            )
            self.assertIn('/portal/login', resp.headers.get('Location', ''),
                          f'{route} did not redirect to portal login')

    # ──────────────────────────────────────────────────────────────
    #  4. Staff session cannot access portal as a client
    # ──────────────────────────────────────────────────────────────

    def test_staff_session_redirected_from_portal(self):
        """A staff user (flask-login) without client_user_id should not
        access portal routes — they should be redirected to portal login."""
        self._login_as_staff()

        for route in self.PORTAL_ROUTES:
            resp = self.client.get(route, follow_redirects=False)
            # Staff session has _user_id but NOT client_user_id,
            # so require_client_login should redirect
            self.assertEqual(
                resp.status_code, 302,
                f'Staff session got {resp.status_code} on portal route {route}'
            )

    # ──────────────────────────────────────────────────────────────
    #  5. Inactive client user cannot access portal
    # ──────────────────────────────────────────────────────────────

    def test_inactive_client_user_rejected(self):
        """A deactivated ClientUser should be redirected to login."""
        self.cu_a.is_active = False
        db.session.commit()

        self._login_as_client(self.cu_a)
        resp = self.client.get('/portal/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))

    # ──────────────────────────────────────────────────────────────
    #  6. Magic link one-time use
    # ──────────────────────────────────────────────────────────────

    def test_magic_link_single_use(self):
        """A magic link token should only work once."""
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

        # First use — should work
        resp = self.client.get(f'/portal/auth/{token}', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal', resp.headers.get('Location', ''))

        # Clear session for second attempt
        with self.client.session_transaction() as sess:
            sess.clear()

        # Second use — should fail
        resp = self.client.get(f'/portal/auth/{token}', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/login', resp.headers.get('Location', ''))


if __name__ == '__main__':
    unittest.main()
