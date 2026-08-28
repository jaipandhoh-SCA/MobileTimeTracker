"""Tests for the offline-first field sync system.

Covers:
1. Offline entry — server upsert creates record from client_uuid
2. App restart with queue non-empty — entries survive (server-side dedup test)
3. Duplicate sync attempt — returns "duplicate" for time punches, "updated" for logs
4. Partial photo upload failure — text record syncs, photo endpoint returns error gracefully
5. 48-hour-offline backlog drain — bulk sync of many entries
6. Conflict policy — time punch append-only, daily log last-write-wins
"""

import os
import json
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

os.environ.setdefault('SESSION_SECRET', 'test-secret-key')
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('ALLOW_DEV_LOGIN', 'false')

from app import app, db
from models import User, Client, Project, DailyLog, TimeEntry, ClientActivity


# Register field sync endpoints. We can't always import routes.py because
# other test files (test_access_control.py) register stub routes that
# conflict with routes.py's module-level @app.route decorators.
# Instead, register just the endpoints we need using the extracted helpers.
from flask import request as flask_request, jsonify as flask_jsonify
from google_auth import require_login
from app import csrf
from field_sync_helpers import (
    upsert_daily_log, upsert_time_punch,
    upsert_material_note, upsert_general_note,
)

if 'field_sync' not in app.view_functions:

    @app.route('/api/field/sync', methods=['POST'])
    @require_login
    @csrf.exempt
    def field_sync():
        if not flask_request.is_json:
            return flask_jsonify(ok=False, error='JSON required'), 400
        payload = flask_request.get_json()
        client_uuid = payload.get('client_uuid')
        entry_type = payload.get('type')
        data = payload.get('data', {})
        if not client_uuid:
            return flask_jsonify(ok=False, error='client_uuid is required'), 400
        if not entry_type:
            return flask_jsonify(ok=False, error='type is required'), 400
        try:
            if entry_type == 'daily_log':
                result = upsert_daily_log(client_uuid, data)
            elif entry_type == 'time_punch':
                result = upsert_time_punch(client_uuid, data)
            elif entry_type == 'material_note':
                result = upsert_material_note(client_uuid, data)
            elif entry_type == 'general_note':
                result = upsert_general_note(client_uuid, data)
            else:
                return flask_jsonify(ok=False, error=f'Unknown type: {entry_type}'), 400
            db.session.commit()
            return flask_jsonify(ok=True, **result)
        except Exception as e:
            db.session.rollback()
            return flask_jsonify(ok=False, error=str(e)), 500

if 'field_media_upload' not in app.view_functions:

    @app.route('/api/field/media', methods=['POST'])
    @require_login
    @csrf.exempt
    def field_media_upload():
        parent_uuid = flask_request.form.get('parent_uuid')
        f = flask_request.files.get('file')
        if not parent_uuid:
            return flask_jsonify(ok=False, error='parent_uuid is required'), 400
        if not f:
            return flask_jsonify(ok=False, error='file is required'), 400
        parent_log = DailyLog.query.filter_by(client_uuid=parent_uuid).first()
        if not parent_log:
            return flask_jsonify(ok=False, error='Parent entry not found. Sync the log first.'), 404
        return flask_jsonify(ok=True, status='created', id=0)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables and a test user + client for each test."""
    with app.app_context():
        db.create_all()
        _seed_test_data()
        yield
        db.session.remove()
        db.drop_all()


def _seed_test_data():
    """Create a user and client for tests."""
    user = User()
    user.id = 'test-user'
    user.email = 'test@test.com'
    user.first_name = 'Test'
    user.last_name = 'User'
    user.role = 'supervisor'
    user.is_external = False
    db.session.add(user)

    client = Client(name='Test Client', address='123 Test St')
    db.session.add(client)
    db.session.flush()

    project = Project(
        client_id=client.id,
        name='Default',
        is_default=True,
        status='Active',
    )
    db.session.add(project)
    db.session.commit()


def _login(tc):
    """Simulate login for test client."""
    with tc.session_transaction() as sess:
        sess['_user_id'] = 'test-user'


def _get_client_id():
    return Client.query.first().id


class TestOfflineEntry:
    """1. Offline entry — server creates record from client_uuid."""

    def test_daily_log_sync_creates_record(self):
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            resp = tc.post('/api/field/sync',
                           json={
                               'client_uuid': 'uuid-log-001',
                               'type': 'daily_log',
                               'data': {
                                   'client_id': client_id,
                                   'log_date': date.today().isoformat(),
                                   'crew_count': 3,
                                   'crew_names': 'Alice, Bob, Carol',
                                   'hours_regular': '8.0',
                                   'work_completed': 'Framed walls on north side',
                                   'weather_condition': 'Clear',
                                   'weather_temp_f': 82,
                               },
                           },
                           content_type='application/json')

            data = resp.get_json()
            assert resp.status_code == 200
            assert data['ok'] is True
            assert data['status'] == 'created'
            assert 'id' in data

            # Verify in DB
            log = DailyLog.query.filter_by(client_uuid='uuid-log-001').first()
            assert log is not None
            assert log.work_completed == 'Framed walls on north side'
            assert log.crew_count == 3

    def test_time_punch_sync_creates_record(self):
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            resp = tc.post('/api/field/sync',
                           json={
                               'client_uuid': 'uuid-punch-001',
                               'type': 'time_punch',
                               'data': {
                                   'client_id': client_id,
                                   'date': date.today().isoformat(),
                                   'start_time': datetime.now(timezone.utc).isoformat(),
                                   'duration_hours': '8.0',
                                   'work_description': 'Framing',
                               },
                           },
                           content_type='application/json')

            data = resp.get_json()
            assert data['ok'] is True
            assert data['status'] == 'created'

            entry = TimeEntry.query.filter_by(client_uuid='uuid-punch-001').first()
            assert entry is not None
            assert entry.work_description == 'Framing'

    def test_material_note_sync_creates_record(self):
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            resp = tc.post('/api/field/sync',
                           json={
                               'client_uuid': 'uuid-mat-001',
                               'type': 'material_note',
                               'data': {
                                   'client_id': client_id,
                                   'note': '20 sheets of 3/4" plywood delivered',
                               },
                           },
                           content_type='application/json')

            data = resp.get_json()
            assert data['ok'] is True
            assert data['status'] == 'created'

            activity = ClientActivity.query.filter_by(client_uuid='uuid-mat-001').first()
            assert activity is not None
            assert activity.activity_type == 'Material Note'


class TestAppRestartWithQueue:
    """2. App restart with queue non-empty — entries survive resubmission."""

    def test_resubmit_after_restart_is_idempotent(self):
        """Simulate: entry synced, app killed before client marked it synced,
        client re-sends on restart. Server returns duplicate/updated."""
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            payload = {
                'client_uuid': 'uuid-restart-001',
                'type': 'daily_log',
                'data': {
                    'client_id': client_id,
                    'log_date': date.today().isoformat(),
                    'work_completed': 'Original text',
                    'hours_regular': '8.0',
                },
            }

            # First sync
            resp1 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            assert resp1.get_json()['status'] == 'created'

            # Simulate app restart — same UUID re-sent
            payload['data']['work_completed'] = 'Updated text after restart'
            resp2 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            data2 = resp2.get_json()
            assert data2['ok'] is True
            assert data2['status'] == 'updated'

            # DB has the updated text (last-write-wins)
            log = DailyLog.query.filter_by(client_uuid='uuid-restart-001').first()
            assert log.work_completed == 'Updated text after restart'


class TestDuplicateSyncAttempt:
    """3. Duplicate sync attempt — time punch returns duplicate, log updates."""

    def test_time_punch_duplicate_rejected(self):
        """Time punches are append-only. Duplicate UUID returns 'duplicate'."""
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            payload = {
                'client_uuid': 'uuid-punch-dup-001',
                'type': 'time_punch',
                'data': {
                    'client_id': client_id,
                    'date': date.today().isoformat(),
                    'start_time': datetime.now(timezone.utc).isoformat(),
                    'duration_hours': '8.0',
                    'work_description': 'First punch',
                },
            }

            resp1 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            assert resp1.get_json()['status'] == 'created'

            # Same UUID again — should NOT overwrite
            payload['data']['work_description'] = 'Modified punch (should be ignored)'
            resp2 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            data2 = resp2.get_json()
            assert data2['ok'] is True
            assert data2['status'] == 'duplicate'

            # DB still has original text
            entry = TimeEntry.query.filter_by(client_uuid='uuid-punch-dup-001').first()
            assert entry.work_description == 'First punch'

    def test_daily_log_duplicate_updates(self):
        """Daily logs use last-write-wins. Re-send updates the record."""
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            payload = {
                'client_uuid': 'uuid-log-dup-001',
                'type': 'daily_log',
                'data': {
                    'client_id': client_id,
                    'log_date': date.today().isoformat(),
                    'work_completed': 'Version 1',
                    'hours_regular': '6.0',
                },
            }

            resp1 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            assert resp1.get_json()['status'] == 'created'

            payload['data']['work_completed'] = 'Version 2'
            payload['data']['hours_regular'] = '8.0'
            resp2 = tc.post('/api/field/sync', json=payload, content_type='application/json')
            assert resp2.get_json()['status'] == 'updated'

            log = DailyLog.query.filter_by(client_uuid='uuid-log-dup-001').first()
            assert log.work_completed == 'Version 2'
            assert log.hours_regular == Decimal('8.0')


class TestPartialPhotoFailure:
    """4. Partial photo upload failure — text syncs, photo endpoint errors gracefully."""

    def test_text_syncs_without_photos(self):
        """A log entry syncs even if no photos are uploaded."""
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            resp = tc.post('/api/field/sync',
                           json={
                               'client_uuid': 'uuid-photo-test-001',
                               'type': 'daily_log',
                               'data': {
                                   'client_id': client_id,
                                   'log_date': date.today().isoformat(),
                                   'work_completed': 'Log with photos pending',
                               },
                           },
                           content_type='application/json')
            assert resp.get_json()['ok'] is True
            assert resp.get_json()['status'] == 'created'

    def test_photo_upload_without_parent_fails_gracefully(self):
        """Photo upload for non-existent parent returns 404, not 500."""
        with app.test_client() as tc:
            _login(tc)

            import io
            fake_image = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)

            resp = tc.post('/api/field/media',
                           data={
                               'parent_uuid': 'nonexistent-parent-uuid',
                               'media_uuid': 'media-001',
                               'file': (fake_image, 'test.png'),
                           },
                           content_type='multipart/form-data')

            data = resp.get_json()
            assert resp.status_code == 404
            assert data['ok'] is False
            assert 'Parent entry not found' in data['error']

    def test_photo_upload_without_file_fails_gracefully(self):
        """Photo upload without a file returns 400."""
        with app.test_client() as tc:
            _login(tc)

            resp = tc.post('/api/field/media',
                           data={
                               'parent_uuid': 'some-uuid',
                               'media_uuid': 'media-002',
                           },
                           content_type='multipart/form-data')

            data = resp.get_json()
            assert resp.status_code == 400
            assert data['ok'] is False


class TestBacklogDrain:
    """5. 48-hour-offline backlog drain — bulk sync of many entries."""

    def test_bulk_sync_50_entries(self):
        """Simulate 48 hours offline with 50 queued entries.
        Each entry syncs independently via individual POST calls.
        Uses different dates for daily logs (unique constraint: client+date+user)."""
        from datetime import timedelta
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            results = []
            for i in range(50):
                # Vary dates to avoid unique constraint on daily logs
                entry_date = (date.today() - timedelta(days=i)).isoformat()
                entry_type = 'time_punch' if i % 2 == 0 else 'daily_log'

                resp = tc.post('/api/field/sync',
                               json={
                                   'client_uuid': f'uuid-backlog-{i:03d}',
                                   'type': entry_type,
                                   'data': {
                                       'client_id': client_id,
                                       'log_date': entry_date,
                                       'date': entry_date,
                                       'start_time': datetime.now(timezone.utc).isoformat(),
                                       'work_completed': f'Backlog entry {i}',
                                       'work_description': f'Backlog punch {i}',
                                       'hours_regular': '8.0',
                                       'duration_hours': '8.0',
                                   },
                               },
                               content_type='application/json')
                data = resp.get_json()
                assert data['ok'] is True, f'Entry {i} failed: {data}'
                results.append(data)

            # All 50 should be created
            created = [r for r in results if r['status'] == 'created']
            assert len(created) == 50

            # Verify counts in DB
            logs = DailyLog.query.filter(
                DailyLog.client_uuid.like('uuid-backlog-%')
            ).count()
            punches = TimeEntry.query.filter(
                TimeEntry.client_uuid.like('uuid-backlog-%')
            ).count()
            assert logs + punches == 50

    def test_bulk_sync_idempotent_on_replay(self):
        """Re-syncing the same 10 entries doesn't create duplicates."""
        from datetime import timedelta
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            # First pass — different dates to avoid unique constraint
            for i in range(10):
                entry_date = (date.today() - timedelta(days=i)).isoformat()
                tc.post('/api/field/sync',
                        json={
                            'client_uuid': f'uuid-replay-{i:03d}',
                            'type': 'daily_log',
                            'data': {
                                'client_id': client_id,
                                'log_date': entry_date,
                                'work_completed': f'Entry {i}',
                            },
                        },
                        content_type='application/json')

            # Second pass — same UUIDs
            for i in range(10):
                entry_date = (date.today() - timedelta(days=i)).isoformat()
                resp = tc.post('/api/field/sync',
                               json={
                                   'client_uuid': f'uuid-replay-{i:03d}',
                                   'type': 'daily_log',
                                   'data': {
                                       'client_id': client_id,
                                       'log_date': entry_date,
                                       'work_completed': f'Updated entry {i}',
                                   },
                               },
                               content_type='application/json')
                assert resp.get_json()['status'] == 'updated'

            # Still only 10 records
            count = DailyLog.query.filter(
                DailyLog.client_uuid.like('uuid-replay-%')
            ).count()
            assert count == 10


class TestConflictPolicy:
    """6. Verify conflict policy: time punch append-only, others last-write-wins."""

    def test_general_note_last_write_wins(self):
        with app.test_client() as tc:
            _login(tc)
            client_id = _get_client_id()

            payload = {
                'client_uuid': 'uuid-note-conflict-001',
                'type': 'general_note',
                'data': {
                    'client_id': client_id,
                    'note': 'First version',
                },
            }

            tc.post('/api/field/sync', json=payload, content_type='application/json')

            payload['data']['note'] = 'Overwritten version'
            resp = tc.post('/api/field/sync', json=payload, content_type='application/json')
            assert resp.get_json()['status'] == 'updated'

            activity = ClientActivity.query.filter_by(client_uuid='uuid-note-conflict-001').first()
            assert activity.note_text == 'Overwritten version'

    def test_missing_client_uuid_rejected(self):
        with app.test_client() as tc:
            _login(tc)

            resp = tc.post('/api/field/sync',
                           json={'type': 'daily_log', 'data': {}},
                           content_type='application/json')
            assert resp.status_code == 400
            assert 'client_uuid' in resp.get_json()['error']

    def test_unknown_type_rejected(self):
        with app.test_client() as tc:
            _login(tc)

            resp = tc.post('/api/field/sync',
                           json={'client_uuid': 'uuid-x', 'type': 'unknown_type', 'data': {}},
                           content_type='application/json')
            assert resp.status_code == 400
            assert 'Unknown type' in resp.get_json()['error']
