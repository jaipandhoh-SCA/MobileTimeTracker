"""Field sync upsert helpers — business logic for offline-first data capture.

These functions are used by both the /api/field/sync route and tests.
Extracted from routes.py to avoid circular import issues in test suites.

Conflict policy:
  - time_punch: APPEND-ONLY. Never overwrite an existing punch UUID.
  - daily_log, material_note, general_note: LAST-WRITE-WINS. Upsert on client_uuid.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from flask_login import current_user
from app import db
from models import (
    DailyLog, TimeEntry, ClientActivity, Client, Project, ActiveClock,
    CostEntry, FieldIssue, DAILY_LOG_STATUSES,
)
from utils import calculate_duration, utc_to_pacific


def upsert_daily_log(client_uuid, data):
    """Upsert a daily log by client_uuid. Last-write-wins."""
    existing = DailyLog.query.filter_by(client_uuid=client_uuid).first()

    if existing:
        existing.crew_count = data.get('crew_count') or existing.crew_count
        existing.crew_names = data.get('crew_names') or existing.crew_names
        hrs_reg = data.get('hours_regular', '')
        if hrs_reg not in (None, ''):
            existing.hours_regular = Decimal(str(hrs_reg))
        hrs_ot = data.get('hours_overtime', '')
        if hrs_ot not in (None, ''):
            existing.hours_overtime = Decimal(str(hrs_ot))
        existing.work_completed = data.get('work_completed') or existing.work_completed
        existing.weather_condition = data.get('weather_condition') or existing.weather_condition
        temp = data.get('weather_temp_f')
        if temp not in (None, ''):
            existing.weather_temp_f = int(temp) if temp else None
        existing.weather_notes = data.get('weather_notes')
        existing.delays = data.get('delays')
        existing.safety_incidents = data.get('safety_incidents')
        existing.visitors = data.get('visitors')
        existing.materials_delivered = data.get('materials_delivered')
        if data.get('status') in DAILY_LOG_STATUSES:
            existing.status = data['status']
        return {'status': 'updated', 'id': existing.id}

    # Create new
    cid = data.get('client_id')
    if not cid:
        raise ValueError('client_id is required')
    client = Client.query.get(cid)
    if not client:
        raise ValueError(f'Client {cid} not found')

    project = Project.query.filter_by(client_id=cid, is_default=True).first()
    log_date_str = data.get('log_date', '')
    try:
        log_date = date.fromisoformat(log_date_str) if log_date_str else date.today()
    except (ValueError, TypeError):
        log_date = date.today()

    # Check natural key constraint (client + date + user)
    natural_existing = DailyLog.query.filter_by(
        client_id=cid,
        log_date=log_date,
        created_by_user_id=current_user.id,
    ).first()
    if natural_existing:
        natural_existing.client_uuid = client_uuid
        natural_existing.crew_count = data.get('crew_count') or natural_existing.crew_count
        natural_existing.crew_names = data.get('crew_names') or natural_existing.crew_names
        hrs_reg = data.get('hours_regular', '')
        if hrs_reg not in (None, ''):
            natural_existing.hours_regular = Decimal(str(hrs_reg))
        hrs_ot = data.get('hours_overtime', '')
        if hrs_ot not in (None, ''):
            natural_existing.hours_overtime = Decimal(str(hrs_ot))
        natural_existing.work_completed = data.get('work_completed') or natural_existing.work_completed
        natural_existing.weather_condition = data.get('weather_condition') or natural_existing.weather_condition
        temp = data.get('weather_temp_f')
        if temp not in (None, ''):
            natural_existing.weather_temp_f = int(temp) if temp else None
        natural_existing.weather_notes = data.get('weather_notes')
        natural_existing.delays = data.get('delays')
        if data.get('status') in DAILY_LOG_STATUSES:
            natural_existing.status = data['status']
        return {'status': 'updated', 'id': natural_existing.id}

    log = DailyLog(
        client_id=cid,
        project_id=project.id if project else None,
        log_date=log_date,
        created_by_user_id=current_user.id,
        client_uuid=client_uuid,
    )
    log.crew_count = data.get('crew_count')
    log.crew_names = data.get('crew_names')
    hrs_reg = data.get('hours_regular', '0')
    hrs_ot = data.get('hours_overtime', '0')
    log.hours_regular = Decimal(str(hrs_reg)) if hrs_reg else Decimal('0')
    log.hours_overtime = Decimal(str(hrs_ot)) if hrs_ot else Decimal('0')
    log.work_completed = data.get('work_completed')
    log.weather_condition = data.get('weather_condition')
    temp = data.get('weather_temp_f')
    log.weather_temp_f = int(temp) if temp not in (None, '') else None
    log.weather_notes = data.get('weather_notes')
    log.delays = data.get('delays')
    log.safety_incidents = data.get('safety_incidents')
    log.visitors = data.get('visitors')
    log.materials_delivered = data.get('materials_delivered')
    log.status = data.get('status', 'Draft')

    db.session.add(log)
    db.session.flush()

    # Create timeline activity
    _create_log_activity(log, client)
    return {'status': 'created', 'id': log.id}


def upsert_time_punch(client_uuid, data):
    """Insert a time punch. APPEND-ONLY — never overwrite existing.

    Time punches represent clock-in/out events that must not be mutated
    after capture (payroll integrity).
    """
    existing = TimeEntry.query.filter_by(client_uuid=client_uuid).first()
    if existing:
        return {'status': 'duplicate', 'id': existing.id}

    cid = data.get('client_id')
    punch_date_str = data.get('date', '')
    try:
        punch_date = date.fromisoformat(punch_date_str) if punch_date_str else date.today()
    except (ValueError, TypeError):
        punch_date = date.today()

    start_str = data.get('start_time')
    end_str = data.get('end_time')
    start_time = datetime.fromisoformat(start_str) if start_str else datetime.now(timezone.utc)
    end_time = datetime.fromisoformat(end_str) if end_str else None

    entry = TimeEntry(
        user_id=current_user.id,
        client_id=cid,
        cost_code_id=data.get('cost_code_id'),
        date=punch_date,
        start_time=start_time,
        end_time=end_time,
        duration_hours=Decimal(str(data['duration_hours'])) if data.get('duration_hours') else None,
        work_description=data.get('work_description', ''),
        is_manual=data.get('is_manual', False),
        client_uuid=client_uuid,
    )
    db.session.add(entry)
    db.session.flush()
    return {'status': 'created', 'id': entry.id}


def upsert_material_note(client_uuid, data):
    """Upsert a material delivery/usage note. Last-write-wins."""
    existing = ClientActivity.query.filter_by(client_uuid=client_uuid).first()
    if existing:
        existing.note_text = data.get('note', existing.note_text)
        return {'status': 'updated', 'id': existing.id}

    cid = data.get('client_id')
    if not cid:
        raise ValueError('client_id is required')

    activity = ClientActivity(
        client_id=cid,
        user_id=current_user.id,
        activity_type='Material Note',
        note_text=data.get('note', ''),
        activity_date=datetime.now(timezone.utc),
        client_uuid=client_uuid,
    )
    db.session.add(activity)
    db.session.flush()
    return {'status': 'created', 'id': activity.id}


def upsert_general_note(client_uuid, data):
    """Upsert a general field note. Last-write-wins."""
    existing = ClientActivity.query.filter_by(client_uuid=client_uuid).first()
    if existing:
        existing.note_text = data.get('note', existing.note_text)
        return {'status': 'updated', 'id': existing.id}

    cid = data.get('client_id')
    if not cid:
        raise ValueError('client_id is required')

    activity = ClientActivity(
        client_id=cid,
        user_id=current_user.id,
        activity_type='Field Note',
        note_text=data.get('note', ''),
        activity_date=datetime.now(timezone.utc),
        client_uuid=client_uuid,
    )
    db.session.add(activity)
    db.session.flush()
    return {'status': 'created', 'id': activity.id}


def upsert_clock_in(client_uuid, data):
    """Create an ActiveClock from offline sync. Idempotent — returns existing if present."""
    existing = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if existing:
        return {'status': 'already_clocked_in', 'id': existing.id}

    start_str = data.get('start_time')
    start_time = (datetime.fromisoformat(start_str) if start_str
                  else datetime.now(timezone.utc))

    clock = ActiveClock(
        user_id=current_user.id,
        start_time=start_time,
        client_id=data.get('client_id'),
        cost_code_id=data.get('cost_code_id'),
        clock_in_lat=data.get('latitude'),
        clock_in_lng=data.get('longitude'),
    )
    db.session.add(clock)
    db.session.flush()
    return {'status': 'created', 'id': clock.id}


def upsert_clock_out(client_uuid, data):
    """Close ActiveClock → TimeEntry from offline sync. Append-only dedup on client_uuid."""
    existing_entry = TimeEntry.query.filter_by(client_uuid=client_uuid).first()
    if existing_entry:
        return {'status': 'duplicate', 'id': existing_entry.id}

    active = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if not active:
        # No active clock — create TimeEntry directly from data
        start_str = data.get('start_time')
        end_str = data.get('end_time')
        start_time = datetime.fromisoformat(start_str) if start_str else datetime.now(timezone.utc)
        end_time = datetime.fromisoformat(end_str) if end_str else datetime.now(timezone.utc)
    else:
        start_time = active.start_time
        end_time_str = data.get('end_time')
        end_time = datetime.fromisoformat(end_time_str) if end_time_str else datetime.now(timezone.utc)

    duration = calculate_duration(start_time, end_time)
    work_desc = data.get('work_description', 'Clock punch')

    entry = TimeEntry(
        user_id=current_user.id,
        client_id=data.get('client_id') or (active.client_id if active else None),
        cost_code_id=data.get('cost_code_id') or (active.cost_code_id if active else None),
        date=utc_to_pacific(end_time).date(),
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration,
        work_description=work_desc,
        is_manual=False,
        client_uuid=client_uuid,
        clock_in_lat=data.get('clock_in_lat') or (active.clock_in_lat if active else None),
        clock_in_lng=data.get('clock_in_lng') or (active.clock_in_lng if active else None),
        clock_out_lat=data.get('latitude'),
        clock_out_lng=data.get('longitude'),
    )
    db.session.add(entry)
    if active:
        db.session.delete(active)
    db.session.flush()
    return {'status': 'created', 'id': entry.id}


def upsert_photo_batch(client_uuid, data):
    """Upsert a photo batch record. Creates ClientActivity as anchor, plus
    optional CostEntry (delivery) or FieldIssue (issue)."""
    existing = ClientActivity.query.filter_by(client_uuid=client_uuid).first()
    if existing:
        return {'status': 'duplicate', 'id': existing.id}

    cid = data.get('client_id')
    if not cid:
        raise ValueError('client_id is required')

    client = Client.query.get(cid)
    if not client:
        raise ValueError(f'Client {cid} not found')

    category = data.get('category', 'uncategorized')
    photo_count = data.get('photo_count', 0)
    project_id = data.get('project_id')

    # If no project_id, try default project
    if not project_id:
        proj = Project.query.filter_by(client_id=cid, is_default=True).first()
        project_id = proj.id if proj else None

    note = f"[Photo Batch] {photo_count} {category} photo(s)"

    # Create anchor activity
    activity = ClientActivity(
        client_id=cid,
        user_id=current_user.id,
        activity_type='Photo Batch',
        note_text=note,
        activity_date=datetime.now(timezone.utc),
        client_uuid=client_uuid,
    )
    db.session.add(activity)
    db.session.flush()

    result_extra = {}

    # Delivery → CostEntry (only if we have the required fields)
    if category == 'delivery' and project_id:
        cost_code_id = data.get('cost_code_id')
        if cost_code_id:
            cost_code_id = int(cost_code_id)
        else:
            # Skip CostEntry if no cost code — can't satisfy NOT NULL
            cost_code_id = None

        if cost_code_id:
            desc_parts = []
            if data.get('supplier'):
                desc_parts.append(f"Supplier: {data['supplier']}")
            if data.get('quantity_note'):
                desc_parts.append(data['quantity_note'])
            description = ' | '.join(desc_parts) or 'Delivery (photo batch)'

            entry = CostEntry(
                project_id=project_id,
                cost_code_id=cost_code_id,
                cost_type='Material',
                description=description,
                amount=Decimal('0'),
                source='photo_batch',
                source_ref_type='photo_batch',
                source_ref_id=activity.id,
                entry_date=date.today(),
                created_by_user_id=current_user.id,
            )
            db.session.add(entry)
            db.session.flush()
            result_extra['cost_entry_id'] = entry.id

    # Issue → FieldIssue
    if category == 'issue':
        issue = FieldIssue(
            client_id=cid,
            project_id=project_id,
            title=data.get('issue_title', 'Field issue'),
            description=data.get('issue_description'),
            priority=data.get('priority', 'Medium'),
            reported_by_user_id=current_user.id,
            client_uuid=client_uuid + '-issue',
        )
        db.session.add(issue)
        db.session.flush()
        result_extra['field_issue_id'] = issue.id
        # Store issue ID in activity note for photo linking
        activity.note_text = f"{note} | issue_id={issue.id}"

    return {'status': 'created', 'id': activity.id, **result_extra}


def _create_log_activity(log, client):
    """Create a ClientActivity entry so the log appears in the timeline."""
    summary_parts = []
    if log.work_completed:
        summary_parts.append(log.work_completed[:200])
    if log.delays:
        summary_parts.append(f"Delays: {log.delays[:100]}")
    note = ' | '.join(summary_parts) or 'Daily log entry'

    activity = ClientActivity(
        client_id=client.id,
        user_id=log.created_by_user_id,
        activity_type='Daily Log',
        note_text=f"[{log.log_date.strftime('%m/%d/%Y')}] {note}",
        activity_date=log.created_at or datetime.now(timezone.utc),
    )
    db.session.add(activity)
