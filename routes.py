from flask import render_template, request, redirect, url_for, session, jsonify, flash, Response, current_app, abort
from flask_login import current_user
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation
import csv
from io import StringIO, BytesIO
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from collections import defaultdict

from app import app, db, csrf
from models import (
    User, Client, TimeEntry, ActiveClock, ClientActivity, PropertyImage,
    LeadSource, ClientStatusChange, ChannelSpend, AppSetting,
    Project, CostCode, Budget, CostEntry, COST_TYPES, COST_SOURCES,
    AssemblyItem, EstimateTemplate, EstimateTemplateItem,
    Estimate, EstimateLineItem, ADU_TYPES, ESTIMATE_STATUSES,
    Proposal, Contract, DrawScheduleItem, PROPOSAL_STATUSES, CONTRACT_STATUSES,
    Document, DocumentVersion, Permit,
    DOCUMENT_FOLDERS, DOCUMENT_FOLDER_KEYS, PERMIT_STATUSES, PERMIT_TYPES,
    SchedulePhase, ScheduleTask, TaskDependency, TaskAssignment,
    Notification, NotificationPreference, TASK_STATUSES, TASK_PRIORITIES,
    DailyLog, DailyLogPhoto, WEATHER_CONDITIONS, DAILY_LOG_STATUSES,
    ChangeOrder, ChangeOrderItem, CHANGE_ORDER_STATUSES,
    Invoice, InvoiceLineItem, Payment,
    INVOICE_STATUSES, PAYMENT_METHODS,
    QBOToken, QBOMapping, QBOSyncLog,
    ClientUser, MagicLink, SelectionCategory, SelectionOption,
    ClientSelection, PortalMessage, SELECTION_STATUSES,
)
from google_auth import require_login, require_supervisor, google_auth
from utils import (
    utc_to_pacific, pacific_to_utc, calculate_duration, round_to_quarter_hour,
    format_hours, format_date_for_display, format_datetime_for_display,
    get_pay_period_dates, get_next_pay_period_dates, get_previous_pay_period_dates,
    get_last_30_days_dates, get_month_to_date_dates,
)

from utils import PACIFIC_TZ

app.register_blueprint(google_auth)

from client_portal import portal as client_portal_bp
app.register_blueprint(client_portal_bp)


def build_daily_hours(entries, period_start, period_end):
    """Build a date->hours dict for every day in the period, filling gaps with 0."""
    daily = defaultdict(float)
    for e in entries:
        if e.date and e.duration_hours:
            daily[e.date] += float(e.duration_hours)
    result = []
    current = period_start
    while current <= period_end:
        result.append({'date': current.strftime('%Y-%m-%d'), 'hours': round(daily[current], 2)})
        current += timedelta(days=1)
    return result


def _build_client_timeline(client, activities):
    """Merge all client events into a single chronological timeline."""
    events = []

    # 1. Lead created
    events.append({
        'type': 'created',
        'date': client.created_at,
        'data': {
            'source': client.lead_source,
            'source_detail': client.source_detail,
            'created_by': client.created_by,
            'initial_status': client.status,
        }
    })

    # 2. Status changes (from the structured table)
    status_changes = ClientStatusChange.query.filter_by(client_id=client.id)\
        .order_by(ClientStatusChange.changed_at).all()
    for sc in status_changes:
        events.append({
            'type': 'status_change',
            'date': sc.changed_at,
            'data': {
                'from_status': sc.from_status,
                'to_status': sc.to_status,
                'changed_by': sc.changed_by,
            }
        })

    # 3. Activities (skip "Status Change" type — covered above)
    for a in activities:
        if a.activity_type == 'Status Change':
            continue
        events.append({
            'type': 'activity',
            'date': a.activity_date,
            'data': {
                'activity_type': a.activity_type,
                'note_text': a.note_text,
                'file_name': a.file_name,
                'activity_id': a.id,
                'user': a.user,
                'next_step_description': a.next_step_description,
                'next_step_date': a.next_step_date,
            }
        })

    # 4. Property image uploads
    images = PropertyImage.query.filter_by(client_id=client.id).order_by(PropertyImage.created_at).all()
    for img in images:
        events.append({
            'type': 'upload',
            'date': img.created_at,
            'data': {
                'file_name': img.file_name,
                'uploaded_by': img.uploaded_by,
            }
        })

    # 5. Deal closed (if completed with final value)
    if client.status == 'Completed' and client.final_contract_value is not None:
        # Use the last status change to Completed as the date
        completed_change = ClientStatusChange.query.filter_by(
            client_id=client.id, to_status='Completed'
        ).order_by(ClientStatusChange.changed_at.desc()).first()
        close_date = completed_change.changed_at if completed_change else client.updated_at
        events.append({
            'type': 'deal_closed',
            'date': close_date,
            'data': {
                'final_value': client.final_contract_value,
                'opportunity_value': client.opportunity_value,
            }
        })

    # Sort chronologically
    events.sort(key=lambda e: e['date'] or datetime.min)

    # Calculate elapsed time between stage changes
    stage_durations = []
    for i, ev in enumerate(events):
        if ev['type'] == 'status_change' and ev['data'].get('from_status'):
            # Find previous status_change or created event
            prev_date = client.created_at
            for j in range(i - 1, -1, -1):
                if events[j]['type'] in ('status_change', 'created'):
                    prev_date = events[j]['date']
                    break
            if prev_date and ev['date']:
                delta = (ev['date'] - prev_date).days
                ev['data']['days_in_stage'] = delta
                ev['data']['stage_label'] = ev['data']['from_status']

    # Compute total deal age and current stage duration
    now = datetime.now(timezone.utc)
    total_age_days = (now - client.created_at).days if client.created_at else 0

    # Current stage duration: time since last status change
    last_change = ClientStatusChange.query.filter_by(client_id=client.id)\
        .order_by(ClientStatusChange.changed_at.desc()).first()
    if last_change:
        current_stage_days = (now - last_change.changed_at).days
    else:
        current_stage_days = total_age_days

    return {
        'events': events,
        'total_age_days': total_age_days,
        'current_stage': client.status,
        'current_stage_days': current_stage_days,
    }


@app.before_request
def make_session_permanent():
    session.permanent = True


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.jpg'))


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('landing.html')


@app.route('/fresh-login')
def fresh_login():
    """Force a completely fresh login by clearing all session data and redirecting to Google account selection"""
    from flask_login import logout_user
    
    # Log out current user if logged in
    if current_user.is_authenticated:
        logout_user()
    
    # Clear entire Flask session
    session.clear()
    
    # Redirect directly to Google login (which has prompt=select_account)
    # This will show the account chooser every time
    return redirect(url_for('google_auth.login'))


def _get_integration_status():
    """Return which integrations are actually connected (env vars set)."""
    import os
    ghl = bool(os.environ.get('GHL_API_KEY')) and bool(os.environ.get('GHL_LOCATION_ID'))
    meta = bool(os.environ.get('META_ADS_ACCESS_TOKEN')) and bool(os.environ.get('META_ADS_ACCOUNT_ID'))
    google_ads = bool(os.environ.get('GOOGLE_ADS_API_KEY'))  # future
    return {
        'ghl': ghl,
        'meta': meta,
        'google_ads': google_ads,
        'any_connected': ghl or meta or google_ads,
        'connected_names': [n for n, v in [('GoHighLevel', ghl), ('Meta', meta), ('Google', google_ads)] if v],
        'ghl_last_sync': AppSetting.get('ghl_last_sync'),
        'meta_last_sync': AppSetting.get('meta_last_sync'),
    }


# Canonical channels — always shown, in this order
CANONICAL_CHANNELS = [
    {'key': 'organic',    'name': 'Organic',       'channel_type': 'organic_social', 'requires': None},
    {'key': 'meta_ads',   'name': 'Meta Ads',      'channel_type': 'paid_ads',       'requires': 'meta'},
    {'key': 'google_ads', 'name': 'Google Ads',     'channel_type': 'paid_ads',       'requires': 'google_ads'},
    {'key': 'calls',      'name': 'Calls',          'channel_type': 'phone',          'requires': 'ghl'},
    {'key': 'crm',        'name': 'CRM pipeline',   'channel_type': 'other',          'requires': 'ghl'},
    {'key': 'referral',   'name': 'Referral',        'channel_type': 'referral',       'requires': None},
]

# Map canonical channel keys to lead source name patterns
_CHANNEL_SOURCE_PATTERNS = {
    'organic':    ['instagram organic', 'facebook organic', 'website', 'seo'],
    'meta_ads':   ['meta ads'],
    'google_ads': ['google ads'],
    'calls':      ['phone call', 'phone'],
    'crm':        ['repeat client', 'other'],
    'referral':   ['referral'],
}


def _build_channel_cards():
    """Build per-channel performance cards for the current month.

    Always returns one card per canonical channel. Each card has:
    - connected: whether the required integration is configured
    - has_data: whether there's any spend or leads this month
    """
    import pytz
    from utils import PACIFIC_TZ

    integrations = _get_integration_status()

    now_pacific = datetime.now(PACIFIC_TZ)
    month_start = now_pacific.replace(day=1).date()
    if now_pacific.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    month_start_utc = PACIFIC_TZ.localize(datetime.combine(month_start, datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)
    month_end_utc = PACIFIC_TZ.localize(datetime.combine(month_end, datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)

    # Previous month boundaries (for deltas)
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)
    prev_month_start_utc = PACIFIC_TZ.localize(datetime.combine(prev_month_start, datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)
    prev_month_end_utc = month_start_utc

    # Get all active lead sources and build lookup
    sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()
    source_map = {s.id: s for s in sources}
    source_ids = [s.id for s in sources]

    # Map each source to a canonical channel key
    source_to_channel = {}
    for s in sources:
        name_lower = s.name.lower()
        for chan_key, patterns in _CHANNEL_SOURCE_PATTERNS.items():
            if any(p in name_lower for p in patterns):
                source_to_channel[s.id] = chan_key
                break

    # Query spend and clients only if we have sources
    spend_by_channel = defaultdict(float)
    leads_by_channel = defaultdict(int)
    revenue_by_channel = defaultdict(float)
    won_by_channel = defaultdict(int)
    leads_last_by_channel = defaultdict(int)

    if source_ids:
        spend_entries = ChannelSpend.query.filter(
            ChannelSpend.lead_source_id.in_(source_ids),
            ChannelSpend.period_month == month_start
        ).all()
        for e in spend_entries:
            chan = source_to_channel.get(e.lead_source_id)
            if chan:
                spend_by_channel[chan] += float(e.amount)

        clients_this_month = Client.query.filter(
            Client.is_active == True,
            Client.created_at >= month_start_utc,
            Client.created_at < month_end_utc,
            Client.lead_source_id.in_(source_ids)
        ).all()
        for c in clients_this_month:
            chan = source_to_channel.get(c.lead_source_id)
            if chan:
                leads_by_channel[chan] += 1
                if c.status in ('Active', 'Completed'):
                    won_by_channel[chan] += 1
                    revenue_by_channel[chan] += float(c.final_contract_value or c.opportunity_value or 0)

        clients_last_month = Client.query.filter(
            Client.is_active == True,
            Client.created_at >= prev_month_start_utc,
            Client.created_at < prev_month_end_utc,
            Client.lead_source_id.in_(source_ids)
        ).all()
        for c in clients_last_month:
            chan = source_to_channel.get(c.lead_source_id)
            if chan:
                leads_last_by_channel[chan] += 1

    # Build one card per canonical channel
    cards = []
    for ch in CANONICAL_CHANNELS:
        key = ch['key']
        requires = ch['requires']

        # Channels with no integration requirement are always "connected"
        if requires is None:
            connected = True
        else:
            connected = integrations.get(requires, False)

        spend = spend_by_channel.get(key, 0)
        leads = leads_by_channel.get(key, 0)
        rev = revenue_by_channel.get(key, 0)
        won = won_by_channel.get(key, 0)
        leads_prev = leads_last_by_channel.get(key, 0)

        has_data = spend > 0 or leads > 0 or rev > 0

        cpl = spend / leads if leads and spend else None
        roi = rev / spend if spend else None
        close_rate = (won / leads * 100) if leads else None
        lead_delta = leads - leads_prev if leads_prev > 0 else None

        cards.append({
            'source_name': ch['name'],
            'channel_type': ch['channel_type'],
            'connected': connected,
            'has_data': has_data,
            'spend': spend,
            'leads': leads,
            'cpl': cpl,
            'revenue': rev,
            'roi': roi,
            'won': won,
            'close_rate': close_rate,
            'lead_delta': lead_delta,
        })

    return cards


@app.route('/styleguide')
@require_supervisor
def styleguide():
    return render_template('styleguide.html')


@app.route('/home')
@require_login
def home():
    filter_user_id = request.args.get('filter_user')
    all_users = []
    selected_user = None
    
    if current_user.is_supervisor:
        all_users = User.query.order_by(User.first_name, User.last_name).all()
        
        if filter_user_id:
            selected_user = User.query.get(filter_user_id)
            if selected_user:
                my_clients = Client.query.filter_by(assigned_to_user_id=filter_user_id, is_active=True).all()
                recent_clients = Client.query.options(joinedload(Client.assigned_to)).filter_by(assigned_to_user_id=filter_user_id, is_active=True).order_by(Client.created_at.desc()).limit(5).all()
            else:
                my_clients = Client.query.filter_by(is_active=True).all()
                recent_clients = Client.query.options(joinedload(Client.assigned_to)).filter_by(is_active=True).order_by(Client.created_at.desc()).limit(5).all()
        else:
            my_clients = Client.query.filter_by(is_active=True).all()
            recent_clients = Client.query.options(joinedload(Client.assigned_to)).filter_by(is_active=True).order_by(Client.created_at.desc()).limit(5).all()
    else:
        my_clients = Client.query.filter_by(assigned_to_user_id=current_user.id, is_active=True).all()
        recent_clients = Client.query.options(joinedload(Client.assigned_to)).filter_by(assigned_to_user_id=current_user.id, is_active=True).order_by(Client.created_at.desc()).limit(5).all()
    
    status_counts = {'Lead': 0, 'Prospect': 0, 'Active': 0, 'Completed': 0, 'On Hold': 0}
    status_values = {'Lead': 0, 'Prospect': 0, 'Active': 0, 'Completed': 0, 'On Hold': 0}
    total_value = 0
    
    for client in my_clients:
        if client.status in status_counts:
            status_counts[client.status] += 1
            client_value = float(client.opportunity_value or 0)
            status_values[client.status] += client_value
            total_value += client_value
    
    if current_user.is_supervisor:
        if filter_user_id and selected_user:
            next_steps = ClientActivity.query.join(Client).filter(
                Client.assigned_to_user_id == filter_user_id,
                ClientActivity.next_step_date.isnot(None),
                ClientActivity.next_step_date >= datetime.now(timezone.utc)
            ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
            
            recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).filter(
                Client.assigned_to_user_id == filter_user_id
            ).order_by(ClientActivity.activity_date.desc()).limit(5).all()
        else:
            next_steps = ClientActivity.query.join(Client).filter(
                ClientActivity.next_step_date.isnot(None),
                ClientActivity.next_step_date >= datetime.now(timezone.utc)
            ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
            
            recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).order_by(
                ClientActivity.activity_date.desc()
            ).limit(5).all()
    else:
        next_steps = ClientActivity.query.join(Client).filter(
            Client.assigned_to_user_id == current_user.id,
            ClientActivity.next_step_date.isnot(None),
            ClientActivity.next_step_date >= datetime.now(timezone.utc)
        ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
        
        recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).filter(
            Client.assigned_to_user_id == current_user.id
        ).order_by(ClientActivity.activity_date.desc()).limit(5).all()
    
    # --- Compute Mon-Sun Pacific week boundaries ---
    from utils import PACIFIC_TZ
    import pytz
    now_pacific = datetime.now(PACIFIC_TZ)
    today = now_pacific.date()
    # Monday of this week
    this_week_start = today - timedelta(days=today.weekday())
    this_week_end = this_week_start + timedelta(days=6)
    # Last week for deltas
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)

    # Convert to UTC datetimes for queries
    this_week_start_utc = PACIFIC_TZ.localize(datetime.combine(this_week_start, datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)
    last_week_start_utc = PACIFIC_TZ.localize(datetime.combine(last_week_start, datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)
    last_week_end_utc = PACIFIC_TZ.localize(datetime.combine(last_week_end + timedelta(days=1), datetime.min.time())).astimezone(pytz.utc).replace(tzinfo=None)

    # --- Helper: scope filter for queries ---
    is_company_wide = current_user.is_supervisor and not selected_user
    target_user_id = (selected_user.id if selected_user else current_user.id) if not is_company_wide else None

    def _user_filter(query):
        if not is_company_wide:
            return query.filter(Client.assigned_to_user_id == target_user_id)
        return query

    # === NEW LEADS THIS WEEK (with lead source breakdown) ===
    new_leads_q = _user_filter(Client.query.filter(
        Client.is_active == True,
        Client.created_at >= this_week_start_utc
    ))
    new_leads_this_week_list = new_leads_q.options(joinedload(Client.lead_source)).all()
    new_leads_this_week = len(new_leads_this_week_list)

    # Breakdown by source
    lead_source_counts = defaultdict(int)
    for c in new_leads_this_week_list:
        source_name = c.lead_source.name if c.lead_source else 'Unknown'
        lead_source_counts[source_name] += 1
    # Sort descending by count
    lead_source_breakdown = sorted(lead_source_counts.items(), key=lambda x: -x[1])

    # Last week's leads for delta
    last_week_leads_q = _user_filter(Client.query.filter(
        Client.is_active == True,
        Client.created_at >= last_week_start_utc,
        Client.created_at < this_week_start_utc
    ))
    last_week_leads_count = last_week_leads_q.count()

    # === PIPELINE MOVEMENT (status changes this week) ===
    # We detect movement via ClientActivity entries of type "Status Change" this week
    pipeline_moves_q = ClientActivity.query.join(Client).filter(
        Client.is_active == True,
        ClientActivity.activity_type == 'Status Change',
        ClientActivity.activity_date >= this_week_start_utc
    )
    if not is_company_wide:
        pipeline_moves_q = pipeline_moves_q.filter(Client.assigned_to_user_id == target_user_id)
    pipeline_moves = pipeline_moves_q.options(joinedload(ClientActivity.client)).all()

    # Group by transition description
    pipeline_move_summary = defaultdict(list)
    for pm in pipeline_moves:
        pipeline_move_summary[pm.note_text].append(pm.client.name)

    # === DEALS CLOSED THIS WEEK ===
    completed_q = _user_filter(Client.query.filter(
        Client.status == 'Completed',
        Client.is_active == True,
        Client.updated_at >= this_week_start_utc
    ))
    completed_this_week = completed_q.all()
    completed_count = len(completed_this_week)
    completed_revenue = sum(float(c.final_contract_value or c.opportunity_value or 0) for c in completed_this_week)

    # Last week's closed for delta
    last_completed_q = _user_filter(Client.query.filter(
        Client.status == 'Completed',
        Client.is_active == True,
        Client.updated_at >= last_week_start_utc,
        Client.updated_at < this_week_start_utc
    ))
    last_week_completed_count = last_completed_q.count()

    # === NEEDS ATTENTION (unified) ===
    now = datetime.now(timezone.utc)
    stale_amber_days = app.config.get('STALE_AMBER_DAYS', 14)
    stale_red_days = app.config.get('STALE_RED_DAYS', 28)
    active_statuses = ['Lead', 'Prospect', 'Active']

    from sqlalchemy import func as sa_func

    # Overdue next steps
    overdue_q = ClientActivity.query.join(Client).filter(
        Client.is_active == True,
        Client.status.in_(active_statuses),
        ClientActivity.next_step_date.isnot(None),
        ClientActivity.next_step_date < now
    )
    if not is_company_wide:
        overdue_q = overdue_q.filter(Client.assigned_to_user_id == target_user_id)
    overdue_steps = overdue_q.options(
        joinedload(ClientActivity.client).joinedload(Client.assigned_to)
    ).order_by(ClientActivity.next_step_date.asc()).all()

    # Clients with no next step scheduled
    has_next_step_ids = db.session.query(ClientActivity.client_id).filter(
        ClientActivity.next_step_date.isnot(None),
        ClientActivity.next_step_date >= now
    ).distinct().subquery()

    no_next_step_q = Client.query.filter(
        Client.is_active == True,
        Client.status.in_(active_statuses),
        ~Client.id.in_(db.session.query(has_next_step_ids))
    )
    if not is_company_wide:
        no_next_step_q = no_next_step_q.filter(Client.assigned_to_user_id == target_user_id)
    clients_no_next_step = no_next_step_q.options(joinedload(Client.assigned_to)).all()

    # Stale clients
    stale_threshold = now - timedelta(days=stale_amber_days)
    stale_q = _user_filter(Client.query.filter(
        Client.is_active == True,
        Client.status.in_(active_statuses),
        Client.updated_at < stale_threshold
    ))
    stale_clients = stale_q.options(joinedload(Client.assigned_to)).order_by(Client.updated_at.asc()).all()

    # Clients missing lead source
    missing_source_q = _user_filter(Client.query.filter(
        Client.is_active == True,
        Client.status.in_(active_statuses),
        Client.lead_source_id.is_(None)
    ))
    clients_missing_source = missing_source_q.options(joinedload(Client.assigned_to)).all()

    # Build unified attention_items list
    attention_items = []
    seen_client_ids = set()

    # 1. Overdue steps (deduplicate to one per client - oldest overdue)
    overdue_by_client = {}
    for activity in overdue_steps:
        cid = activity.client_id
        if cid not in overdue_by_client:
            overdue_by_client[cid] = activity
    for cid, activity in overdue_by_client.items():
        step_date = activity.next_step_date
        if step_date.tzinfo is None:
            step_date = step_date.replace(tzinfo=timezone.utc)
        days_overdue = (now - step_date).days
        attention_items.append({
            'client': activity.client,
            'issue_type': 'overdue_step',
            'label': 'Next step overdue',
            'detail': activity.next_step_description or '',
            'days': days_overdue,
            'severity': 'red' if days_overdue >= 7 else 'amber',
            'extra_issues': []
        })
        seen_client_ids.add(cid)

    # 2. No next step
    for client in clients_no_next_step:
        if client.id not in seen_client_ids:
            attention_items.append({
                'client': client,
                'issue_type': 'no_next_step',
                'label': 'No next step set',
                'detail': '',
                'days': 0,
                'severity': 'amber',
                'extra_issues': []
            })
            seen_client_ids.add(client.id)

    # 3. Stale
    for client in stale_clients:
        days_stale = (now - client.updated_at).days
        severity = 'red' if days_stale >= stale_red_days else 'amber'
        if client.id in seen_client_ids:
            for item in attention_items:
                if item['client'].id == client.id:
                    item['extra_issues'].append({
                        'issue_type': 'stale',
                        'label': f'No activity in {days_stale} days',
                        'days': days_stale,
                        'severity': severity
                    })
                    if severity == 'red':
                        item['severity'] = 'red'
                    break
        else:
            attention_items.append({
                'client': client,
                'issue_type': 'stale',
                'label': f'No activity in {days_stale} days',
                'detail': '',
                'days': days_stale,
                'severity': severity,
                'extra_issues': []
            })
            seen_client_ids.add(client.id)

    # 4. Missing lead source
    for client in clients_missing_source:
        if client.id in seen_client_ids:
            for item in attention_items:
                if item['client'].id == client.id:
                    item['extra_issues'].append({
                        'issue_type': 'missing_source',
                        'label': 'Missing lead source',
                        'days': 0,
                        'severity': 'amber'
                    })
                    break
        else:
            attention_items.append({
                'client': client,
                'issue_type': 'missing_source',
                'label': 'Missing lead source',
                'detail': '',
                'days': 0,
                'severity': 'amber',
                'extra_issues': []
            })
            seen_client_ids.add(client.id)

    # Sort: red first, then by days desc
    attention_items.sort(key=lambda x: (0 if x['severity'] == 'red' else 1, -x['days']))

    # Per-rep summary for supervisors
    attention_rep_summary = []
    if current_user.is_supervisor and not selected_user and attention_items:
        rep_counts = defaultdict(int)
        for item in attention_items:
            rep = item['client'].assigned_to
            name = rep.first_name if rep else 'Unassigned'
            rep_counts[name] += 1
        attention_rep_summary = sorted(rep_counts.items(), key=lambda x: -x[1])

    return render_template('home.html',
                         my_clients=my_clients,
                         recent_clients=recent_clients,
                         status_counts=status_counts,
                         status_values=status_values,
                         total_value=total_value,
                         next_steps=next_steps,
                         recent_activities=recent_activities,
                         all_users=all_users,
                         selected_user=selected_user,
                         new_leads_this_week=new_leads_this_week,
                         lead_source_breakdown=lead_source_breakdown,
                         last_week_leads_count=last_week_leads_count,
                         pipeline_moves=pipeline_moves,
                         pipeline_move_summary=pipeline_move_summary,
                         completed_count=completed_count,
                         completed_revenue=completed_revenue,
                         last_week_completed_count=last_week_completed_count,
                         overdue_steps=overdue_steps,
                         clients_no_next_step=clients_no_next_step,
                         stale_clients=stale_clients,
                         attention_items=attention_items,
                         attention_rep_summary=attention_rep_summary,
                         stale_amber_days=stale_amber_days,
                         stale_red_days=stale_red_days,
                         missing_source_count=Client.query.filter(Client.lead_source_id.is_(None), Client.is_active == True).count() if current_user.is_supervisor else 0,
                         channel_cards=_build_channel_cards() if current_user.is_supervisor else [],
                         integrations=_get_integration_status() if current_user.is_supervisor else {})


# --- Time Tracking Routes ---

@app.route('/clock/start', methods=['POST'])
@require_login
def start_clock():
    existing = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if existing:
        flash('You already have an active clock running.', 'warning')
        return redirect(url_for('home'))

    new_clock = ActiveClock(user_id=current_user.id, start_time=datetime.now(timezone.utc))
    db.session.add(new_clock)
    db.session.commit()

    flash('Clock started successfully!', 'success')
    return redirect(url_for('home'))


@app.route('/clock/status')
@require_login
def clock_status():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if active_clock:
        elapsed = (datetime.now(timezone.utc) - active_clock.start_time).total_seconds()
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return jsonify({
            'active': True,
            'elapsed': f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            'start_time': format_datetime_for_display(active_clock.start_time),
            'break_15_taken': active_clock.break_15_taken,
            'lunch_taken': active_clock.lunch_taken,
            'elapsed_seconds': int(elapsed)
        })
    return jsonify({'active': False})


@app.route('/clock/break15', methods=['POST'])
@require_login
def take_break_15():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if not active_clock:
        return jsonify({'success': False, 'message': 'No active clock found'}), 400

    if active_clock.break_15_taken:
        return jsonify({'success': False, 'message': '15-minute break already taken'}), 400

    elapsed = (datetime.now(timezone.utc) - active_clock.start_time).total_seconds()
    if elapsed < 3600:
        return jsonify({'success': False, 'message': 'Must work at least 1 hour before taking break'}), 400

    active_clock.break_15_taken = True
    db.session.commit()

    return jsonify({'success': True, 'message': '15-minute break recorded'})


@app.route('/clock/lunch', methods=['POST'])
@require_login
def take_lunch():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if not active_clock:
        return jsonify({'success': False, 'message': 'No active clock found'}), 400

    if active_clock.lunch_taken:
        return jsonify({'success': False, 'message': 'Lunch break already taken'}), 400

    elapsed = (datetime.now(timezone.utc) - active_clock.start_time).total_seconds()
    if elapsed < 7200:
        return jsonify({'success': False, 'message': 'Must work at least 2 hours before taking lunch'}), 400

    active_clock.lunch_taken = True
    db.session.commit()

    return jsonify({'success': True, 'message': '1-hour lunch break recorded'})


@app.route('/clock/stop', methods=['GET', 'POST'])
@require_login
def stop_clock():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if not active_clock:
        flash('No active clock found.', 'error')
        return redirect(url_for('home'))

    if request.method == 'GET':
        clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
        cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
        duration = calculate_duration(active_clock.start_time, datetime.now(timezone.utc))
        return render_template('stop_clock.html',
                             active_clock=active_clock,
                             clients=clients,
                             cost_codes=cost_codes,
                             duration=duration)

    client_id = request.form.get('client_id')
    cost_code_id = request.form.get('cost_code_id') or None
    new_client_name = request.form.get('new_client_name', '').strip()
    new_client_address = request.form.get('new_client_address', '').strip()
    work_description = request.form.get('work_description', '').strip()

    if client_id == 'daily_activities':
        client_id = None
    elif new_client_name and new_client_address:
        client = Client(name=new_client_name, address=new_client_address, created_by_user_id=current_user.id)
        db.session.add(client)
        db.session.flush()
        client_id = client.id
    elif not client_id:
        flash('Please select a client or add a new one.', 'error')
        return redirect(url_for('stop_clock'))

    if not work_description or len(work_description) < 10:
        flash('Work description must be at least 10 characters.', 'error')
        return redirect(url_for('stop_clock'))

    end_time = datetime.now(timezone.utc)
    duration = calculate_duration(active_clock.start_time, end_time)

    break_deduction = Decimal('0')
    if active_clock.break_15_taken:
        break_deduction += Decimal('0.25')
    if active_clock.lunch_taken:
        break_deduction += Decimal('1.0')

    final_duration = max(Decimal('0'), duration - break_deduction)

    entry = TimeEntry(
        user_id=current_user.id,
        client_id=client_id,
        cost_code_id=cost_code_id,
        date=utc_to_pacific(end_time).date(),
        start_time=active_clock.start_time,
        end_time=end_time,
        duration_hours=final_duration,
        work_description=work_description,
        is_manual=False
    )

    db.session.add(entry)
    db.session.delete(active_clock)
    db.session.commit()

    flash(f'Shift logged: {format_hours(duration)} hours', 'success')
    return redirect(url_for('my_logs'))


@app.route('/quick-log', methods=['GET', 'POST'])
@require_login
def quick_log():
    if request.method == 'GET':
        clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
        cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
        return render_template('quick_log.html', clients=clients, cost_codes=cost_codes, today=date.today())

    entry_date = request.form.get('date')
    client_id = request.form.get('client_id')
    cost_code_id = request.form.get('cost_code_id') or None
    new_client_name = request.form.get('new_client_name', '').strip()
    new_client_address = request.form.get('new_client_address', '').strip()
    work_description = request.form.get('work_description', '').strip()
    hours = request.form.get('hours')

    try:
        entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()
    except:
        flash('Invalid date format.', 'error')
        return redirect(url_for('quick_log'))

    if entry_date > date.today():
        flash('Date cannot be in the future.', 'error')
        return redirect(url_for('quick_log'))

    if client_id == 'daily_activities':
        client_id = None
    elif new_client_name and new_client_address:
        client = Client(name=new_client_name, address=new_client_address, created_by_user_id=current_user.id)
        db.session.add(client)
        db.session.flush()
        client_id = client.id
    elif not client_id:
        flash('Please select a client or add a new one.', 'error')
        return redirect(url_for('quick_log'))

    if not work_description or len(work_description) < 10:
        flash('Work description must be at least 10 characters.', 'error')
        return redirect(url_for('quick_log'))

    try:
        hours_decimal = Decimal(hours)
        if hours_decimal <= 0 or hours_decimal > 12:
            raise ValueError()
        hours_decimal = round_to_quarter_hour(hours_decimal)
    except:
        flash('Hours must be between 0.25 and 12.00.', 'error')
        return redirect(url_for('quick_log'))

    pacific_dt = PACIFIC_TZ.localize(datetime.combine(entry_date, datetime.min.time()))
    start_time = pacific_to_utc(pacific_dt)

    entry = TimeEntry(
        user_id=current_user.id,
        client_id=client_id,
        cost_code_id=cost_code_id,
        date=entry_date,
        start_time=start_time,
        end_time=start_time,
        duration_hours=hours_decimal,
        work_description=work_description,
        is_manual=True
    )

    db.session.add(entry)
    db.session.commit()

    flash(f'Manual entry logged: {format_hours(hours_decimal)} hours', 'success')
    return redirect(url_for('my_logs'))


@app.route('/my-logs')
@require_login
def my_logs():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    client_id = request.args.get('client_id')
    timeframe = request.args.get('timeframe', 'current_period')

    if timeframe == 'current_period':
        summary_start, summary_end, summary_pay_date = get_pay_period_dates()
        summary_label = f"Current Pay Period: {format_date_for_display(summary_start)} - {format_date_for_display(summary_end)}"
    elif timeframe == 'previous_period':
        summary_start, summary_end, summary_pay_date = get_previous_pay_period_dates()
        summary_label = f"Previous Pay Period: {format_date_for_display(summary_start)} - {format_date_for_display(summary_end)}"
    elif timeframe == 'month_to_date':
        summary_start, summary_end, summary_label = get_month_to_date_dates()
        summary_pay_date = None
    else:
        summary_start, summary_end, summary_label = get_last_30_days_dates()
        summary_pay_date = None

    query = TimeEntry.query.filter_by(user_id=current_user.id)

    if date_from:
        try:
            query = query.filter(TimeEntry.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except:
            pass
    else:
        query = query.filter(TimeEntry.date >= summary_start)
        date_from = summary_start.strftime('%Y-%m-%d')

    if date_to:
        try:
            query = query.filter(TimeEntry.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except:
            pass
    else:
        query = query.filter(TimeEntry.date <= summary_end)
        date_to = summary_end.strftime('%Y-%m-%d')

    if client_id:
        query = query.filter_by(client_id=client_id)

    entries = query.order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc()).all()

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()

    approved_entries = TimeEntry.query.filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.status == 'approved',
        TimeEntry.date >= summary_start,
        TimeEntry.date <= summary_end
    ).all()

    summary_hours = sum((e.duration_hours or 0) for e in approved_entries)
    summary_billable = sum((e.duration_hours or 0) for e in approved_entries if e.client_id)
    summary_entry_count = len(approved_entries)
    summary_unique_clients = len(set(e.client_id for e in approved_entries if e.client_id))
    summary_pay = float(summary_hours) * float(current_user.hourly_rate or 0)
    daily_hours = build_daily_hours(summary_entries, summary_start, summary_end)

    return render_template('my_logs.html',
                         entries=entries,
                         clients=clients,
                         date_from=date_from,
                         date_to=date_to,
                         client_id=client_id,
                         timeframe=timeframe,
                         summary_label=summary_label,
                         summary_start=summary_start,
                         summary_end=summary_end,
                         summary_pay_date=summary_pay_date,
                         summary_hours=summary_hours,
                         summary_billable=summary_billable,
                         summary_entry_count=summary_entry_count,
                         summary_unique_clients=summary_unique_clients,
                         summary_pay=summary_pay,
                         daily_hours=daily_hours)


@app.route('/clients/<int:client_id>/quick_next_step', methods=['POST'])
@require_login
def quick_add_next_step(client_id):
    """Inline 'Add next step' from the Needs Attention section."""
    client = Client.query.get_or_404(client_id)
    step_type = request.form.get('step_type', '').strip()
    step_date_str = request.form.get('step_date', '').strip()

    if not step_type or not step_date_str:
        flash('Step type and date are required.', 'error')
        return redirect(url_for('home'))

    try:
        step_date_pacific = datetime.strptime(step_date_str, '%Y-%m-%d')
        step_date_utc = pacific_to_utc(step_date_pacific).replace(tzinfo=None)
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('home'))

    activity = ClientActivity(
        client_id=client_id,
        user_id=current_user.id,
        activity_type='Next Step Scheduled',
        note_text=f"Next step added: {step_type}",
        activity_date=datetime.now(timezone.utc),
        next_step_description=step_type,
        next_step_date=step_date_utc
    )
    db.session.add(activity)
    client.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f'Next step added for {client.name}.', 'success')
    return redirect(url_for('home'))


@app.route('/clients')
@require_login
def clients():
    search = request.args.get('search', '')
    show_all = request.args.get('show_all', 'false') == 'true'

    query = Client.query.options(joinedload(Client.lead_source))

    if not show_all:
        query = query.filter_by(is_active=True)
    
    if not current_user.is_supervisor:
        query = query.filter_by(assigned_to_user_id=current_user.id)
    
    if search:
        query = query.filter(
            db.or_(
                Client.name.ilike(f'%{search}%'),
                Client.address.ilike(f'%{search}%')
            )
        )
    
    clients = query.order_by(Client.name).all()
    
    return render_template('clients.html', clients=clients, search=search, show_all=show_all)


@app.route('/clients/create', methods=['GET', 'POST'])
@require_login
def create_client():
    if request.method == 'GET':
        lead_sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()
        return render_template('client_form.html', client=None, lead_sources=lead_sources)
    
    name = request.form.get('name', '').strip()
    address = request.form.get('address', '').strip()
    contact_name = request.form.get('contact_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    status = request.form.get('status', 'Lead').strip()
    notes = request.form.get('notes', '').strip()
    
    lot_sqft = request.form.get('lot_sqft', '').strip()
    sqft = request.form.get('sqft', '').strip()
    existing_sqft = request.form.get('existing_sqft', '').strip()
    residential_zoning = request.form.get('residential_zoning', '').strip()
    type_of_adu = request.form.get('type_of_adu', '').strip()
    desired_adu_sqft = request.form.get('desired_adu_sqft', '').strip()
    number_of_bed = request.form.get('number_of_bed', '').strip()
    number_of_bath = request.form.get('number_of_bath', '').strip()
    style = request.form.get('style', '').strip()
    key_features = request.form.get('key_features', '').strip()
    max_budget = request.form.get('max_budget', '').strip()
    financing_option = request.form.get('financing_option', '').strip()
    original_property_value = request.form.get('original_property_value', '').strip()
    expected_roi = request.form.get('expected_roi', '').strip()
    value_increase = request.form.get('value_increase', '').strip()
    new_property_value = request.form.get('new_property_value', '').strip()
    estimated_start_date = request.form.get('estimated_start_date', '').strip()
    estimated_end_date = request.form.get('estimated_end_date', '').strip()
    permitting_status = request.form.get('permitting_status', '').strip()
    lead_source_id = request.form.get('lead_source_id', '').strip()
    source_detail = request.form.get('source_detail', '').strip()

    if not name or not address:
        flash('Name and address are required.', 'error')
        return redirect(url_for('create_client'))

    if not lead_source_id:
        flash('Lead source is required.', 'error')
        return redirect(url_for('create_client'))

    from datetime import datetime

    client = Client(
        name=name,
        address=address,
        contact_name=contact_name if contact_name else None,
        phone=phone if phone else None,
        email=email if email else None,
        status=status,
        notes=notes if notes else None,
        lot_sqft=lot_sqft if lot_sqft else None,
        sqft=sqft if sqft else None,
        existing_sqft=existing_sqft if existing_sqft else None,
        residential_zoning=residential_zoning if residential_zoning else None,
        type_of_adu=type_of_adu if type_of_adu else None,
        desired_adu_sqft=desired_adu_sqft if desired_adu_sqft else None,
        number_of_bed=number_of_bed if number_of_bed else None,
        number_of_bath=number_of_bath if number_of_bath else None,
        style=style if style else None,
        key_features=key_features if key_features else None,
        max_budget=float(max_budget.replace(',', '')) if max_budget else None,
        financing_option=financing_option if financing_option else None,
        original_property_value=float(original_property_value.replace(',', '')) if original_property_value else None,
        expected_roi=float(expected_roi.replace(',', '')) if expected_roi else None,
        value_increase=float(value_increase.replace(',', '')) if value_increase else None,
        new_property_value=float(new_property_value.replace(',', '')) if new_property_value else None,
        estimated_start_date=datetime.strptime(estimated_start_date, '%Y-%m-%d').date() if estimated_start_date else None,
        estimated_end_date=datetime.strptime(estimated_end_date, '%Y-%m-%d').date() if estimated_end_date else None,
        permitting_status=permitting_status if permitting_status else None,
        lead_source_id=int(lead_source_id),
        source_detail=source_detail if source_detail else None,
        created_by_user_id=current_user.id,
        assigned_to_user_id=current_user.id
    )
    db.session.add(client)
    db.session.commit()
    
    from r2_storage_helper import build_client_prefix
    client.storage_prefix = build_client_prefix(client.name, client.address)

    # Log initial status
    db.session.add(ClientStatusChange(
        client_id=client.id,
        from_status=None,
        to_status=client.status,
        changed_by_user_id=current_user.id,
        changed_at=client.created_at or datetime.now(timezone.utc)
    ))
    db.session.commit()

    flash(f'Client "{name}" created successfully.', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    
    if request.method == 'GET':
        activities = ClientActivity.query.filter_by(client_id=client_id).order_by(ClientActivity.activity_date.desc()).all()
        all_users = User.query.filter_by(role='rep').all()
        all_users = sorted(all_users, key=lambda u: u.display_name.lower())
        lead_sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()

        # Build journey timeline
        timeline = _build_client_timeline(client, activities)

        return render_template('client_form.html', client=client, activities=activities,
                               all_users=all_users, lead_sources=lead_sources, timeline=timeline)
    
    name = request.form.get('name', '').strip()
    address = request.form.get('address', '').strip()
    contact_name = request.form.get('contact_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    status = request.form.get('status', 'Lead').strip()
    notes = request.form.get('notes', '').strip()
    
    lot_sqft = request.form.get('lot_sqft', '').strip()
    sqft = request.form.get('sqft', '').strip()
    existing_sqft = request.form.get('existing_sqft', '').strip()
    residential_zoning = request.form.get('residential_zoning', '').strip()
    type_of_adu = request.form.get('type_of_adu', '').strip()
    desired_adu_sqft = request.form.get('desired_adu_sqft', '').strip()
    number_of_bed = request.form.get('number_of_bed', '').strip()
    number_of_bath = request.form.get('number_of_bath', '').strip()
    style = request.form.get('style', '').strip()
    key_features = request.form.get('key_features', '').strip()
    max_budget = request.form.get('max_budget', '').strip()
    financing_option = request.form.get('financing_option', '').strip()
    original_property_value = request.form.get('original_property_value', '').strip()
    expected_roi = request.form.get('expected_roi', '').strip()
    value_increase = request.form.get('value_increase', '').strip()
    new_property_value = request.form.get('new_property_value', '').strip()
    estimated_start_date = request.form.get('estimated_start_date', '').strip()
    estimated_end_date = request.form.get('estimated_end_date', '').strip()
    permitting_status = request.form.get('permitting_status', '').strip()
    
    if not name or not address:
        flash('Name and address are required.', 'error')
        return redirect(url_for('edit_client', client_id=client_id))
    
    old_status = client.status
    client.name = name
    client.address = address
    client.contact_name = contact_name if contact_name else None
    client.phone = phone if phone else None
    client.email = email if email else None
    client.status = status
    client.notes = notes if notes else None

    if old_status != status:
        db.session.add(ClientStatusChange(
            client_id=client.id,
            from_status=old_status,
            to_status=status,
            changed_by_user_id=current_user.id,
            changed_at=datetime.now(timezone.utc)
        ))
    
    client.lot_sqft = lot_sqft if lot_sqft else None
    client.sqft = sqft if sqft else None
    client.existing_sqft = existing_sqft if existing_sqft else None
    client.residential_zoning = residential_zoning if residential_zoning else None
    client.type_of_adu = type_of_adu if type_of_adu else None
    client.desired_adu_sqft = desired_adu_sqft if desired_adu_sqft else None
    client.number_of_bed = number_of_bed if number_of_bed else None
    client.number_of_bath = number_of_bath if number_of_bath else None
    client.style = style if style else None
    client.key_features = key_features if key_features else None
    
    client.max_budget = float(max_budget.replace(',', '')) if max_budget else None
    client.financing_option = financing_option if financing_option else None
    client.original_property_value = float(original_property_value.replace(',', '')) if original_property_value else None
    client.expected_roi = float(expected_roi.replace(',', '')) if expected_roi else None
    client.value_increase = float(value_increase.replace(',', '')) if value_increase else None
    client.new_property_value = float(new_property_value.replace(',', '')) if new_property_value else None
    
    from datetime import datetime
    client.estimated_start_date = datetime.strptime(estimated_start_date, '%Y-%m-%d').date() if estimated_start_date else None
    client.estimated_end_date = datetime.strptime(estimated_end_date, '%Y-%m-%d').date() if estimated_end_date else None
    
    client.permitting_status = permitting_status if permitting_status else None

    lead_source_id = request.form.get('lead_source_id', '').strip()
    source_detail = request.form.get('source_detail', '').strip()
    client.lead_source_id = int(lead_source_id) if lead_source_id else None
    client.source_detail = source_detail if source_detail else None

    if current_user.is_supervisor:
        assigned_to = request.form.get('assigned_to_user_id', '').strip()
        if assigned_to:
            client.assigned_to_user_id = assigned_to

    db.session.commit()
    
    flash(f'Client "{name}" updated successfully.', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:client_id>/toggle', methods=['POST'])
@require_supervisor
def toggle_client(client_id):
    client = Client.query.get_or_404(client_id)
    client.is_active = not client.is_active
    db.session.commit()
    
    status = 'activated' if client.is_active else 'deactivated'
    flash(f'Client "{client.name}" {status}.', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:client_id>/update_status', methods=['POST'])
@require_login
def update_client_status(client_id):
    from flask import jsonify
    
    client = Client.query.get_or_404(client_id)
    new_status = request.form.get('status', '').strip()

    valid_statuses = ['Lead', 'Prospect', 'Active', 'Completed', 'On Hold', 'Lost']
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    old_status = client.status
    client.status = new_status
    # Also save final_contract_value if provided (when completing)
    final_val = request.form.get('final_contract_value', '').strip().replace(',', '').replace('$', '')
    if final_val:
        try:
            client.final_contract_value = Decimal(final_val)
        except (InvalidOperation, ValueError):
            pass

    # Log status change as activity + structured record for timeline
    if old_status != new_status:
        activity = ClientActivity(
            client_id=client.id,
            user_id=current_user.id,
            activity_type='Status Change',
            note_text=f'{old_status} → {new_status}',
            activity_date=datetime.now(timezone.utc)
        )
        db.session.add(activity)

        status_change = ClientStatusChange(
            client_id=client.id,
            from_status=old_status,
            to_status=new_status,
            changed_by_user_id=current_user.id,
            changed_at=datetime.now(timezone.utc)
        )
        db.session.add(status_change)

    # When status moves to Active, auto-carry accepted estimate into budget
    estimate_carried = False
    if old_status != new_status and new_status == 'Active':
        accepted_est = Estimate.query.filter_by(
            client_id=client.id, status='Accepted'
        ).order_by(Estimate.accepted_at.desc()).first()
        if accepted_est and not client.final_contract_value:
            project = client.default_project()
            project.contract_value = accepted_est.total
            client.final_contract_value = accepted_est.total
            estimate_carried = True

    db.session.commit()

    needs_final_value = (new_status == 'Completed' and client.final_contract_value is None)
    return jsonify({'success': True, 'status': new_status,
                    'needs_final_value': needs_final_value,
                    'estimate_carried': estimate_carried})


@app.route('/clients/<int:client_id>/update_final_value', methods=['POST'])
@require_login
def update_client_final_value(client_id):
    client = Client.query.get_or_404(client_id)
    val_str = request.form.get('final_contract_value', '').strip().replace(',', '').replace('$', '')
    if not val_str:
        return jsonify({'success': False, 'error': 'Value is required'}), 400
    try:
        client.final_contract_value = Decimal(val_str)
    except (InvalidOperation, ValueError):
        return jsonify({'success': False, 'error': 'Invalid number'}), 400
    db.session.commit()
    return jsonify({'success': True, 'final_contract_value': float(client.final_contract_value)})


@app.route('/clients/<int:client_id>/update_opportunity', methods=['POST'])
@require_login
def update_client_opportunity(client_id):
    from flask import jsonify
    from decimal import Decimal, InvalidOperation
    
    client = Client.query.get_or_404(client_id)
    opportunity_value_str = request.form.get('opportunity_value', '').strip()
    
    try:
        if opportunity_value_str == '':
            opportunity_value = Decimal('0')
        else:
            opportunity_value = Decimal(opportunity_value_str.replace(',', '').replace('$', ''))
            
            if opportunity_value < 0:
                return jsonify({'success': False, 'error': 'Value cannot be negative'}), 400
            
            if opportunity_value > 99999999.99:
                return jsonify({'success': False, 'error': 'Value is too large'}), 400
    except (InvalidOperation, ValueError):
        return jsonify({'success': False, 'error': 'Invalid number format'}), 400
    
    client.opportunity_value = opportunity_value
    db.session.commit()
    
    return jsonify({'success': True, 'opportunity_value': float(opportunity_value)})


@app.route('/clients/<int:client_id>/add_activity', methods=['POST'])
@require_login
def add_activity(client_id):
    import os
    from werkzeug.utils import secure_filename
    
    client = Client.query.get_or_404(client_id)
    
    activity_type = request.form.get('activity_type', '').strip()
    note_text = request.form.get('note_text', '').strip()
    activity_date_str = request.form.get('activity_date', '').strip()
    next_step_description = request.form.get('next_step_description', '').strip()
    next_step_date_str = request.form.get('next_step_date', '').strip()
    
    if not activity_type or not note_text or not activity_date_str:
        flash('Activity type, note, and date are required.', 'error')
        return redirect(url_for('edit_client', client_id=client_id))
    
    try:
        activity_date_pacific = datetime.strptime(activity_date_str, '%Y-%m-%dT%H:%M')
        activity_date_utc = pacific_to_utc(activity_date_pacific).replace(tzinfo=None)
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('edit_client', client_id=client_id))
    
    next_step_date_utc = None
    if next_step_date_str:
        try:
            next_step_date_pacific = datetime.strptime(next_step_date_str, '%Y-%m-%dT%H:%M')
            next_step_date_utc = pacific_to_utc(next_step_date_pacific).replace(tzinfo=None)
        except ValueError:
            flash('Invalid next step date format.', 'error')
            return redirect(url_for('edit_client', client_id=client_id))
    
    storage_key = None
    file_name = None

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:

            filename = secure_filename(file.filename)
            if not filename:
                flash('Invalid filename.', 'error')
                return redirect(url_for('edit_client', client_id=client_id))

            ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

            if ext not in current_app.config['ALLOWED_EXTENSIONS']:
                flash(f'File type .{ext} not allowed. Allowed types: PDF, DOC, DOCX, TXT, JPG, PNG, XLS, XLSX, CSV', 'error')
                return redirect(url_for('edit_client', client_id=client_id))

            if not client.storage_prefix:
                from r2_storage_helper import build_client_prefix
                client.storage_prefix = build_client_prefix(client.name, client.address)
                db.session.commit()

            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"

            try:
                import mimetypes
                from r2_storage_helper import upload_file as r2_upload

                file_content = file.read()
                mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                key = f"{client.storage_prefix}/documents/{unique_filename}"

                r2_upload(file_content, key, mime_type)

                storage_key = key
                file_name = filename
            except Exception as e:
                flash(f'Failed to upload file: {str(e)}', 'error')
                return redirect(url_for('edit_client', client_id=client_id))

    try:
        final_note_text = note_text
        if file_name:
            final_note_text = f"{note_text}\n\nAttached: {file_name}"

        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type=activity_type,
            note_text=final_note_text,
            activity_date=activity_date_utc,
            file_path=storage_key,
            file_name=file_name,
            next_step_description=next_step_description if next_step_description else None,
            next_step_date=next_step_date_utc
        )

        db.session.add(activity)
        db.session.commit()

        flash('Activity added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        if storage_key:
            try:
                from r2_storage_helper import delete_file as r2_delete
                r2_delete(storage_key)
            except:
                pass
        flash('Failed to save activity. Please try again.', 'error')

    return redirect(url_for('edit_client', client_id=client_id))


@app.route('/clients/<int:client_id>/download/<int:activity_id>')
@require_login
def download_activity_file(client_id, activity_id):
    from flask import send_file
    import os
    import io
    
    activity = ClientActivity.query.filter_by(id=activity_id, client_id=client_id).first_or_404()
    
    if not activity.file_name:
        flash('No file attached to this activity.', 'error')
        return redirect(url_for('edit_client', client_id=client_id))
    
    if activity.file_path and activity.file_path.startswith('property-files/'):
        from r2_storage_helper import generate_presigned_url
        url = generate_presigned_url(activity.file_path)
        return redirect(url)

    if activity.file_path:
        upload_folder = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
        file_path = os.path.abspath(activity.file_path)

        if not file_path.startswith(upload_folder):
            flash('Invalid file path.', 'error')
            return redirect(url_for('edit_client', client_id=client_id))

        if not os.path.exists(file_path):
            flash('File not found.', 'error')
            return redirect(url_for('edit_client', client_id=client_id))

        return send_file(file_path, as_attachment=True, download_name=activity.file_name)

    flash('File not found.', 'error')
    return redirect(url_for('edit_client', client_id=client_id))


@app.route('/clients/<int:client_id>/images/upload', methods=['POST'])
@require_login
def upload_property_image(client_id):
    from flask import jsonify
    from werkzeug.utils import secure_filename
    import mimetypes
    
    client = Client.query.get_or_404(client_id)
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400
    
    file = request.files['image']
    
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed. Only images (JPG, PNG, GIF, WebP) are accepted'}), 400
    
    if not client.storage_prefix:
        from r2_storage_helper import build_client_prefix
        client.storage_prefix = build_client_prefix(client.name, client.address)
        db.session.commit()

    try:
        from r2_storage_helper import upload_file as r2_upload

        file_content = file.read()
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        unique_filename = f"property_{timestamp}_{filename}"
        key = f"{client.storage_prefix}/property-images/{unique_filename}"

        r2_upload(file_content, key, mime_type)

        property_image = PropertyImage(
            client_id=client_id,
            file_name=filename,
            storage_key=key,
            uploaded_by_user_id=current_user.id
        )

        db.session.add(property_image)
        db.session.commit()

        return jsonify({
            'success': True,
            'image_id': property_image.id,
            'file_name': property_image.file_name,
            'image_url': url_for('view_property_image', client_id=client_id, image_id=property_image.id),
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to save image: {str(e)}'}), 500


@app.route('/clients/<int:client_id>/images/<int:image_id>')
@require_login
def view_property_image(client_id, image_id):
    from flask import send_file
    import os
    import io
    import mimetypes
    
    property_image = PropertyImage.query.filter_by(id=image_id, client_id=client_id).first_or_404()
    
    if property_image.storage_key:
        try:
            from r2_storage_helper import download_file
            file_content = download_file(property_image.storage_key)

            mime_type = mimetypes.guess_type(property_image.file_name)[0] or 'image/jpeg'

            return send_file(
                io.BytesIO(file_content),
                mimetype=mime_type,
                as_attachment=False
            )
        except Exception as e:
            flash(f'Error loading image: {str(e)}', 'error')
            return redirect(url_for('edit_client', client_id=client_id))
    
    if property_image.file_path:
        upload_folder = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
        file_path = os.path.abspath(property_image.file_path)
        
        if not file_path.startswith(upload_folder):
            abort(403)
        
        if not os.path.exists(file_path):
            abort(404)
        
        return send_file(file_path)
    
    abort(404)


@app.route('/clients/<int:client_id>/images/<int:image_id>', methods=['DELETE'])
@require_login
def delete_property_image(client_id, image_id):
    from flask import jsonify
    import os
    
    property_image = PropertyImage.query.filter_by(id=image_id, client_id=client_id).first_or_404()
    
    r2_key = property_image.storage_key
    file_path = property_image.file_path

    try:
        db.session.delete(property_image)
        db.session.commit()

        if r2_key:
            try:
                from r2_storage_helper import delete_file as r2_delete
                r2_delete(r2_key)
            except Exception as e:
                print(f"Warning: Could not delete file from R2: {e}")

        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to delete image'}), 500


@app.route('/clients/<int:client_id>/upload_to_folder', methods=['POST'])
@require_login
def upload_to_folder(client_id):
    from flask import jsonify
    from werkzeug.utils import secure_filename
    import mimetypes
    
    client = Client.query.get_or_404(client_id)
    folder_type = request.form.get('folder_type')
    
    if not folder_type or folder_type not in ['property_images', 'documents', 'contracts']:
        return jsonify({'success': False, 'error': 'Invalid folder type'}), 400
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if folder_type == 'property_images':
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Only images (JPG, PNG, GIF, WebP) allowed'}), 400
    elif folder_type == 'documents':
        ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'csv'}
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Only documents (PDF, DOC, TXT, XLS) allowed'}), 400
    elif folder_type == 'contracts':
        ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Only PDF or DOC files allowed'}), 400
    
    if not client.storage_prefix:
        from r2_storage_helper import build_client_prefix
        client.storage_prefix = build_client_prefix(client.name, client.address)
        db.session.commit()

    folder_key_segment = {
        'property_images': 'property-images',
        'documents': 'documents',
        'contracts': 'contracts',
    }

    try:
        from r2_storage_helper import upload_file as r2_upload

        file_content = file.read()
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        key = f"{client.storage_prefix}/{folder_key_segment[folder_type]}/{unique_filename}"

        r2_upload(file_content, key, mime_type)

        activity_type_map = {
            'property_images': 'Property image uploaded',
            'documents': 'Document uploaded',
            'contracts': 'Contract uploaded'
        }

        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type=activity_type_map[folder_type],
            note_text=f"Uploaded {filename}",
            activity_date=datetime.now(timezone.utc),
            file_path=key,
            file_name=filename
        )

        db.session.add(activity)
        db.session.commit()

        return jsonify({'success': True, 'file_name': filename})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to upload file: {str(e)}'}), 500


# --- Payroll / Admin Time Tracking Routes ---


def _sync_time_entry_cost(entry, approver_id):
    """Create/update a CostEntry when a time entry is approved.

    Snapshots the employee's rate, burden multiplier, and computed amount
    so job-cost data is immutable once posted.  Upserts on the unique
    time_entry_id column for idempotency.
    """
    if not entry.client_id or not entry.cost_code_id:
        return
    client = Client.query.get(entry.client_id)
    if not client:
        return
    project = client.default_project()
    employee = entry.user
    rate = Decimal(str(employee.hourly_rate or 0))
    hours = Decimal(str(entry.duration_hours or 0))
    burden = employee.effective_burden_multiplier()
    amount = (rate * hours * burden).quantize(Decimal('0.01'))
    CostEntry.upsert_for_time_entry(
        time_entry_id=entry.id,
        project_id=project.id,
        cost_code_id=entry.cost_code_id,
        cost_type='Labor',
        source='time',
        user_id=employee.id,
        raw_hours=hours,
        hourly_rate=rate,
        burden_multiplier=burden,
        amount=amount,
        description=entry.work_description[:500] if entry.work_description else None,
        entry_date=entry.date,
        committed=False,
        created_by_user_id=approver_id,
    )


def _remove_time_entry_cost(entry):
    """Remove the CostEntry when a time entry is unapproved/rejected."""
    ce = CostEntry.query.filter_by(time_entry_id=entry.id).first()
    if ce:
        db.session.delete(ce)


@app.route('/admin')
@require_supervisor
def admin_dashboard():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rep_id = request.args.get('rep_id')
    client_id = request.args.get('client_id')

    first_day_of_month = date.today().replace(day=1)
    default_date_from = first_day_of_month.strftime('%Y-%m-%d')

    filters_applied = bool(
        (date_from and date_from != default_date_from) or
        date_to or
        rep_id or
        client_id
    )

    query = TimeEntry.query

    if date_from:
        try:
            query = query.filter(TimeEntry.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except:
            pass
    else:
        query = query.filter(TimeEntry.date >= first_day_of_month)
        date_from = default_date_from

    if date_to:
        try:
            query = query.filter(TimeEntry.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except:
            pass

    if rep_id:
        query = query.filter_by(user_id=rep_id)

    if client_id:
        query = query.filter_by(client_id=client_id)

    entries = query.order_by(TimeEntry.date.desc()).all()

    approved_entries = [e for e in entries if e.status == 'approved']
    pending_entries = [e for e in entries if e.status == 'pending']

    total_hours = sum((e.duration_hours or 0) for e in approved_entries)
    total_billable = sum((e.duration_hours or 0) for e in approved_entries if e.client_id)
    pending_hours = sum((e.duration_hours or 0) for e in pending_entries)
    entry_count = len(entries)
    unique_clients = len(set(e.client_id for e in approved_entries if e.client_id))

    reps = User.query.filter_by(role='rep').order_by(User.first_name).all()
    supervisors = User.query.filter_by(role='supervisor').order_by(User.first_name).all()
    all_users = reps + supervisors
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()

    current_period_start, current_period_end, current_pay_date = get_pay_period_dates()
    next_period_start, next_period_end, next_pay_date = get_next_pay_period_dates()

    payroll_data = []
    for rep in all_users:
        cur_approved = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.status == 'approved',
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end,
        ).all()
        cur_hours = sum((e.duration_hours or 0) for e in cur_approved)
        cur_pay = float(cur_hours) * float(rep.hourly_rate or 0)
        cur_pending = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.status == 'pending',
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end,
        ).count()

        # Costed labor from CostEntries for this employee in current period
        costed_labor = float(db.session.query(
            func.coalesce(func.sum(CostEntry.amount), 0)
        ).filter(
            CostEntry.user_id == rep.id,
            CostEntry.cost_type == 'Labor',
            CostEntry.source == 'time',
            CostEntry.entry_date >= current_period_start,
            CostEntry.entry_date <= current_period_end,
        ).scalar())
        cost_variance = cur_pay - costed_labor

        nxt_approved = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.status == 'approved',
            TimeEntry.date >= next_period_start,
            TimeEntry.date <= next_period_end,
        ).all()
        nxt_hours = sum((e.duration_hours or 0) for e in nxt_approved)
        nxt_pay = float(nxt_hours) * float(rep.hourly_rate or 0)

        if cur_hours > 0 or nxt_hours > 0 or cur_pending > 0:
            payroll_data.append({
                'rep': rep,
                'current_hours': float(cur_hours),
                'current_pay': cur_pay,
                'current_pending': cur_pending,
                'costed_labor': costed_labor,
                'cost_variance': cost_variance,
                'next_hours': float(nxt_hours),
                'next_pay': nxt_pay,
            })

    filtered_payroll_data = None
    filtered_date_from = None
    filtered_date_to = None

    if filters_applied:
        try:
            filtered_date_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
        except:
            filtered_date_from = None

        try:
            filtered_date_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        except:
            filtered_date_to = None

        if rep_id:
            filtered_reps = [User.query.get(rep_id)] if User.query.get(rep_id) else []
        else:
            filtered_reps = reps

        filtered_payroll_data = []
        for rep in filtered_reps:
            filtered_query = TimeEntry.query.filter_by(user_id=rep.id).filter(
                TimeEntry.status == 'approved'
            )

            if filtered_date_from:
                filtered_query = filtered_query.filter(TimeEntry.date >= filtered_date_from)

            if filtered_date_to:
                filtered_query = filtered_query.filter(TimeEntry.date <= filtered_date_to)

            if client_id:
                filtered_query = filtered_query.filter_by(client_id=client_id)

            filtered_hours = filtered_query.all()
            filtered_total_hours = sum((e.duration_hours or 0) for e in filtered_hours)
            filtered_pay = float(filtered_total_hours) * float(rep.hourly_rate or 0)

            if filtered_total_hours > 0:
                filtered_payroll_data.append({
                    'rep': rep,
                    'hours': float(filtered_total_hours),
                    'pay': filtered_pay
                })

    # --- Job cost reconciliation: budgeted labor vs costed labor per project ---
    recon_data = []
    active_projects = Project.query.join(Client).filter(Client.is_active.is_(True)).all()
    for proj in active_projects:
        budgeted = sum(
            b.amount for b in Budget.query.filter_by(project_id=proj.id, cost_type='Labor').all()
        )
        labor_ces = CostEntry.query.filter_by(
            project_id=proj.id, cost_type='Labor', source='time',
        ).all()
        actual = sum(ce.amount for ce in labor_ces)
        variance = budgeted - actual
        # Per-employee breakdown within this job
        emp_breakdown = defaultdict(lambda: {'hours': 0.0, 'gross': 0.0, 'costed': 0.0})
        for ce in labor_ces:
            name = ce.employee.display_name if ce.employee else 'Unknown'
            emp_breakdown[name]['hours'] += float(ce.raw_hours or 0)
            emp_breakdown[name]['gross'] += float((ce.raw_hours or 0) * (ce.hourly_rate or 0))
            emp_breakdown[name]['costed'] += float(ce.amount or 0)
        if budgeted or actual:
            recon_data.append({
                'project': proj,
                'client_name': proj.client.name if proj.client else '',
                'budgeted': float(budgeted),
                'actual': float(actual),
                'variance': float(variance),
                'pct': float((actual / budgeted * 100).quantize(Decimal('0.1'))) if budgeted else 0,
                'employees': dict(emp_breakdown),
            })

    # Per-employee cost code breakdown for current period
    emp_cost_data = []
    for rep in all_users:
        rep_entries = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.status == 'approved',
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end,
        ).all()
        by_code = defaultdict(float)
        for e in rep_entries:
            code_label = e.cost_code.code if e.cost_code else 'Untagged'
            by_code[code_label] += float(e.duration_hours or 0)
        if by_code:
            emp_cost_data.append({
                'rep': rep,
                'codes': dict(by_code),
                'total_hours': sum(by_code.values()),
                'total_pay': sum(by_code.values()) * float(rep.hourly_rate or 0),
            })

    daily_totals = build_daily_hours(
        TimeEntry.query.filter(
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end,
        ).all(),
        current_period_start, current_period_end,
    )

    return render_template('admin_dashboard.html',
                         entries=entries,
                         approved_entries=approved_entries,
                         pending_entries=pending_entries,
                         total_hours=total_hours,
                         total_billable=total_billable,
                         pending_hours=pending_hours,
                         entry_count=entry_count,
                         unique_clients=unique_clients,
                         users=all_users,
                         clients=clients,
                         date_from=date_from,
                         date_to=date_to,
                         payroll_data=payroll_data,
                         current_period_start=current_period_start,
                         current_period_end=current_period_end,
                         current_pay_date=current_pay_date,
                         next_period_start=next_period_start,
                         next_period_end=next_period_end,
                         next_pay_date=next_pay_date,
                         filters_applied=filters_applied,
                         filtered_payroll_data=filtered_payroll_data,
                         filtered_date_from=filtered_date_from,
                         filtered_date_to=filtered_date_to,
                         recon_data=recon_data,
                         emp_cost_data=emp_cost_data,
                         daily_totals=daily_totals)


@app.route('/admin/entries/approve', methods=['POST'])
@require_supervisor
def approve_entries():
    entry_ids = request.form.getlist('entry_ids')
    if not entry_ids:
        flash('No entries selected.', 'error')
        return redirect(url_for('admin_dashboard'))
    now = datetime.now(timezone.utc)
    count = 0
    for eid in entry_ids:
        entry = TimeEntry.query.get(int(eid))
        if entry and entry.status == 'pending':
            entry.status = 'approved'
            entry.approved_by_user_id = current_user.id
            entry.approved_at = now
            entry.rejection_reason = None
            _sync_time_entry_cost(entry, current_user.id)
            count += 1
    db.session.commit()
    flash(f'{count} entries approved.', 'success')
    return redirect(request.form.get('return_url') or url_for('admin_dashboard'))


@app.route('/admin/entries/reject', methods=['POST'])
@require_supervisor
def reject_entries():
    entry_ids = request.form.getlist('entry_ids')
    reason = request.form.get('rejection_reason', '').strip()
    if not entry_ids:
        flash('No entries selected.', 'error')
        return redirect(url_for('admin_dashboard'))
    count = 0
    for eid in entry_ids:
        entry = TimeEntry.query.get(int(eid))
        if entry and entry.status in ('pending', 'approved'):
            if entry.status == 'approved':
                _remove_time_entry_cost(entry)
            entry.status = 'rejected'
            entry.rejection_reason = reason or None
            entry.approved_by_user_id = current_user.id
            entry.approved_at = datetime.now(timezone.utc)
            count += 1
    db.session.commit()
    flash(f'{count} entries rejected.', 'success')
    return redirect(request.form.get('return_url') or url_for('admin_dashboard'))


@app.route('/admin/payroll/export')
@require_supervisor
def payroll_export():
    """CSV export of approved time entries mapped to cost codes for QuickBooks."""
    period_start, period_end, _ = get_pay_period_dates()
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    try:
        start = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else period_start
        end = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else period_end
    except (ValueError, TypeError):
        start, end = period_start, period_end

    entries = TimeEntry.query.filter(
        TimeEntry.status == 'approved',
        TimeEntry.date >= start,
        TimeEntry.date <= end,
    ).order_by(TimeEntry.user_id, TimeEntry.date).all()

    si = StringIO()
    writer = csv.writer(si)
    # QuickBooks-friendly headers: Customer:Job maps to QB Customer, Class maps to QB Class
    writer.writerow([
        'Employee', 'Date', 'Hours', 'Hourly Rate', 'Gross Pay',
        'Burden Multiplier', 'Burdened Cost',
        'Cost Code', 'Cost Code Name',
        'Customer:Job', 'Class',
        'Description',
    ])
    for e in entries:
        rate = float(e.user.hourly_rate or 0)
        hours = float(e.duration_hours or 0)
        burden = float(e.user.effective_burden_multiplier())
        gross = hours * rate
        burdened = gross * burden
        cc_code = e.cost_code.code if e.cost_code else ''
        writer.writerow([
            e.user.display_name,
            e.date.strftime('%m/%d/%Y'),
            f'{hours:.2f}',
            f'{rate:.2f}',
            f'{gross:.2f}',
            f'{burden:.4f}',
            f'{burdened:.2f}',
            cc_code,
            e.cost_code.name if e.cost_code else '',
            e.client.name if e.client else 'Overhead',
            cc_code,  # QB Class = cost code
            e.work_description,
        ])

    filename = f"payroll_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    return Response(
        si.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@app.route('/admin/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@require_supervisor
def edit_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    return_url = request.args.get('return_url') or request.form.get('return_url')

    if request.method == 'GET':
        clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
        cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
        return render_template('edit_entry.html', entry=entry, clients=clients, cost_codes=cost_codes, return_url=return_url)

    entry_date = request.form.get('date')
    client_id = request.form.get('client_id')
    cost_code_id = request.form.get('cost_code_id') or None
    work_description = request.form.get('work_description', '').strip()
    duration_hours = request.form.get('duration_hours')

    try:
        entry.date = datetime.strptime(entry_date, '%Y-%m-%d').date()
        entry.client_id = client_id if client_id else None
        entry.cost_code_id = cost_code_id
        entry.work_description = work_description
        entry.duration_hours = round_to_quarter_hour(Decimal(duration_hours))

        db.session.commit()
        flash('Entry updated successfully.', 'success')

        if return_url:
            return redirect(return_url)
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'Error updating entry: {str(e)}', 'error')
        return redirect(url_for('edit_entry', entry_id=entry_id, return_url=return_url))


@app.route('/admin/entry/<int:entry_id>/approve', methods=['POST'])
@require_supervisor
def approve_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    return_url = request.form.get('return_url')

    if not entry.client_id:
        flash('Cannot approve: entry must be assigned to a client.', 'error')
        return redirect(url_for('edit_entry', entry_id=entry_id, return_url=return_url))

    if not entry.cost_code_id:
        flash('Cannot approve: a cost code is required.', 'error')
        return redirect(url_for('edit_entry', entry_id=entry_id, return_url=return_url))

    _sync_time_entry_cost(entry, current_user.id)

    entry.status = 'approved'
    entry.rejection_reason = None
    entry.approved_by_user_id = current_user.id
    entry.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    hours = entry.duration_hours or 0
    rate = entry.user.hourly_rate or 0
    burden = entry.user.effective_burden_multiplier()
    costed = (Decimal(str(hours)) * Decimal(str(rate)) * burden).quantize(Decimal('0.01'))
    flash(f'Entry approved. Labor cost ${costed} posted.', 'success')
    if return_url:
        return redirect(return_url)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/entry/<int:entry_id>/reject', methods=['POST'])
@require_supervisor
def reject_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    return_url = request.form.get('return_url')
    reason = request.form.get('rejection_reason', '').strip()

    entry.status = 'rejected'
    entry.rejection_reason = reason or None
    entry.approved_by_user_id = None
    entry.approved_at = None

    _remove_time_entry_cost(entry)

    db.session.commit()
    flash('Entry rejected.', 'success')
    if return_url:
        return redirect(return_url)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/entry/<int:entry_id>/reset-pending', methods=['POST'])
@require_supervisor
def reset_entry_pending(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    return_url = request.form.get('return_url')

    entry.status = 'pending'
    entry.rejection_reason = None
    entry.approved_by_user_id = None
    entry.approved_at = None

    _remove_time_entry_cost(entry)

    db.session.commit()
    flash('Entry reset to pending.', 'success')
    if return_url:
        return redirect(return_url)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/rep/<user_id>/entries')
@require_supervisor
def rep_time_entries(user_id):
    rep = User.query.get_or_404(user_id)

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    client_id = request.args.get('client_id')
    timeframe = request.args.get('timeframe', 'current_period')

    if timeframe == 'current_period':
        summary_start, summary_end, summary_pay_date = get_pay_period_dates()
        summary_label = f"Current Pay Period: {format_date_for_display(summary_start)} - {format_date_for_display(summary_end)}"
    elif timeframe == 'previous_period':
        summary_start, summary_end, summary_pay_date = get_previous_pay_period_dates()
        summary_label = f"Previous Pay Period: {format_date_for_display(summary_start)} - {format_date_for_display(summary_end)}"
    elif timeframe == 'month_to_date':
        summary_start, summary_end, summary_label = get_month_to_date_dates()
        summary_pay_date = None
    else:
        summary_start, summary_end, summary_label = get_last_30_days_dates()
        summary_pay_date = None

    query = TimeEntry.query.filter_by(user_id=user_id)

    if date_from:
        try:
            query = query.filter(TimeEntry.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except:
            pass
    else:
        query = query.filter(TimeEntry.date >= summary_start)
        date_from = summary_start.strftime('%Y-%m-%d')

    if date_to:
        try:
            query = query.filter(TimeEntry.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except:
            pass
    else:
        query = query.filter(TimeEntry.date <= summary_end)
        date_to = summary_end.strftime('%Y-%m-%d')

    if client_id:
        query = query.filter_by(client_id=client_id)

    entries = query.order_by(TimeEntry.date.desc()).all()

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()

    summary_entries = TimeEntry.query.filter(
        TimeEntry.user_id == user_id,
        TimeEntry.status == 'approved',
        TimeEntry.date >= summary_start,
        TimeEntry.date <= summary_end
    ).all()

    summary_hours = sum((e.duration_hours or 0) for e in summary_entries)
    summary_billable = sum((e.duration_hours or 0) for e in summary_entries if e.client_id)
    summary_entry_count = len(summary_entries)
    summary_unique_clients = len(set(e.client_id for e in summary_entries if e.client_id))
    summary_pay = float(summary_hours) * float(rep.hourly_rate or 0)
    daily_hours = build_daily_hours(summary_entries, summary_start, summary_end)

    return render_template('rep_time_entries.html',
                         rep=rep,
                         entries=entries,
                         clients=clients,
                         date_from=date_from,
                         date_to=date_to,
                         client_id=client_id,
                         timeframe=timeframe,
                         summary_label=summary_label,
                         summary_start=summary_start,
                         summary_end=summary_end,
                         summary_pay_date=summary_pay_date,
                         summary_hours=summary_hours,
                         summary_billable=summary_billable,
                         summary_entry_count=summary_entry_count,
                         summary_unique_clients=summary_unique_clients,
                         summary_pay=summary_pay,
                         daily_hours=daily_hours)


@app.route('/admin/users')
@require_supervisor
def manage_users():
    from models import AuthorizedUser
    users = User.query.order_by(User.created_at.desc()).all()
    authorized_users = AuthorizedUser.query.order_by(AuthorizedUser.created_at.desc()).all()
    
    # Create a set of emails for users who have logged in
    logged_in_emails = {user.email.lower() for user in users if user.email}
    
    # Add status to each authorized user
    for auth_user in authorized_users:
        auth_user.has_logged_in = auth_user.email.lower() in logged_in_emails
    
    return render_template('manage_users.html', users=users, authorized_users=authorized_users)


@app.route('/admin/users/<user_id>/toggle-role', methods=['POST'])
@require_supervisor
def toggle_user_role(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('manage_users'))
    
    user.role = 'supervisor' if user.role == 'rep' else 'rep'
    db.session.commit()
    
    flash(f'{user.display_name} is now a {user.role}.', 'success')
    return redirect(url_for('manage_users'))


@app.route('/admin/users/add-authorized', methods=['POST'])
@require_supervisor
def add_authorized_user():
    from models import AuthorizedUser
    
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'rep').strip()

    if not email:
        flash('Email address is required.', 'error')
        return redirect(url_for('manage_users'))

    if role not in ['rep', 'supervisor']:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('manage_users'))

    existing = AuthorizedUser.query.filter_by(email=email).first()
    if existing:
        flash(f'{email} is already authorized.', 'error')
        return redirect(url_for('manage_users'))

    hourly_rate = request.form.get('hourly_rate', '0').strip()
    try:
        hourly_rate_val = Decimal(hourly_rate) if hourly_rate else Decimal('0')
    except:
        hourly_rate_val = Decimal('0')

    auth_user = AuthorizedUser(
        email=email,
        role=role,
        hourly_rate=hourly_rate_val,
        added_by_user_id=current_user.id
    )
    db.session.add(auth_user)
    db.session.commit()

    flash(f'Successfully authorized {email} as {role.title()}.', 'success')
    return redirect(url_for('manage_users'))


@app.route('/admin/users/remove-authorized/<int:auth_id>', methods=['POST'])
@require_supervisor
def remove_authorized_user(auth_id):
    from models import AuthorizedUser
    
    auth_user = AuthorizedUser.query.get_or_404(auth_id)
    email = auth_user.email
    
    db.session.delete(auth_user)
    db.session.commit()
    
    flash(f'Removed authorization for {email}. They will no longer be able to sign in.', 'success')
    return redirect(url_for('manage_users'))


@app.route('/profile/edit', methods=['GET', 'POST'])
@require_login
def edit_profile():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()

        if not first_name or not last_name or not email or not phone or not address:
            flash('All fields are required.', 'error')
            return redirect(url_for('edit_profile'))

        if email != current_user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('This email is already in use by another user.', 'error')
                return redirect(url_for('edit_profile'))

        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.email = email
        current_user.phone = phone
        current_user.address = address

        current_user.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('edit_profile'))
    
    return render_template('edit_profile.html', user=current_user)


@app.route('/profile/upload-picture', methods=['POST'])
@require_login
def upload_profile_picture():
    from flask import jsonify
    import os
    from werkzeug.utils import secure_filename
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400
    
    file = request.files['image']
    
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed. Only images (JPG, PNG, GIF, WebP) are accepted'}), 400
    
    MAX_FILE_SIZE = 5 * 1024 * 1024
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        return jsonify({'success': False, 'error': f'File size ({size_mb:.2f}MB) exceeds maximum of 5MB'}), 400
    
    profile_images_folder = os.path.join(os.getcwd(), 'profile_images')
    os.makedirs(profile_images_folder, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    unique_filename = f"profile_{current_user.id}_{timestamp}.{ext}"
    file_path = os.path.join(profile_images_folder, unique_filename)
    
    try:
        old_profile_pic = current_user.profile_image_url
        if old_profile_pic and old_profile_pic.startswith('/profile-picture/'):
            old_filename = old_profile_pic.split('/')[-1]
            old_file_path = os.path.join(profile_images_folder, old_filename)
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except:
                    pass
        
        file.save(file_path)
        
        current_user.profile_image_url = f'/profile-picture/{unique_filename}'
        current_user.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'image_url': current_user.profile_image_url
        })
        
    except Exception as e:
        db.session.rollback()
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        return jsonify({'success': False, 'error': 'Failed to save profile picture. Please try again'}), 500


@app.route('/profile-picture/<filename>')
@require_login
def view_profile_picture(filename):
    from flask import send_from_directory
    import os
    
    profile_images_folder = os.path.join(os.getcwd(), 'profile_images')
    return send_from_directory(profile_images_folder, filename)


@app.route('/admin/users/<user_id>/edit', methods=['GET', 'POST'])
@require_supervisor
def edit_user_profile(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        role = request.form.get('role', '').strip()

        if not first_name or not last_name or not email or not phone or not address:
            flash('All fields are required.', 'error')
            return redirect(url_for('edit_user_profile', user_id=user_id))

        if email != user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('This email is already in use by another user.', 'error')
                return redirect(url_for('edit_user_profile', user_id=user_id))

        if role not in ['rep', 'supervisor']:
            flash('Invalid role selected.', 'error')
            return redirect(url_for('edit_user_profile', user_id=user_id))

        hourly_rate = request.form.get('hourly_rate', '0').strip()
        try:
            hourly_rate_val = Decimal(hourly_rate) if hourly_rate else Decimal('0')
        except:
            hourly_rate_val = Decimal('0')

        burden_str = request.form.get('burden_multiplier', '').strip()
        burden_val = None
        if burden_str:
            try:
                burden_val = Decimal(burden_str)
            except:
                pass

        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.phone = phone
        user.address = address
        user.role = role
        user.hourly_rate = hourly_rate_val
        user.burden_multiplier = burden_val

        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        flash(f'Profile for {user.display_name} updated successfully!', 'success')
        return redirect(url_for('edit_user_profile', user_id=user_id))

    default_burden = AppSetting.get('labor_burden_multiplier', '1.25')
    all_users = User.query.order_by(User.first_name, User.last_name).all()
    clients_assigned_count = Client.query.filter_by(assigned_to_user_id=user.id, is_active=True).count()
    
    return render_template('edit_user_profile.html', user=user, editing_user=user,
                          all_users=all_users, clients_assigned_count=clients_assigned_count,
                          default_burden=default_burden)


@app.route('/admin/users/<user_id>/remove', methods=['POST'])
@require_supervisor
def remove_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot remove yourself.', 'error')
        return redirect(url_for('manage_users'))
    
    user_name = user.display_name
    reassign_to_id = request.form.get('reassign_to', '').strip()
    
    if reassign_to_id:
        reassign_to_user = User.query.get(reassign_to_id)
        if not reassign_to_user:
            flash('Invalid user selected for client reassignment.', 'error')
            return redirect(url_for('edit_user_profile', user_id=user_id))
        
        clients_count = Client.query.filter_by(assigned_to_user_id=user.id).count()
        Client.query.filter_by(assigned_to_user_id=user.id).update({'assigned_to_user_id': reassign_to_id})
        
        flash_message = f'Successfully removed user {user_name}. {clients_count} client(s) have been reassigned to {reassign_to_user.display_name}.'
    else:
        Client.query.filter_by(assigned_to_user_id=user.id).update({'assigned_to_user_id': None})
        flash_message = f'Successfully removed user {user_name}. Clients have been unassigned.'
    
    Client.query.filter_by(created_by_user_id=user.id).update({'created_by_user_id': None})
    
    from models import AuthorizedUser
    AuthorizedUser.query.filter_by(email=user.email).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    flash(flash_message, 'success')
    return redirect(url_for('manage_users'))


@app.template_filter('format_date')
def format_date_filter(value):
    return format_date_for_display(value)


@app.template_filter('format_datetime')
def format_datetime_filter(value):
    return format_datetime_for_display(value)


@app.template_filter('format_datetime_input')
def format_datetime_input_filter(value):
    from utils import format_datetime_for_input
    return format_datetime_for_input(value)


@app.template_filter('format_hours')
def format_hours_filter(value):
    return format_hours(value)


# --- Cost Code & Burden Settings (Supervisors Only) ---

@app.route('/settings/cost-codes')
@require_supervisor
def cost_codes_settings():
    codes = CostCode.query.order_by(CostCode.sort_order, CostCode.code).all()
    default_burden = AppSetting.get('labor_burden_multiplier', '1.25')
    return render_template('cost_codes_settings.html', codes=codes, cost_types=COST_TYPES,
                         default_burden=default_burden)


@app.route('/settings/cost-codes/add', methods=['POST'])
@require_supervisor
def add_cost_code():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    default_cost_type = request.form.get('default_cost_type', 'Other')
    sort_order = request.form.get('sort_order', '0')

    if not code or not name:
        flash('Code and name are required.', 'error')
        return redirect(url_for('cost_codes_settings'))

    existing = CostCode.query.filter_by(code=code).first()
    if existing:
        flash(f'Cost code "{code}" already exists.', 'error')
        return redirect(url_for('cost_codes_settings'))

    try:
        sort_val = int(sort_order)
    except:
        sort_val = 0

    cc = CostCode(code=code, name=name, default_cost_type=default_cost_type, sort_order=sort_val)
    db.session.add(cc)
    db.session.commit()
    flash(f'Cost code {code} - {name} added.', 'success')
    return redirect(url_for('cost_codes_settings'))


@app.route('/settings/cost-codes/<int:code_id>/toggle', methods=['POST'])
@require_supervisor
def toggle_cost_code(code_id):
    cc = CostCode.query.get_or_404(code_id)
    cc.is_active = not cc.is_active
    db.session.commit()
    status = 'activated' if cc.is_active else 'deactivated'
    flash(f'Cost code {cc.code} {status}.', 'success')
    return redirect(url_for('cost_codes_settings'))


@app.route('/settings/burden-multiplier', methods=['POST'])
@require_supervisor
def update_burden_multiplier():
    value = request.form.get('burden_multiplier', '').strip()
    try:
        val = Decimal(value)
        if val <= 0:
            raise ValueError
        AppSetting.set('labor_burden_multiplier', str(val))
        flash(f'Default burden multiplier updated to {val}.', 'success')
    except:
        flash('Invalid burden multiplier. Must be a positive number.', 'error')
    return redirect(url_for('cost_codes_settings'))


# --- Lead Source Management (Supervisors Only) ---

@app.route('/settings/lead-sources')
@require_supervisor
def lead_sources_settings():
    sources = LeadSource.query.order_by(LeadSource.is_active.desc(), LeadSource.name).all()
    return render_template('lead_sources_settings.html', sources=sources, channel_types=LeadSource.CHANNEL_TYPES)


@app.route('/settings/lead-sources/add', methods=['POST'])
@require_supervisor
def add_lead_source():
    name = request.form.get('name', '').strip()
    channel_type = request.form.get('channel_type', '').strip()
    if not name or channel_type not in LeadSource.CHANNEL_TYPES:
        flash('Name and valid channel type are required.', 'error')
        return redirect(url_for('lead_sources_settings'))
    source = LeadSource(name=name, channel_type=channel_type)
    db.session.add(source)
    db.session.commit()
    flash(f'Lead source "{name}" added.', 'success')
    return redirect(url_for('lead_sources_settings'))


@app.route('/settings/lead-sources/<int:source_id>/update', methods=['POST'])
@require_supervisor
def update_lead_source(source_id):
    source = LeadSource.query.get_or_404(source_id)
    name = request.form.get('name', '').strip()
    channel_type = request.form.get('channel_type', '').strip()
    is_active = request.form.get('is_active') == '1'
    if name:
        source.name = name
    if channel_type in LeadSource.CHANNEL_TYPES:
        source.channel_type = channel_type
    source.is_active = is_active
    db.session.commit()
    flash(f'Lead source "{source.name}" updated.', 'success')
    return redirect(url_for('lead_sources_settings'))


@app.route('/settings/lead-sources/seed', methods=['POST'])
@require_supervisor
def seed_lead_sources():
    """Seed the default lead sources if none exist."""
    if LeadSource.query.count() > 0:
        flash('Lead sources already exist.', 'error')
        return redirect(url_for('lead_sources_settings'))
    defaults = [
        ('Google Ads', 'paid_ads'),
        ('Meta Ads', 'paid_ads'),
        ('Instagram Organic', 'organic_social'),
        ('Facebook Organic', 'organic_social'),
        ('Website / SEO', 'website'),
        ('Phone Call', 'phone'),
        ('Referral — Client', 'referral'),
        ('Referral — Partner', 'referral'),
        ('Repeat Client', 'other'),
        ('Other', 'other'),
    ]
    for name, channel in defaults:
        db.session.add(LeadSource(name=name, channel_type=channel))
    db.session.commit()
    flash('Default lead sources seeded.', 'success')
    return redirect(url_for('lead_sources_settings'))


# --- Lead Source Backfill (Supervisors Only) ---

@app.route('/settings/lead-sources/backfill')
@require_supervisor
def lead_source_backfill():
    clients_missing = Client.query.filter(Client.lead_source_id.is_(None), Client.is_active == True).order_by(Client.name).all()
    lead_sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()
    return render_template('lead_source_backfill.html', clients=clients_missing, lead_sources=lead_sources)


@app.route('/settings/lead-sources/backfill/save', methods=['POST'])
@require_supervisor
def lead_source_backfill_save():
    data = request.form
    updated = 0
    for key, value in data.items():
        if key.startswith('source_') and value:
            client_id = int(key.replace('source_', ''))
            client = Client.query.get(client_id)
            if client:
                client.lead_source_id = int(value)
                detail = data.get(f'detail_{client_id}', '').strip()
                client.source_detail = detail if detail else None
                updated += 1
    db.session.commit()
    flash(f'{updated} client(s) updated with lead source.', 'success')
    return redirect(url_for('lead_source_backfill'))


@app.route('/api/missing-lead-source-count')
@require_login
def missing_lead_source_count():
    count = Client.query.filter(Client.lead_source_id.is_(None), Client.is_active == True).count()
    return jsonify({'count': count})


# --- Channel Spend (Supervisors Only) ---

@app.route('/reports/channel-spend')
@require_supervisor
def channel_spend():
    month_str = request.args.get('month')
    if month_str:
        try:
            selected_month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
        except ValueError:
            selected_month = date.today().replace(day=1)
    else:
        selected_month = date.today().replace(day=1)

    entries = ChannelSpend.query.filter_by(period_month=selected_month)\
        .options(joinedload(ChannelSpend.lead_source))\
        .order_by(ChannelSpend.created_at.desc()).all()

    source_totals = defaultdict(Decimal)
    for e in entries:
        source_totals[e.lead_source.name] += e.amount
    grand_total = sum(source_totals.values())

    lead_sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()

    return render_template('channel_spend.html',
                           entries=entries,
                           source_totals=dict(sorted(source_totals.items())),
                           grand_total=grand_total,
                           lead_sources=lead_sources,
                           selected_month=selected_month)


@app.route('/reports/channel-spend/add', methods=['POST'])
@require_supervisor
def add_channel_spend():
    lead_source_id = request.form.get('lead_source_id', '').strip()
    amount_str = request.form.get('amount', '').strip().replace(',', '').replace('$', '')
    month_str = request.form.get('period_month', '').strip()
    note = request.form.get('note', '').strip()

    if not lead_source_id or not amount_str or not month_str:
        flash('Source and amount are required.', 'error')
        return redirect(url_for('channel_spend', month=month_str))

    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash('Enter a valid positive amount.', 'error')
        return redirect(url_for('channel_spend', month=month_str))

    try:
        period_month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
    except ValueError:
        flash('Invalid month.', 'error')
        return redirect(url_for('channel_spend'))

    entry = ChannelSpend(
        lead_source_id=int(lead_source_id),
        amount=amount,
        period_month=period_month,
        note=note if note else None,
        created_by=current_user.id
    )
    db.session.add(entry)
    db.session.commit()
    flash('Spend entry added.', 'success')
    return redirect(url_for('channel_spend', month=month_str))


@app.route('/reports/channel-spend/<int:spend_id>/edit', methods=['POST'])
@require_supervisor
def edit_channel_spend(spend_id):
    entry = ChannelSpend.query.get_or_404(spend_id)
    lead_source_id = request.form.get('lead_source_id', '').strip()
    amount_str = request.form.get('amount', '').strip().replace(',', '').replace('$', '')
    note = request.form.get('note', '').strip()
    month_str = request.form.get('period_month', '').strip()

    if lead_source_id:
        entry.lead_source_id = int(lead_source_id)
    if amount_str:
        try:
            entry.amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            flash('Invalid amount.', 'error')
            return redirect(url_for('channel_spend', month=month_str))
    entry.note = note if note else None
    db.session.commit()
    flash('Spend entry updated.', 'success')
    return redirect(url_for('channel_spend', month=month_str))


@app.route('/reports/channel-spend/<int:spend_id>/delete', methods=['POST'])
@require_supervisor
def delete_channel_spend(spend_id):
    entry = ChannelSpend.query.get_or_404(spend_id)
    month_str = entry.period_month.strftime('%Y-%m')
    db.session.delete(entry)
    db.session.commit()
    flash('Spend entry deleted.', 'success')
    return redirect(url_for('channel_spend', month=month_str))


# --- Integrations Settings (Supervisors Only) ---

import ghl_helper
import meta_ads_helper
import qbo_helper

# Session keys for storing sync results and lead source mappings
_GHL_LEAD_SOURCE_KEY = 'ghl_lead_source_id'
_META_LEAD_SOURCE_KEY = 'meta_lead_source_id'


@app.route('/settings/integrations')
@require_supervisor
def integrations_settings():
    import os

    # GHL status
    ghl_connected = ghl_helper.is_configured()
    ghl_location_name = ''
    if ghl_connected:
        ok, msg = ghl_helper.test_connection()
        ghl_connected = ok
        ghl_location_name = msg if ok else ''

    ghl_status = {
        'connected': ghl_connected,
        'location_name': ghl_location_name,
        'has_key': bool(os.environ.get('GHL_API_KEY')),
        'has_location': bool(os.environ.get('GHL_LOCATION_ID')),
        'last_sync': AppSetting.get('ghl_last_sync'),
        'last_sync_result': AppSetting.get('ghl_sync_result'),
        'last_sync_success': AppSetting.get('ghl_sync_success') == 'true',
        'health': AppSetting.get('ghl_health_status'),
        'health_error': AppSetting.get('ghl_health_error'),
        'health_checked_at': AppSetting.get('ghl_health_checked_at'),
        'opp_sync_result': AppSetting.get('ghl_opp_sync_result'),
    }

    # Meta status
    meta_connected = meta_ads_helper.is_configured()
    meta_account_name = ''
    if meta_connected:
        ok, msg = meta_ads_helper.test_connection()
        meta_connected = ok
        meta_account_name = msg if ok else ''

    meta_status = {
        'connected': meta_connected,
        'account_name': meta_account_name,
        'has_token': bool(os.environ.get('META_ADS_ACCESS_TOKEN')),
        'has_account': bool(os.environ.get('META_ADS_ACCOUNT_ID')),
        'last_sync': AppSetting.get('meta_last_sync'),
        'last_sync_result': AppSetting.get('meta_sync_result'),
        'last_sync_success': AppSetting.get('meta_sync_success') == 'true',
    }

    # Campaign breakdown for current month
    meta_campaigns = []
    if meta_connected:
        from utils import PACIFIC_TZ
        now_pacific = datetime.now(PACIFIC_TZ)
        meta_campaigns = meta_ads_helper.fetch_campaign_breakdown(now_pacific.year, now_pacific.month)

    lead_sources = LeadSource.query.filter_by(is_active=True).order_by(LeadSource.name).all()

    # QBO status
    qbo_token = QBOToken.query.first()
    qbo_status = {
        'connected': qbo_token is not None,
        'company_name': qbo_token.company_name if qbo_token else '',
        'configured': qbo_helper.is_configured(),
        'last_sync': AppSetting.get('qbo_last_sync'),
        'last_sync_result': AppSetting.get('qbo_sync_result'),
        'last_sync_success': AppSetting.get('qbo_sync_success') == 'true',
    }

    return render_template('integrations_settings.html',
                         ghl_status=ghl_status,
                         meta_status=meta_status,
                         meta_campaigns=meta_campaigns,
                         lead_sources=lead_sources,
                         ghl_lead_source_id=AppSetting.get(_GHL_LEAD_SOURCE_KEY),
                         meta_lead_source_id=AppSetting.get(_META_LEAD_SOURCE_KEY),
                         qbo_status=qbo_status)


@app.route('/settings/integrations/ghl/test', methods=['POST'])
@require_supervisor
def ghl_test_connection():
    ok, msg = ghl_helper.test_connection()
    if ok:
        flash(f'GoHighLevel connected: {msg}', 'success')
    else:
        flash(f'GoHighLevel connection failed: {msg}', 'error')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/ghl/lead-source', methods=['POST'])
@require_supervisor
def save_ghl_lead_source():
    source_id = request.form.get('lead_source_id', '').strip()
    if source_id:
        AppSetting.set(_GHL_LEAD_SOURCE_KEY, source_id)
        flash('GHL lead source mapping saved.', 'success')
    else:
        AppSetting.set(_GHL_LEAD_SOURCE_KEY, '')
        flash('GHL lead source mapping cleared.', 'success')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/ghl/sync', methods=['POST'])
@require_supervisor
def ghl_sync_contacts():
    """Import GHL contacts as CRM leads."""
    lead_source_id = AppSetting.get(_GHL_LEAD_SOURCE_KEY)
    if not lead_source_id:
        flash('Please set a lead source mapping for GHL first.', 'error')
        return redirect(url_for('integrations_settings'))
    lead_source_id = int(lead_source_id)

    if not ghl_helper.is_configured():
        flash('GoHighLevel is not configured.', 'error')
        return redirect(url_for('integrations_settings'))

    try:
        contacts = ghl_helper.fetch_all_contacts()
    except Exception as e:
        result = f'Sync failed: {e}'
        AppSetting.set('ghl_last_sync', format_datetime_for_display(datetime.now(timezone.utc)))
        AppSetting.set('ghl_sync_result', result)
        AppSetting.set('ghl_sync_success', 'false')
        flash(result, 'error')
        return redirect(url_for('integrations_settings'))

    if not contacts:
        result = 'GHL returned 0 contacts. Check that your sub-account has contacts and that your API key has contacts.readonly scope.'
        AppSetting.set('ghl_last_sync', format_datetime_for_display(datetime.now(timezone.utc)))
        AppSetting.set('ghl_sync_result', result)
        AppSetting.set('ghl_sync_success', 'false')
        flash(result, 'warning')
        return redirect(url_for('integrations_settings'))

    created = 0
    skipped = 0

    for contact in contacts:
        ghl_id = contact.get('id')
        if not ghl_id:
            continue

        # Skip if already imported
        existing = Client.query.filter_by(ghl_contact_id=ghl_id).first()
        if existing:
            skipped += 1
            continue

        data = ghl_helper.map_contact_to_client_data(contact)
        client = Client(
            name=data['name'],
            address=data['address'],
            contact_name=data['contact_name'],
            phone=data['phone'],
            email=data['email'],
            status=data['status'],
            notes=data['notes'],
            ghl_contact_id=data['ghl_contact_id'],
            lead_source_id=lead_source_id,
            source_detail=data['source_detail'],
            created_by_user_id=current_user.id,
            assigned_to_user_id=current_user.id,
        )
        db.session.add(client)

        # Log initial status change
        status_change = ClientStatusChange(
            client_id=0,  # placeholder, set after flush
            from_status=None,
            to_status=data['status'],
            changed_by_user_id=current_user.id,
        )
        db.session.flush()  # get client.id
        status_change.client_id = client.id
        db.session.add(status_change)

        created += 1

    db.session.commit()

    result = f'Imported {created} new contact{"s" if created != 1 else ""}'
    if skipped:
        result += f', skipped {skipped} existing'

    AppSetting.set('ghl_last_sync', format_datetime_for_display(datetime.now(timezone.utc)))
    AppSetting.set('ghl_sync_result', result)
    AppSetting.set('ghl_sync_success', 'true')
    flash(result, 'success')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/ghl/sync-opportunities', methods=['POST'])
@require_supervisor
def ghl_sync_opportunities():
    """Sync won GHL opportunities → update matching Client records."""
    if not ghl_helper.is_configured():
        flash('GoHighLevel is not configured.', 'error')
        return redirect(url_for('integrations_settings'))

    try:
        opps = ghl_helper.fetch_all_opportunities()
    except Exception as e:
        flash(f'Failed to fetch opportunities: {e}', 'error')
        return redirect(url_for('integrations_settings'))

    updated = 0
    skipped = 0

    for opp in opps:
        update_data = ghl_helper.map_opportunity_to_client_update(opp)
        if not update_data:
            continue  # not won

        # Find matching client by GHL contact ID
        contact_id = opp.get('contactId') or (opp.get('contact', {}).get('id'))
        if not contact_id:
            skipped += 1
            continue

        client = Client.query.filter_by(ghl_contact_id=contact_id).first()
        if not client:
            skipped += 1
            continue

        # Update client fields
        changed = False
        if client.status not in ('Active', 'Completed'):
            old_status = client.status
            client.status = update_data['status']
            sc = ClientStatusChange(
                client_id=client.id,
                from_status=old_status,
                to_status=update_data['status'],
                changed_by_user_id=current_user.id,
            )
            db.session.add(sc)
            changed = True

        if 'opportunity_value' in update_data and not client.opportunity_value:
            client.opportunity_value = update_data['opportunity_value']
            changed = True

        if changed:
            updated += 1
        else:
            skipped += 1

    db.session.commit()

    result = f'Opportunities: {updated} client{"s" if updated != 1 else ""} updated'
    if skipped:
        result += f', {skipped} skipped'
    AppSetting.set('ghl_opp_sync_result', result)
    flash(result, 'success')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/ghl/health', methods=['POST'])
@require_supervisor
def ghl_health_check():
    """Run a GHL integration health check."""
    ok, details = ghl_helper.health_check()

    checks = []
    checks.append(('API Key', details['has_api_key']))
    checks.append(('Location ID', details['has_location_id']))
    checks.append(('API Reachable', details['api_reachable']))
    checks.append(('Location Valid', details['location_valid']))
    checks.append(('Contacts Readable', details['contacts_readable']))

    passed = sum(1 for _, v in checks if v)
    total = len(checks)

    if ok:
        result = f'Health check passed ({passed}/{total} checks OK)'
        AppSetting.set('ghl_health_status', 'healthy')
        flash(result, 'success')
    else:
        result = f'Health check failed ({passed}/{total}): {details.get("error", "Unknown error")}'
        AppSetting.set('ghl_health_status', 'unhealthy')
        AppSetting.set('ghl_health_error', details.get('error', ''))
        flash(result, 'error')

    AppSetting.set('ghl_health_checked_at', format_datetime_for_display(datetime.now(timezone.utc)))
    AppSetting.set('ghl_health_detail', str(details))
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/meta/test', methods=['POST'])
@require_supervisor
def meta_test_connection():
    ok, msg = meta_ads_helper.test_connection()
    if ok:
        flash(f'Meta Ads connected: {msg}', 'success')
    else:
        flash(f'Meta Ads connection failed: {msg}', 'error')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/meta/lead-source', methods=['POST'])
@require_supervisor
def save_meta_lead_source():
    source_id = request.form.get('lead_source_id', '').strip()
    if source_id:
        AppSetting.set(_META_LEAD_SOURCE_KEY, source_id)
        flash('Meta Ads lead source mapping saved.', 'success')
    else:
        AppSetting.set(_META_LEAD_SOURCE_KEY, '')
        flash('Meta Ads lead source mapping cleared.', 'success')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/integrations/meta/sync', methods=['POST'])
@require_supervisor
def meta_sync_spend():
    """Pull Meta Ads spend for current month into ChannelSpend."""
    lead_source_id = AppSetting.get(_META_LEAD_SOURCE_KEY)
    if not lead_source_id:
        flash('Please set a lead source mapping for Meta Ads first.', 'error')
        return redirect(url_for('integrations_settings'))
    lead_source_id = int(lead_source_id)

    if not meta_ads_helper.is_configured():
        flash('Meta Ads is not configured.', 'error')
        return redirect(url_for('integrations_settings'))

    from utils import PACIFIC_TZ
    now_pacific = datetime.now(PACIFIC_TZ)
    year, month = now_pacific.year, now_pacific.month
    period_month = date(year, month, 1)

    try:
        spend, leads, impressions, clicks = meta_ads_helper.fetch_monthly_spend(year, month)
    except Exception as e:
        result = f'Sync failed: {e}'
        AppSetting.set('meta_last_sync', format_datetime_for_display(datetime.now(timezone.utc)))
        AppSetting.set('meta_sync_result', result)
        AppSetting.set('meta_sync_success', 'false')
        flash(result, 'error')
        return redirect(url_for('integrations_settings'))

    # Upsert: find existing entry or create
    existing = ChannelSpend.query.filter_by(
        lead_source_id=lead_source_id,
        period_month=period_month,
    ).first()

    if existing:
        existing.amount = spend
        existing.note = f'Meta Ads auto-sync: {leads} leads, {impressions:,} impressions, {clicks:,} clicks'
        action = 'Updated'
    else:
        entry = ChannelSpend(
            lead_source_id=lead_source_id,
            amount=spend,
            period_month=period_month,
            note=f'Meta Ads auto-sync: {leads} leads, {impressions:,} impressions, {clicks:,} clicks',
            created_by=current_user.id,
        )
        db.session.add(entry)
        action = 'Created'

    db.session.commit()

    result = f'{action} spend entry: ${spend:,.2f} for {now_pacific.strftime("%B %Y")} ({leads} leads, {clicks:,} clicks)'
    AppSetting.set('meta_last_sync', format_datetime_for_display(datetime.now(timezone.utc)))
    AppSetting.set('meta_sync_result', result)
    AppSetting.set('meta_sync_success', 'true')
    flash(result, 'success')
    return redirect(url_for('integrations_settings'))


# --- ROI Report (Supervisors Only) ---

def _parse_roi_dates(req):
    """Parse date range from request args. Returns (start, end, prev_start, prev_end, preset)."""
    preset = req.args.get('preset', '')
    today = date.today()

    if preset == 'this_month':
        start = today.replace(day=1)
        end = today
    elif preset == 'last_3_months':
        m = today.replace(day=1)
        end = m - timedelta(days=1)
        m2 = end.replace(day=1)
        m3 = (m2 - timedelta(days=1)).replace(day=1)
        start = (m3 - timedelta(days=1)).replace(day=1)
    elif preset == 'ytd':
        start = today.replace(month=1, day=1)
        end = today
    elif preset == 'last_month' or (not req.args.get('start') and not preset):
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        preset = 'last_month'
    else:
        try:
            start = datetime.strptime(req.args['start'], '%Y-%m-%d').date()
            end = datetime.strptime(req.args['end'], '%Y-%m-%d').date()
        except (KeyError, ValueError):
            first_this = today.replace(day=1)
            end = first_this - timedelta(days=1)
            start = end.replace(day=1)
            preset = 'last_month'

    period_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    return start, end, prev_start, prev_end, preset


def _build_roi_rows(clients_in_period, spend_by_source, all_source_ids):
    """Build per-source ROI rows from clients created in the period."""
    empty = lambda: {
        'funnel_lead': 0, 'funnel_prospect': 0, 'funnel_active': 0,
        'funnel_completed': 0, 'funnel_on_hold': 0, 'funnel_lost': 0,
        'total_leads': 0,
        'revenue_closed': Decimal(0), 'revenue_projected': Decimal(0),
        '_days_to_close': [],  # list of day counts for completed clients
    }
    rows = {sid: empty() for sid in all_source_ids}
    rows[None] = empty()

    status_key = {
        'Lead': 'funnel_lead', 'Prospect': 'funnel_prospect',
        'Active': 'funnel_active', 'Completed': 'funnel_completed',
        'On Hold': 'funnel_on_hold', 'Lost': 'funnel_lost',
    }
    for c in clients_in_period:
        sid = c.lead_source_id if c.lead_source_id in rows else None
        r = rows[sid]
        r['total_leads'] += 1
        r[status_key.get(c.status, 'funnel_lead')] += 1
        if c.status == 'Completed' and c.final_contract_value:
            r['revenue_closed'] += c.final_contract_value
        if c.status == 'Completed' and c.created_at:
            close_change = ClientStatusChange.query.filter_by(
                client_id=c.id, to_status='Completed'
            ).order_by(ClientStatusChange.changed_at.desc()).first()
            close_date = close_change.changed_at if close_change else c.updated_at
            if close_date:
                r['_days_to_close'].append((close_date - c.created_at).days)
        if c.status == 'Active' and c.opportunity_value:
            r['revenue_projected'] += c.opportunity_value

    for sid in rows:
        r = rows[sid]
        r['spend'] = spend_by_source.get(sid, Decimal(0))
        tl = r['total_leads']
        r['cpl'] = r['spend'] / tl if tl and r['spend'] else None
        r['won'] = r['funnel_active'] + r['funnel_completed']
        r['close_rate'] = (r['won'] / tl * 100) if tl else None
        r['total_revenue'] = r['revenue_closed'] + r['revenue_projected']
        r['roi'] = float(r['total_revenue'] / r['spend']) if r['spend'] else None
        dtc = r.pop('_days_to_close')
        r['avg_days_to_close'] = round(sum(dtc) / len(dtc), 1) if len(dtc) >= 5 else None
        r['days_to_close_count'] = len(dtc)
    return rows


@app.route('/reports/roi')
@require_supervisor
def roi_report():
    start, end, prev_start, prev_end, preset = _parse_roi_dates(request)

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    prev_start_dt = datetime.combine(prev_start, datetime.min.time())
    prev_end_dt = datetime.combine(prev_end, datetime.max.time())

    clients_current = Client.query.options(joinedload(Client.lead_source))\
        .filter(Client.created_at >= start_dt, Client.created_at <= end_dt).all()
    clients_prev = Client.query.options(joinedload(Client.lead_source))\
        .filter(Client.created_at >= prev_start_dt, Client.created_at <= prev_end_dt).all()

    spend_entries = ChannelSpend.query.filter(
        ChannelSpend.period_month >= start.replace(day=1),
        ChannelSpend.period_month <= end.replace(day=1)).all()
    spend_by_source = defaultdict(Decimal)
    for e in spend_entries:
        spend_by_source[e.lead_source_id] += e.amount

    prev_spend_entries = ChannelSpend.query.filter(
        ChannelSpend.period_month >= prev_start.replace(day=1),
        ChannelSpend.period_month <= prev_end.replace(day=1)).all()
    prev_spend_by_source = defaultdict(Decimal)
    for e in prev_spend_entries:
        prev_spend_by_source[e.lead_source_id] += e.amount

    all_source_ids = set()
    for c in clients_current + clients_prev:
        if c.lead_source_id:
            all_source_ids.add(c.lead_source_id)
    for sid in list(spend_by_source) + list(prev_spend_by_source):
        all_source_ids.add(sid)

    rows = _build_roi_rows(clients_current, spend_by_source, all_source_ids)
    prev_rows = _build_roi_rows(clients_prev, prev_spend_by_source, all_source_ids)

    sources = LeadSource.query.filter(LeadSource.id.in_(all_source_ids)).all() if all_source_ids else []
    source_names = {s.id: s.name for s in sources}
    source_names[None] = 'Unknown / No Source'

    table = []
    for sid, r in rows.items():
        if r['total_leads'] == 0 and r['spend'] == 0:
            continue
        pr = prev_rows.get(sid, {})
        table.append({
            'source_id': sid, 'source_name': source_names.get(sid, 'Unknown'),
            **r,
            'prev_leads': pr.get('total_leads', 0),
            'prev_won': pr.get('won', 0),
            'prev_spend': pr.get('spend', Decimal(0)),
            'prev_revenue': pr.get('total_revenue', Decimal(0)),
            'prev_roi': pr.get('roi'),
        })
    table.sort(key=lambda x: (float(x['total_revenue']), x['total_leads']), reverse=True)

    best = None
    for r in table:
        if r['roi'] and r['roi'] > 0 and r['spend'] > 0:
            if best is None or r['roi'] > best['roi']:
                best = r

    totals = {
        'spend': sum(r['spend'] for r in table),
        'total_leads': sum(r['total_leads'] for r in table),
        'won': sum(r['won'] for r in table),
        'revenue_closed': sum(r['revenue_closed'] for r in table),
        'revenue_projected': sum(r['revenue_projected'] for r in table),
        'total_revenue': sum(r['total_revenue'] for r in table),
        'prev_leads': sum(r['prev_leads'] for r in table),
        'prev_won': sum(r['prev_won'] for r in table),
        'prev_spend': sum(r['prev_spend'] for r in table),
        'prev_revenue': sum(r['prev_revenue'] for r in table),
    }
    tl = totals['total_leads']
    totals['cpl'] = totals['spend'] / tl if tl and totals['spend'] else None
    totals['close_rate'] = (totals['won'] / tl * 100) if tl else None
    totals['roi'] = float(totals['total_revenue'] / totals['spend']) if totals['spend'] else None
    all_dtc = [r['avg_days_to_close'] for r in table if r.get('avg_days_to_close')]
    totals['avg_days_to_close'] = round(sum(all_dtc) / len(all_dtc), 1) if all_dtc else None

    return render_template('roi_report.html',
                           table=table, totals=totals, best=best,
                           start=start, end=end,
                           prev_start=prev_start, prev_end=prev_end,
                           preset=preset)


@app.route('/reports/roi/export')
@require_supervisor
def roi_report_export():
    start, end, prev_start, prev_end, preset = _parse_roi_dates(request)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    clients_current = Client.query.options(joinedload(Client.lead_source))\
        .filter(Client.created_at >= start_dt, Client.created_at <= end_dt).all()

    spend_entries = ChannelSpend.query.filter(
        ChannelSpend.period_month >= start.replace(day=1),
        ChannelSpend.period_month <= end.replace(day=1)).all()
    spend_by_source = defaultdict(Decimal)
    for e in spend_entries:
        spend_by_source[e.lead_source_id] += e.amount

    all_source_ids = set()
    for c in clients_current:
        if c.lead_source_id:
            all_source_ids.add(c.lead_source_id)
    for sid in spend_by_source:
        all_source_ids.add(sid)

    rows = _build_roi_rows(clients_current, spend_by_source, all_source_ids)
    sources = LeadSource.query.filter(LeadSource.id.in_(all_source_ids)).all() if all_source_ids else []
    source_names = {s.id: s.name for s in sources}
    source_names[None] = 'Unknown / No Source'

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow([
        'Source', 'Spend', 'Leads', 'Cost per Lead',
        'Won (Active+Completed)', 'Close Rate',
        'Revenue (Closed)', 'Revenue (Projected)', 'Total Revenue', 'ROI Multiple',
        'Avg Days to Close',
        'Funnel: Lead', 'Funnel: Prospect', 'Funnel: Active', 'Funnel: Completed',
        'Funnel: On Hold', 'Funnel: Lost',
    ])
    sorted_rows = sorted(rows.items(), key=lambda x: float(x[1]['total_revenue']), reverse=True)
    for sid, r in sorted_rows:
        if r['total_leads'] == 0 and r['spend'] == 0:
            continue
        writer.writerow([
            source_names.get(sid, 'Unknown'),
            f"{r['spend']:.2f}", r['total_leads'],
            f"{r['cpl']:.2f}" if r['cpl'] else '',
            r['won'],
            f"{r['close_rate']:.1f}%" if r['close_rate'] is not None else '',
            f"{r['revenue_closed']:.2f}", f"{r['revenue_projected']:.2f}",
            f"{r['total_revenue']:.2f}",
            f"{r['roi']:.2f}x" if r['roi'] else '',
            f"{r['avg_days_to_close']}" if r.get('avg_days_to_close') else '',
            r['funnel_lead'], r['funnel_prospect'], r['funnel_active'],
            r['funnel_completed'], r['funnel_on_hold'], r['funnel_lost'],
        ])

    filename = f"roi_report_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    return Response(
        si.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# --- Estimating Routes ---

@app.route('/estimates')
@require_login
def estimates_list():
    client_id = request.args.get('client_id')
    status_filter = request.args.get('status')
    query = Estimate.query
    if client_id:
        query = query.filter_by(client_id=int(client_id))
    if status_filter:
        query = query.filter_by(status=status_filter)
    estimates = query.order_by(Estimate.updated_at.desc()).all()
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    templates = EstimateTemplate.query.filter_by(is_active=True).order_by(EstimateTemplate.name).all()
    return render_template('estimates_list.html', estimates=estimates, clients=clients,
                         templates=templates, statuses=ESTIMATE_STATUSES,
                         selected_client=client_id, selected_status=status_filter)


@app.route('/estimates/create', methods=['GET', 'POST'])
@require_login
def create_estimate():
    if request.method == 'GET':
        clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
        templates = EstimateTemplate.query.filter_by(is_active=True).order_by(EstimateTemplate.name).all()
        preselect_client = request.args.get('client_id')
        preselect_template = request.args.get('template_id')
        return render_template('estimate_create.html', clients=clients, templates=templates,
                             adu_types=ADU_TYPES, preselect_client=preselect_client,
                             preselect_template=preselect_template)

    client_id = request.form.get('client_id')
    template_id = request.form.get('template_id') or None
    name = request.form.get('name', '').strip()
    adu_type = request.form.get('adu_type', '').strip()
    sqft = request.form.get('sqft', '').strip()

    if not client_id or not name:
        flash('Client and estimate name are required.', 'error')
        return redirect(url_for('create_estimate'))

    client = Client.query.get_or_404(int(client_id))

    # Default from template if selected
    markup, overhead, contingency = Decimal('15'), Decimal('10'), Decimal('5')
    if template_id:
        tpl = EstimateTemplate.query.get(int(template_id))
        if tpl:
            markup = tpl.default_markup_pct
            overhead = tpl.default_overhead_pct
            contingency = tpl.default_contingency_pct
            if not adu_type:
                adu_type = tpl.adu_type
            if not sqft and tpl.default_sqft:
                sqft = str(tpl.default_sqft)

    # Pull ADU fields from client if not specified
    if not adu_type and client.type_of_adu:
        adu_type = client.type_of_adu
    if not sqft and client.desired_adu_sqft:
        sqft = client.desired_adu_sqft

    estimate = Estimate(
        client_id=client.id,
        template_id=int(template_id) if template_id else None,
        name=name,
        adu_type=adu_type or None,
        sqft=int(sqft) if sqft and sqft.isdigit() else None,
        markup_pct=markup,
        overhead_pct=overhead,
        contingency_pct=contingency,
        created_by_user_id=current_user.id,
    )
    db.session.add(estimate)
    db.session.flush()

    # Populate line items from template
    if template_id:
        tpl = EstimateTemplate.query.get(int(template_id))
        if tpl:
            est_sqft = estimate.sqft or tpl.default_sqft or 400
            for ti in tpl.items.order_by(EstimateTemplateItem.sort_order).all():
                ai = ti.assembly_item
                # Scale qty for SF-based items
                qty = float(ti.default_qty)
                if ai.unit == 'SF' and est_sqft:
                    qty = est_sqft  # SF items scale to building size
                elif ai.unit == 'SQ':
                    qty = max(1, est_sqft / 100)  # roofing squares
                elif ai.unit == 'LF':
                    qty = float(ti.default_qty)  # keep template default for linear items

                li = EstimateLineItem(
                    estimate_id=estimate.id,
                    cost_code_id=ai.cost_code_id,
                    assembly_item_id=ai.id,
                    description=ai.name,
                    unit=ai.unit,
                    qty=Decimal(str(round(qty, 2))),
                    unit_cost=ai.unit_cost,
                    labor_pct=ai.labor_pct,
                    material_pct=ai.material_pct,
                    waste_pct=ai.waste_pct,
                    sort_order=ti.sort_order,
                )
                db.session.add(li)

    db.session.commit()
    flash(f'Estimate "{name}" created.', 'success')
    return redirect(url_for('edit_estimate', estimate_id=estimate.id))


@app.route('/estimates/<int:estimate_id>')
@require_login
def view_estimate(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)
    # Group line items by cost code
    line_items = estimate.line_items.order_by(EstimateLineItem.sort_order).all()
    grouped = defaultdict(list)
    for li in line_items:
        key = li.cost_code.code if li.cost_code else 'Other'
        grouped[key].append(li)
    show_internal = request.args.get('internal', '1') == '1'
    return render_template('estimate_view.html', estimate=estimate,
                         grouped=dict(grouped), line_items=line_items,
                         show_internal=show_internal)


@app.route('/estimates/<int:estimate_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_estimate(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)

    if request.method == 'GET':
        line_items = estimate.line_items.order_by(EstimateLineItem.sort_order).all()
        cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
        assembly_items = AssemblyItem.query.filter_by(is_active=True).order_by(AssemblyItem.sort_order).all()
        return render_template('estimate_edit.html', estimate=estimate,
                             line_items=line_items, cost_codes=cost_codes,
                             assembly_items=assembly_items, adu_types=ADU_TYPES,
                             statuses=ESTIMATE_STATUSES)

    # Update estimate header
    estimate.name = request.form.get('name', estimate.name).strip()
    estimate.adu_type = request.form.get('adu_type', '').strip() or None
    sqft_str = request.form.get('sqft', '').strip()
    estimate.sqft = int(sqft_str) if sqft_str and sqft_str.isdigit() else None
    estimate.notes = request.form.get('notes', '').strip() or None

    try:
        estimate.markup_pct = Decimal(request.form.get('markup_pct', '15'))
        estimate.overhead_pct = Decimal(request.form.get('overhead_pct', '10'))
        estimate.contingency_pct = Decimal(request.form.get('contingency_pct', '5'))
    except (InvalidOperation, ValueError):
        pass

    status = request.form.get('status', '').strip()
    if status and status in ESTIMATE_STATUSES:
        if status == 'Accepted' and estimate.status != 'Accepted':
            estimate.accepted_at = datetime.now(timezone.utc)
        estimate.status = status

    db.session.commit()
    flash('Estimate updated.', 'success')
    return redirect(url_for('edit_estimate', estimate_id=estimate.id))


@app.route('/estimates/<int:estimate_id>/line-items', methods=['POST'])
@require_login
def add_estimate_line_item(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)
    cost_code_id = request.form.get('cost_code_id')
    assembly_item_id = request.form.get('assembly_item_id') or None
    description = request.form.get('description', '').strip()
    unit = request.form.get('unit', 'EA').strip()

    if not cost_code_id or not description:
        flash('Cost code and description are required.', 'error')
        return redirect(url_for('edit_estimate', estimate_id=estimate.id))

    # Pre-fill from assembly item if selected
    unit_cost, labor_pct, material_pct, waste_pct, qty = Decimal('0'), Decimal('50'), Decimal('50'), Decimal('5'), Decimal('1')
    if assembly_item_id:
        ai = AssemblyItem.query.get(int(assembly_item_id))
        if ai:
            unit_cost = ai.unit_cost
            labor_pct = ai.labor_pct
            material_pct = ai.material_pct
            waste_pct = ai.waste_pct
            unit = ai.unit
            if not description:
                description = ai.name

    try:
        qty = Decimal(request.form.get('qty', '1'))
        unit_cost = Decimal(request.form.get('unit_cost', str(unit_cost)))
    except (InvalidOperation, ValueError):
        pass

    max_sort = db.session.query(func.max(EstimateLineItem.sort_order)).filter_by(estimate_id=estimate.id).scalar() or 0

    li = EstimateLineItem(
        estimate_id=estimate.id,
        cost_code_id=int(cost_code_id),
        assembly_item_id=int(assembly_item_id) if assembly_item_id else None,
        description=description,
        unit=unit,
        qty=qty,
        unit_cost=unit_cost,
        labor_pct=labor_pct,
        material_pct=material_pct,
        waste_pct=waste_pct,
        sort_order=max_sort + 10,
    )
    db.session.add(li)
    db.session.commit()
    flash('Line item added.', 'success')
    return redirect(url_for('edit_estimate', estimate_id=estimate.id))


@app.route('/estimates/<int:estimate_id>/line-items/<int:item_id>/update', methods=['POST'])
@require_login
def update_estimate_line_item(estimate_id, item_id):
    li = EstimateLineItem.query.get_or_404(item_id)
    if li.estimate_id != estimate_id:
        abort(404)
    try:
        li.description = request.form.get('description', li.description).strip()
        li.qty = Decimal(request.form.get('qty', str(li.qty)))
        li.unit_cost = Decimal(request.form.get('unit_cost', str(li.unit_cost)))
        li.unit = request.form.get('unit', li.unit).strip()
        li.waste_pct = Decimal(request.form.get('waste_pct', str(li.waste_pct)))
        li.labor_pct = Decimal(request.form.get('labor_pct', str(li.labor_pct)))
        li.material_pct = Decimal(request.form.get('material_pct', str(li.material_pct)))
    except (InvalidOperation, ValueError):
        flash('Invalid number format.', 'error')
        return redirect(url_for('edit_estimate', estimate_id=estimate_id))
    db.session.commit()
    return redirect(url_for('edit_estimate', estimate_id=estimate_id))


@app.route('/estimates/<int:estimate_id>/line-items/<int:item_id>/delete', methods=['POST'])
@require_login
def delete_estimate_line_item(estimate_id, item_id):
    li = EstimateLineItem.query.get_or_404(item_id)
    if li.estimate_id != estimate_id:
        abort(404)
    db.session.delete(li)
    db.session.commit()
    flash('Line item removed.', 'success')
    return redirect(url_for('edit_estimate', estimate_id=estimate_id))


@app.route('/estimates/<int:estimate_id>/duplicate', methods=['POST'])
@require_login
def duplicate_estimate(estimate_id):
    orig = Estimate.query.get_or_404(estimate_id)
    new_est = Estimate(
        client_id=orig.client_id,
        template_id=orig.template_id,
        name=f"{orig.name} (Copy)",
        adu_type=orig.adu_type,
        sqft=orig.sqft,
        markup_pct=orig.markup_pct,
        overhead_pct=orig.overhead_pct,
        contingency_pct=orig.contingency_pct,
        notes=orig.notes,
        created_by_user_id=current_user.id,
    )
    db.session.add(new_est)
    db.session.flush()
    for li in orig.line_items.all():
        new_li = EstimateLineItem(
            estimate_id=new_est.id,
            cost_code_id=li.cost_code_id,
            assembly_item_id=li.assembly_item_id,
            description=li.description,
            unit=li.unit,
            qty=li.qty,
            unit_cost=li.unit_cost,
            labor_pct=li.labor_pct,
            material_pct=li.material_pct,
            waste_pct=li.waste_pct,
            sort_order=li.sort_order,
        )
        db.session.add(new_li)
    db.session.commit()
    flash(f'Estimate duplicated as "{new_est.name}".', 'success')
    return redirect(url_for('edit_estimate', estimate_id=new_est.id))


@app.route('/estimates/<int:estimate_id>/accept', methods=['POST'])
@require_supervisor
def accept_estimate(estimate_id):
    """Accept estimate: carry into Client budget by cost code, set contract value."""
    estimate = Estimate.query.get_or_404(estimate_id)
    client = estimate.client
    project = client.default_project()

    estimate.status = 'Accepted'
    estimate.accepted_at = datetime.now(timezone.utc)
    project.contract_value = estimate.total
    client.final_contract_value = estimate.total

    _carry_estimate_to_budget(estimate, project)
    db.session.commit()

    budget_count = Budget.query.filter_by(project_id=project.id).count()
    flash(f'Estimate accepted. ${estimate.total:,.2f} contract value set. '
          f'{budget_count} budget lines created for {client.name}.', 'success')
    return redirect(url_for('view_estimate', estimate_id=estimate.id))


@app.route('/estimates/<int:estimate_id>/delete', methods=['POST'])
@require_supervisor
def delete_estimate(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)
    client_id = estimate.client_id
    if estimate.status == 'Accepted':
        flash('Cannot delete an accepted estimate.', 'error')
        return redirect(url_for('view_estimate', estimate_id=estimate.id))
    db.session.delete(estimate)
    db.session.commit()
    flash('Estimate deleted.', 'success')
    return redirect(url_for('estimates_list', client_id=client_id))


@app.route('/api/assembly-items/<int:item_id>')
@require_login
def api_assembly_item(item_id):
    """Return assembly item details as JSON for dynamic form population."""
    ai = AssemblyItem.query.get_or_404(item_id)
    return jsonify({
        'id': ai.id,
        'name': ai.name,
        'unit': ai.unit,
        'unit_cost': float(ai.unit_cost),
        'labor_pct': float(ai.labor_pct),
        'material_pct': float(ai.material_pct),
        'waste_pct': float(ai.waste_pct),
        'cost_code_id': ai.cost_code_id,
    })


# Stub: PDF takeoff interface (not yet built)
@app.route('/estimates/<int:estimate_id>/takeoff')
@require_login
def estimate_takeoff(estimate_id):
    """Stub for future on-screen PDF takeoff interface."""
    estimate = Estimate.query.get_or_404(estimate_id)
    flash('PDF takeoff is coming soon. Use the estimate builder for now.', 'info')
    return redirect(url_for('edit_estimate', estimate_id=estimate.id))


# --- Proposals & Contracts ---

def _generate_token():
    import secrets
    return secrets.token_urlsafe(32)


def _default_scope(estimate):
    """Generate default scope text from estimate line items."""
    lines = []
    items = estimate.line_items.order_by(EstimateLineItem.sort_order).all()
    grouped = defaultdict(list)
    for li in items:
        key = li.cost_code.name if li.cost_code else 'Other'
        grouped[key].append(li)
    for code_name, lis in grouped.items():
        lines.append(f"**{code_name}**")
        for li in lis:
            lines.append(f"- {li.description} ({li.qty} {li.unit})")
    return '\n'.join(lines)


def _default_terms():
    return """1. **Payment Terms**: Payments due per the draw schedule outlined in this contract. Net 15 days from invoice date.

2. **Change Orders**: Any changes to the scope of work must be agreed upon in writing. Change orders may affect the contract price and schedule.

3. **Permits**: Contractor shall obtain all required building permits. Permit fees are included in the contract price unless otherwise noted.

4. **Warranty**: Contractor warrants all work for a period of one (1) year from substantial completion against defects in workmanship. Manufacturer warranties on materials and equipment are passed through to the Owner.

5. **Insurance**: Contractor shall maintain general liability insurance ($1M per occurrence) and workers' compensation insurance for the duration of the project.

6. **Access**: Owner shall provide Contractor reasonable access to the property during normal working hours (7:00 AM - 5:00 PM, Monday through Saturday).

7. **Dispute Resolution**: Any disputes shall first be addressed through good-faith negotiation, then mediation, before pursuing other legal remedies.

8. **Cancellation**: Either party may cancel this contract with 30 days written notice. Owner shall pay for all work completed to date plus reasonable demobilization costs."""


def _default_draw_schedule():
    """Return default ADU draw schedule milestones."""
    return [
        ('Deposit / Mobilization', 10),
        ('Foundation Complete', 15),
        ('Framing & Roof Complete', 20),
        ('Rough MEP Complete', 15),
        ('Drywall & Interior Rough', 15),
        ('Finishes & Fixtures', 15),
        ('Final Completion & Punch List', 10),
    ]


@app.route('/estimates/<int:estimate_id>/proposal', methods=['GET', 'POST'])
@require_login
def create_proposal(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)

    if request.method == 'GET':
        scope = _default_scope(estimate)
        return render_template('proposal_create.html', estimate=estimate,
                             default_scope=scope, statuses=PROPOSAL_STATUSES)

    cover_note = request.form.get('cover_note', '').strip()
    scope_text = request.form.get('scope_text', '').strip()
    exclusions_text = request.form.get('exclusions_text', '').strip()
    validity_days = int(request.form.get('validity_days', '30'))

    proposal = Proposal(
        estimate_id=estimate.id,
        client_id=estimate.client_id,
        share_token=_generate_token(),
        cover_note=cover_note or None,
        scope_text=scope_text or None,
        exclusions_text=exclusions_text or None,
        validity_days=validity_days,
        created_by_user_id=current_user.id,
    )
    db.session.add(proposal)
    db.session.commit()
    flash('Proposal created.', 'success')
    return redirect(url_for('view_proposal', proposal_id=proposal.id))


@app.route('/proposals/<int:proposal_id>')
@require_login
def view_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    estimate = proposal.estimate
    line_items = estimate.line_items.order_by(EstimateLineItem.sort_order).all()
    grouped = defaultdict(list)
    for li in line_items:
        key = li.cost_code.code if li.cost_code else 'Other'
        grouped[key].append(li)
    return render_template('proposal_view.html', proposal=proposal, estimate=estimate,
                         grouped=dict(grouped), line_items=line_items)


@app.route('/proposals/<int:proposal_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    if request.method == 'GET':
        return render_template('proposal_edit.html', proposal=proposal,
                             statuses=PROPOSAL_STATUSES)
    proposal.cover_note = request.form.get('cover_note', '').strip() or None
    proposal.scope_text = request.form.get('scope_text', '').strip() or None
    proposal.exclusions_text = request.form.get('exclusions_text', '').strip() or None
    proposal.validity_days = int(request.form.get('validity_days', '30'))
    status = request.form.get('status', '')
    if status in PROPOSAL_STATUSES:
        proposal.status = status
    db.session.commit()
    flash('Proposal updated.', 'success')
    return redirect(url_for('view_proposal', proposal_id=proposal.id))


@app.route('/proposals/<int:proposal_id>/send', methods=['POST'])
@require_login
def send_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    proposal.status = 'Sent'
    db.session.commit()
    share_url = url_for('public_proposal', token=proposal.share_token, _external=True)
    flash(f'Proposal marked as sent. Share link: {share_url}', 'success')
    return redirect(url_for('view_proposal', proposal_id=proposal.id))


@app.route('/p/<token>')
def public_proposal(token):
    """Public (no auth) proposal view for clients."""
    proposal = Proposal.query.filter_by(share_token=token).first_or_404()
    if not proposal.viewed_at:
        proposal.viewed_at = datetime.now(timezone.utc)
        proposal.viewed_ip = request.remote_addr
        if proposal.status == 'Sent':
            proposal.status = 'Viewed'
        db.session.commit()
    estimate = proposal.estimate
    line_items = estimate.line_items.order_by(EstimateLineItem.sort_order).all()
    grouped = defaultdict(list)
    for li in line_items:
        key = li.cost_code.name if li.cost_code else 'Other'
        grouped[key].append(li)
    return render_template('proposal_public.html', proposal=proposal, estimate=estimate,
                         grouped=dict(grouped), token=token)


@app.route('/p/<token>/accept', methods=['POST'])
def accept_proposal_public(token):
    """Client accepts proposal — records name + IP as audit trail."""
    proposal = Proposal.query.filter_by(share_token=token).first_or_404()
    if proposal.status in ('Accepted', 'Rejected', 'Expired'):
        flash('This proposal has already been responded to.', 'error')
        return redirect(url_for('public_proposal', token=token))
    if proposal.is_expired:
        proposal.status = 'Expired'
        db.session.commit()
        flash('This proposal has expired.', 'error')
        return redirect(url_for('public_proposal', token=token))

    accepted_name = request.form.get('accepted_name', '').strip()
    if not accepted_name:
        flash('Please enter your name to accept.', 'error')
        return redirect(url_for('public_proposal', token=token))

    proposal.status = 'Accepted'
    proposal.accepted_at = datetime.now(timezone.utc)
    proposal.accepted_ip = request.remote_addr
    proposal.accepted_name = accepted_name

    # Also accept the underlying estimate
    estimate = proposal.estimate
    if estimate.status != 'Accepted':
        estimate.status = 'Accepted'
        estimate.accepted_at = datetime.now(timezone.utc)

    # Log to ClientActivity
    activity = ClientActivity(
        client_id=proposal.client_id,
        user_id=proposal.created_by_user_id,
        activity_type='Proposal Accepted',
        note_text=f'Proposal accepted by {accepted_name} (IP: {request.remote_addr})',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash('Proposal accepted! You will receive the contract for signature.', 'success')
    return redirect(url_for('public_proposal', token=token))


@app.route('/proposals/<int:proposal_id>/contract', methods=['GET', 'POST'])
@require_login
def create_contract(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    estimate = proposal.estimate

    if request.method == 'GET':
        scope = proposal.scope_text or _default_scope(estimate)
        terms = _default_terms()
        draws = _default_draw_schedule()
        # Generate contract number
        count = Contract.query.count()
        contract_num = f"ADU-{datetime.now().strftime('%Y')}-{count + 1:04d}"
        return render_template('contract_create.html', proposal=proposal,
                             estimate=estimate, default_scope=scope,
                             default_terms=terms, default_draws=draws,
                             contract_number=contract_num)

    scope_text = request.form.get('scope_text', '').strip()
    terms_text = request.form.get('terms_text', '').strip()
    contract_number = request.form.get('contract_number', '').strip()

    contract = Contract(
        proposal_id=proposal.id,
        client_id=proposal.client_id,
        estimate_id=estimate.id,
        share_token=_generate_token(),
        contract_number=contract_number or f"ADU-{datetime.now().strftime('%Y')}-{Contract.query.count() + 1:04d}",
        scope_text=scope_text or None,
        terms_text=terms_text or None,
        total_price=estimate.total,
        created_by_user_id=current_user.id,
    )
    db.session.add(contract)
    db.session.flush()

    # Create draw schedule
    milestones = request.form.getlist('milestone')
    pcts = request.form.getlist('draw_pct')
    for i, (milestone, pct_str) in enumerate(zip(milestones, pcts)):
        if not milestone.strip():
            continue
        try:
            pct = Decimal(pct_str)
        except (InvalidOperation, ValueError):
            pct = Decimal('0')
        amount = (estimate.total * pct / 100).quantize(Decimal('0.01'))
        db.session.add(DrawScheduleItem(
            contract_id=contract.id,
            milestone=milestone.strip(),
            pct_of_total=pct,
            amount=amount,
            sort_order=(i + 1) * 10,
        ))

    # Log activity
    activity = ClientActivity(
        client_id=contract.client_id,
        user_id=current_user.id,
        activity_type='Contract Created',
        note_text=f'Contract {contract.contract_number} created for ${estimate.total:,.2f}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()
    flash(f'Contract {contract.contract_number} created.', 'success')
    return redirect(url_for('view_contract', contract_id=contract.id))


@app.route('/contracts/<int:contract_id>')
@require_login
def view_contract(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()
    return render_template('contract_view.html', contract=contract, draws=draws)


@app.route('/contracts/<int:contract_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_contract(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    if contract.status in ('Signed', 'Executed'):
        flash('Cannot edit a signed contract.', 'error')
        return redirect(url_for('view_contract', contract_id=contract.id))
    if request.method == 'GET':
        draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()
        return render_template('contract_edit.html', contract=contract, draws=draws,
                             statuses=CONTRACT_STATUSES)

    contract.scope_text = request.form.get('scope_text', '').strip() or None
    contract.terms_text = request.form.get('terms_text', '').strip() or None
    contract.contract_number = request.form.get('contract_number', contract.contract_number).strip()
    status = request.form.get('status', '')
    if status in CONTRACT_STATUSES and status not in ('Signed', 'Executed'):
        contract.status = status
    db.session.commit()
    flash('Contract updated.', 'success')
    return redirect(url_for('view_contract', contract_id=contract.id))


@app.route('/contracts/<int:contract_id>/send', methods=['POST'])
@require_login
def send_contract(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    contract.status = 'Sent'
    db.session.commit()
    share_url = url_for('public_contract', token=contract.share_token, _external=True)
    flash(f'Contract sent. Share link: {share_url}', 'success')
    return redirect(url_for('view_contract', contract_id=contract.id))


@app.route('/c/<token>')
def public_contract(token):
    """Public contract view with signature pad."""
    contract = Contract.query.filter_by(share_token=token).first_or_404()
    draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()
    return render_template('contract_public.html', contract=contract, draws=draws, token=token)


@app.route('/c/<token>/sign', methods=['POST'])
def sign_contract_public(token):
    """Client signs contract — audited signature with timestamp + IP."""
    contract = Contract.query.filter_by(share_token=token).first_or_404()
    if contract.is_signed:
        flash('This contract has already been signed.', 'info')
        return redirect(url_for('public_contract', token=token))

    signed_name = request.form.get('signed_name', '').strip()
    signed_email = request.form.get('signed_email', '').strip()
    signature_data = request.form.get('signature_data', '').strip()

    if not signed_name or not signature_data:
        flash('Name and signature are required.', 'error')
        return redirect(url_for('public_contract', token=token))

    now = datetime.now(timezone.utc)
    contract.signed_at = now
    contract.signed_ip = request.remote_addr
    contract.signed_name = signed_name
    contract.signed_email = signed_email or None
    contract.signature_data = signature_data
    contract.status = 'Signed'

    # Store signed record in R2
    client = contract.client
    try:
        if not client.storage_prefix:
            from r2_storage_helper import build_client_prefix
            client.storage_prefix = build_client_prefix(client.name, client.address)

        from r2_storage_helper import upload_file as r2_upload
        # Store signature audit log as JSON
        import json
        audit = {
            'contract_id': contract.id,
            'contract_number': contract.contract_number,
            'signed_name': signed_name,
            'signed_email': signed_email,
            'signed_at': now.isoformat(),
            'signed_ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'total_price': str(contract.total_price),
        }
        audit_key = f"{client.storage_prefix}/contracts/{contract.contract_number}_signature_audit.json"
        r2_upload(json.dumps(audit, indent=2).encode(), audit_key, 'application/json')
        contract.signed_pdf_key = audit_key
    except Exception as e:
        # Don't fail the signature if R2 upload fails
        current_app.logger.error(f'R2 upload failed for contract signature: {e}')

    # Accept the estimate + carry into budget if not already done
    estimate = contract.estimate
    if estimate.status != 'Accepted':
        estimate.status = 'Accepted'
        estimate.accepted_at = now
    proposal = contract.proposal
    if proposal.status != 'Accepted':
        proposal.status = 'Accepted'
        proposal.accepted_at = now
        proposal.accepted_name = signed_name
        proposal.accepted_ip = request.remote_addr

    # Set contract value on client/project
    project = client.default_project()
    project.contract_value = contract.total_price
    client.final_contract_value = contract.total_price

    # Carry estimate into budget (same logic as accept_estimate)
    _carry_estimate_to_budget(estimate, project)

    # Log to ClientActivity
    activity = ClientActivity(
        client_id=contract.client_id,
        user_id=contract.created_by_user_id,
        activity_type='Contract Signed',
        note_text=f'Contract {contract.contract_number} signed by {signed_name} '
                  f'(IP: {request.remote_addr}) for ${contract.total_price:,.2f}',
        activity_date=now,
        file_path=contract.signed_pdf_key,
        file_name=f'{contract.contract_number}_signature_audit.json',
    )
    db.session.add(activity)
    db.session.commit()

    flash('Contract signed successfully! Thank you.', 'success')
    return redirect(url_for('public_contract', token=token))


def _carry_estimate_to_budget(estimate, project):
    """Carry estimate line items into Budget by cost code (Labor + Material)."""
    code_labor = defaultdict(Decimal)
    code_material = defaultdict(Decimal)
    for li in estimate.line_items.all():
        code_labor[li.cost_code_id] += li.labor_amount
        code_material[li.cost_code_id] += li.material_amount

    subtotal = estimate.subtotal
    multiplier = estimate.total / subtotal if subtotal > 0 else Decimal('1')

    for cc_id, labor_amt in code_labor.items():
        scaled = (labor_amt * multiplier).quantize(Decimal('0.01'))
        existing = Budget.query.filter_by(project_id=project.id, cost_code_id=cc_id, cost_type='Labor').first()
        if existing:
            existing.amount = scaled
            existing.notes = f'From estimate #{estimate.id}'
        else:
            db.session.add(Budget(
                project_id=project.id, cost_code_id=cc_id,
                cost_type='Labor', amount=scaled,
                notes=f'From estimate #{estimate.id}',
            ))

    for cc_id, mat_amt in code_material.items():
        scaled = (mat_amt * multiplier).quantize(Decimal('0.01'))
        existing = Budget.query.filter_by(project_id=project.id, cost_code_id=cc_id, cost_type='Material').first()
        if existing:
            existing.amount = scaled
            existing.notes = f'From estimate #{estimate.id}'
        else:
            db.session.add(Budget(
                project_id=project.id, cost_code_id=cc_id,
                cost_type='Material', amount=scaled,
                notes=f'From estimate #{estimate.id}',
            ))


# --- Assembly Item Management ---

@app.route('/settings/assembly-items')
@require_supervisor
def assembly_items_settings():
    items = AssemblyItem.query.order_by(AssemblyItem.sort_order).all()
    cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
    return render_template('assembly_items_settings.html', items=items, cost_codes=cost_codes)


@app.route('/settings/assembly-items/add', methods=['POST'])
@require_supervisor
def add_assembly_item():
    name = request.form.get('name', '').strip()
    cost_code_id = request.form.get('cost_code_id')
    if not name or not cost_code_id:
        flash('Name and cost code are required.', 'error')
        return redirect(url_for('assembly_items_settings'))
    try:
        ai = AssemblyItem(
            cost_code_id=int(cost_code_id),
            name=name,
            description=request.form.get('description', '').strip() or None,
            unit=request.form.get('unit', 'EA').strip(),
            unit_cost=Decimal(request.form.get('unit_cost', '0')),
            labor_pct=Decimal(request.form.get('labor_pct', '50')),
            material_pct=Decimal(request.form.get('material_pct', '50')),
            waste_pct=Decimal(request.form.get('waste_pct', '5')),
            sort_order=int(request.form.get('sort_order', '0')),
        )
        db.session.add(ai)
        db.session.commit()
        flash(f'Assembly item "{name}" added.', 'success')
    except (InvalidOperation, ValueError) as e:
        flash(f'Invalid input: {e}', 'error')
    return redirect(url_for('assembly_items_settings'))


@app.route('/settings/assembly-items/<int:item_id>/toggle', methods=['POST'])
@require_supervisor
def toggle_assembly_item(item_id):
    ai = AssemblyItem.query.get_or_404(item_id)
    ai.is_active = not ai.is_active
    db.session.commit()
    flash(f'Assembly item "{ai.name}" {"activated" if ai.is_active else "deactivated"}.', 'success')
    return redirect(url_for('assembly_items_settings'))


@app.route('/api/search')
@require_login
def global_search():
    """Search clients and activities by substring, case-insensitive."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'clients': [], 'activities': []})

    like_q = f'%{q}%'
    results = {'clients': [], 'activities': []}

    # Search clients: name, address, contact_name
    clients = Client.query.filter(
        db.or_(
            Client.name.ilike(like_q),
            Client.address.ilike(like_q),
            Client.contact_name.ilike(like_q),
        )
    ).order_by(Client.name).limit(10).all()

    for c in clients:
        results['clients'].append({
            'id': c.id,
            'name': c.name,
            'address': c.address or '',
            'status': c.status or '',
            'url': url_for('edit_client', client_id=c.id),
        })

    # Search activities: note_text
    activities = ClientActivity.query.join(Client).filter(
        ClientActivity.note_text.ilike(like_q)
    ).order_by(ClientActivity.activity_date.desc()).limit(10).all()

    for a in activities:
        results['activities'].append({
            'id': a.id,
            'note': (a.note_text[:80] + '…') if len(a.note_text) > 80 else a.note_text,
            'type': a.activity_type,
            'client_name': a.client.name if a.client else '',
            'client_id': a.client_id,
            'url': url_for('edit_client', client_id=a.client_id),
        })

    return jsonify(results)


# ── Document Management ──────────────────────────────────────────────

def _ensure_storage_prefix(client):
    if not client.storage_prefix:
        from r2_storage_helper import build_client_prefix
        client.storage_prefix = build_client_prefix(client.name, client.address)
        db.session.commit()


def _can_view_document(doc, user):
    """Role-based visibility check."""
    if doc.visibility == 'team':
        return True
    if doc.visibility == 'supervisor':
        return user.role == 'supervisor'
    return True  # 'client' visibility = everyone


@app.route('/clients/<int:client_id>/documents')
@require_login
def client_documents(client_id):
    client = Client.query.get_or_404(client_id)
    folder = request.args.get('folder', '')
    q = Document.query.filter_by(client_id=client_id, is_superseded=False)
    if folder and folder in DOCUMENT_FOLDER_KEYS:
        q = q.filter_by(folder=folder)
    # Role-based filtering
    if current_user.role != 'supervisor':
        q = q.filter(Document.visibility != 'supervisor')
    documents = q.order_by(Document.folder, Document.updated_at.desc()).all()
    # Group by folder
    by_folder = defaultdict(list)
    for doc in documents:
        by_folder[doc.folder].append(doc)
    permits = Permit.query.filter_by(client_id=client_id).order_by(Permit.updated_at.desc()).all()
    return render_template('client_documents.html', client=client,
                           documents=documents, by_folder=by_folder,
                           folders=DOCUMENT_FOLDERS, active_folder=folder,
                           permits=permits, permit_statuses=PERMIT_STATUSES,
                           permit_types=PERMIT_TYPES)


@app.route('/clients/<int:client_id>/documents/upload', methods=['POST'])
@require_login
def upload_document(client_id):
    from werkzeug.utils import secure_filename
    import mimetypes

    client = Client.query.get_or_404(client_id)
    _ensure_storage_prefix(client)

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400

    folder = request.form.get('folder', 'other')
    if folder not in DOCUMENT_FOLDER_KEYS:
        folder = 'other'

    title = request.form.get('title', '').strip() or filename
    description = request.form.get('description', '').strip() or None
    visibility = request.form.get('visibility', 'team')
    if visibility not in ('team', 'supervisor', 'client'):
        visibility = 'team'

    file_content = file.read()
    file_size = len(file_content)
    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    key = f"{client.storage_prefix}/{folder}/{timestamp}_v1_{filename}"

    try:
        from r2_storage_helper import upload_file as r2_upload
        r2_upload(file_content, key, mime)

        doc = Document(
            client_id=client_id,
            folder=folder,
            title=title,
            description=description,
            file_name=filename,
            mime_type=mime,
            visibility=visibility,
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=key,
            file_name=filename,
            file_size=file_size,
            mime_type=mime,
            change_note='Initial upload',
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(version)
        db.session.flush()

        doc.current_version_id = version.id

        # Audit trail
        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type='Document uploaded',
            note_text=f'Uploaded "{title}" to {folder}',
            activity_date=datetime.now(timezone.utc),
            file_path=key,
            file_name=filename,
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({
            'success': True,
            'document_id': doc.id,
            'title': doc.title,
            'redirect': url_for('client_documents', client_id=client_id, folder=folder),
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Document upload failed: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/revise', methods=['POST'])
@require_login
def revise_document(client_id, doc_id):
    """Upload a new revision of an existing document. Never overwrites."""
    from werkzeug.utils import secure_filename
    import mimetypes

    client = Client.query.get_or_404(client_id)
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    _ensure_storage_prefix(client)

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400

    change_note = request.form.get('change_note', '').strip() or None

    file_content = file.read()
    file_size = len(file_content)
    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # Next version number
    max_ver = db.session.query(func.max(DocumentVersion.version_number)).filter_by(
        document_id=doc.id).scalar() or 0
    next_ver = max_ver + 1

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    key = f"{client.storage_prefix}/{doc.folder}/{timestamp}_v{next_ver}_{filename}"

    try:
        from r2_storage_helper import upload_file as r2_upload
        r2_upload(file_content, key, mime)

        version = DocumentVersion(
            document_id=doc.id,
            version_number=next_ver,
            storage_key=key,
            file_name=filename,
            file_size=file_size,
            mime_type=mime,
            change_note=change_note,
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(version)
        db.session.flush()

        doc.current_version_id = version.id
        doc.file_name = filename
        doc.mime_type = mime
        doc.updated_at = datetime.now(timezone.utc)

        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type='Document revised',
            note_text=f'Uploaded revision v{next_ver} of "{doc.title}"'
                      + (f' — {change_note}' if change_note else ''),
            activity_date=datetime.now(timezone.utc),
            file_path=key,
            file_name=filename,
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({
            'success': True,
            'version_number': next_ver,
            'redirect': url_for('view_document', client_id=client_id, doc_id=doc.id),
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Document revision failed: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/supersede', methods=['POST'])
@require_login
def supersede_document(client_id, doc_id):
    """Mark a document as superseded by a new one (for drawings)."""
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    new_doc_id = request.form.get('new_document_id', type=int)
    doc.is_superseded = True
    note = f'"{doc.title}" marked as superseded'
    if new_doc_id:
        new_doc = Document.query.filter_by(id=new_doc_id, client_id=client_id).first_or_404()
        doc.superseded_by_id = new_doc.id
        note = f'"{doc.title}" superseded by "{new_doc.title}"'
    activity = ClientActivity(
        client_id=client_id,
        user_id=current_user.id,
        activity_type='Document superseded',
        note_text=note,
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()
    flash(f'"{doc.title}" marked as superseded.', 'success')
    return redirect(url_for('client_documents', client_id=client_id, folder=doc.folder))


@app.route('/clients/<int:client_id>/documents/<int:doc_id>')
@require_login
def view_document(client_id, doc_id):
    """Document detail page with version history."""
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    if not _can_view_document(doc, current_user):
        abort(403)
    client = Client.query.get_or_404(client_id)
    versions = doc.versions.all()
    # Other non-superseded docs in same folder for supersede picker
    folder_docs = Document.query.filter(
        Document.client_id == client_id,
        Document.folder == doc.folder,
        Document.id != doc.id,
        Document.is_superseded == False,
    ).order_by(Document.title).all()
    return render_template('document_view.html', client=client, doc=doc,
                           versions=versions, folder_docs=folder_docs,
                           folders=DOCUMENT_FOLDERS)


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/edit', methods=['POST'])
@require_login
def edit_document(client_id, doc_id):
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    doc.title = request.form.get('title', doc.title).strip()
    doc.description = request.form.get('description', '').strip() or None
    doc.folder = request.form.get('folder', doc.folder)
    visibility = request.form.get('visibility', doc.visibility)
    if visibility in ('team', 'supervisor', 'client'):
        doc.visibility = visibility
    db.session.commit()
    flash('Document updated.', 'success')
    return redirect(url_for('view_document', client_id=client_id, doc_id=doc.id))


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/delete', methods=['POST'])
@require_supervisor
def delete_document(client_id, doc_id):
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    folder = doc.folder
    title = doc.title
    # Don't delete R2 objects — keep for audit trail
    db.session.delete(doc)
    activity = ClientActivity(
        client_id=client_id,
        user_id=current_user.id,
        activity_type='Document deleted',
        note_text=f'Deleted document "{title}" from {folder}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()
    flash(f'Document "{title}" deleted.', 'success')
    return redirect(url_for('client_documents', client_id=client_id, folder=folder))


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/download')
@app.route('/clients/<int:client_id>/documents/<int:doc_id>/download/<int:version_id>')
@require_login
def download_document(client_id, doc_id, version_id=None):
    """Serve a document via presigned URL (or direct download as fallback)."""
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    if not _can_view_document(doc, current_user):
        abort(403)

    if version_id:
        version = DocumentVersion.query.filter_by(id=version_id, document_id=doc.id).first_or_404()
    else:
        version = doc.current_version
        if not version:
            abort(404)

    try:
        from r2_storage_helper import generate_presigned_url
        url = generate_presigned_url(version.storage_key, expiration=3600)
        return redirect(url)
    except Exception as e:
        current_app.logger.error(f'Presigned URL failed: {e}')
        # Fallback: stream from R2
        from r2_storage_helper import download_file
        from flask import send_file
        content = download_file(version.storage_key)
        return send_file(
            BytesIO(content),
            download_name=version.file_name,
            mimetype=version.mime_type or 'application/octet-stream',
        )


@app.route('/clients/<int:client_id>/documents/<int:doc_id>/view-pdf')
@app.route('/clients/<int:client_id>/documents/<int:doc_id>/view-pdf/<int:version_id>')
@require_login
def view_pdf(client_id, doc_id, version_id=None):
    """PDF viewer page with basic markup tools."""
    doc = Document.query.filter_by(id=doc_id, client_id=client_id).first_or_404()
    if not _can_view_document(doc, current_user):
        abort(403)
    client = Client.query.get_or_404(client_id)

    if version_id:
        version = DocumentVersion.query.filter_by(id=version_id, document_id=doc.id).first_or_404()
    else:
        version = doc.current_version

    # Get presigned URL for the PDF
    try:
        from r2_storage_helper import generate_presigned_url
        pdf_url = generate_presigned_url(version.storage_key, expiration=3600)
    except Exception:
        pdf_url = url_for('download_document', client_id=client_id, doc_id=doc.id,
                          version_id=version.id if version else None)

    return render_template('pdf_viewer.html', client=client, doc=doc,
                           version=version, pdf_url=pdf_url)


# ── Permit Tracking ──────────────────────────────────────────────────

@app.route('/clients/<int:client_id>/permits/new', methods=['GET', 'POST'])
@require_login
def create_permit(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'GET':
        return render_template('permit_form.html', client=client, permit=None,
                               permit_types=PERMIT_TYPES, permit_statuses=PERMIT_STATUSES)

    permit = Permit(
        client_id=client_id,
        permit_type=request.form.get('permit_type', 'Building Permit'),
        jurisdiction=request.form.get('jurisdiction', '').strip() or None,
        permit_number=request.form.get('permit_number', '').strip() or None,
        status=request.form.get('status', 'Not Started'),
        notes=request.form.get('notes', '').strip() or None,
        created_by_user_id=current_user.id,
    )

    # Parse dates
    for field in ('submitted_date', 'approved_date', 'issued_date',
                  'expiration_date', 'corrections_due_date'):
        val = request.form.get(field, '').strip()
        if val:
            try:
                setattr(permit, field, datetime.strptime(val, '%Y-%m-%d').date())
            except ValueError:
                pass

    fee = request.form.get('fee_amount', '').strip().replace(',', '').replace('$', '')
    if fee:
        try:
            permit.fee_amount = Decimal(fee)
        except (ValueError, InvalidOperation):
            pass
    permit.fee_paid = request.form.get('fee_paid') == 'on'
    permit.corrections_note = request.form.get('corrections_note', '').strip() or None

    db.session.add(permit)

    activity = ClientActivity(
        client_id=client_id,
        user_id=current_user.id,
        activity_type='Permit created',
        note_text=f'{permit.permit_type} — {permit.status}'
                  + (f' ({permit.jurisdiction})' if permit.jurisdiction else ''),
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'{permit.permit_type} permit created.', 'success')
    return redirect(url_for('client_documents', client_id=client_id))


@app.route('/clients/<int:client_id>/permits/<int:permit_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_permit(client_id, permit_id):
    client = Client.query.get_or_404(client_id)
    permit = Permit.query.filter_by(id=permit_id, client_id=client_id).first_or_404()

    if request.method == 'GET':
        return render_template('permit_form.html', client=client, permit=permit,
                               permit_types=PERMIT_TYPES, permit_statuses=PERMIT_STATUSES)

    old_status = permit.status
    permit.permit_type = request.form.get('permit_type', permit.permit_type)
    permit.jurisdiction = request.form.get('jurisdiction', '').strip() or None
    permit.permit_number = request.form.get('permit_number', '').strip() or None
    permit.status = request.form.get('status', permit.status)
    permit.notes = request.form.get('notes', '').strip() or None
    permit.corrections_note = request.form.get('corrections_note', '').strip() or None

    for field in ('submitted_date', 'approved_date', 'issued_date',
                  'expiration_date', 'corrections_due_date'):
        val = request.form.get(field, '').strip()
        if val:
            try:
                setattr(permit, field, datetime.strptime(val, '%Y-%m-%d').date())
            except ValueError:
                pass
        else:
            setattr(permit, field, None)

    fee = request.form.get('fee_amount', '').strip().replace(',', '').replace('$', '')
    if fee:
        try:
            permit.fee_amount = Decimal(fee)
        except (ValueError, InvalidOperation):
            pass
    else:
        permit.fee_amount = None
    permit.fee_paid = request.form.get('fee_paid') == 'on'

    if permit.status != old_status:
        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type='Permit status changed',
            note_text=f'{permit.permit_type}: {old_status} → {permit.status}',
            activity_date=datetime.now(timezone.utc),
        )
        db.session.add(activity)

    db.session.commit()
    flash(f'{permit.permit_type} permit updated.', 'success')
    return redirect(url_for('client_documents', client_id=client_id))


@app.route('/clients/<int:client_id>/permits/<int:permit_id>/delete', methods=['POST'])
@require_supervisor
def delete_permit(client_id, permit_id):
    permit = Permit.query.filter_by(id=permit_id, client_id=client_id).first_or_404()
    ptype = permit.permit_type
    db.session.delete(permit)
    db.session.commit()
    flash(f'{ptype} permit deleted.', 'success')
    return redirect(url_for('client_documents', client_id=client_id))


# ──────────────────────────────────────────────────────────────────────────────
# SCHEDULING
# ──────────────────────────────────────────────────────────────────────────────

def _notify_task(task, notif_type, actor, extra_msg=''):
    """Send in-app notification to task assignees (respecting preferences).

    notif_type: 'task_assigned' | 'task_changed'
    """
    pref_field = notif_type  # column name matches type
    for assignment in task.assignments:
        uid = assignment.user_id
        if not uid or uid == actor.id:
            continue
        prefs = NotificationPreference.query.filter_by(user_id=uid).first()
        if prefs and not getattr(prefs, pref_field, True):
            continue
        client = task.project.client
        title_map = {
            'task_assigned': f'New task: {task.name}',
            'task_changed': f'Task updated: {task.name}',
        }
        notif = Notification(
            user_id=uid,
            type=notif_type,
            title=title_map.get(notif_type, task.name),
            message=f'{client.name} — {extra_msg}' if extra_msg else client.name,
            link=url_for('project_schedule', project_id=task.project_id),
        )
        db.session.add(notif)


@app.route('/schedule/<int:project_id>')
@require_login
def project_schedule(project_id):
    project = Project.query.get_or_404(project_id)
    client = Client.query.get_or_404(project.client_id)
    phases = SchedulePhase.query.filter_by(project_id=project_id).order_by(SchedulePhase.sort_order).all()
    unphased_tasks = ScheduleTask.query.filter_by(project_id=project_id, phase_id=None).order_by(ScheduleTask.sort_order).all()
    all_tasks = ScheduleTask.query.filter_by(project_id=project_id).order_by(ScheduleTask.start_date).all()
    users = User.query.order_by(User.first_name).all()
    cost_codes = CostCode.query.filter_by(is_active=True, parent_id=None).order_by(CostCode.sort_order).all()

    # Build Gantt data
    gantt_tasks = []
    for t in all_tasks:
        if t.start_date and t.end_date:
            phase = t.phase
            gantt_tasks.append({
                'id': t.id,
                'name': t.name,
                'start': t.start_date.isoformat(),
                'end': t.end_date.isoformat(),
                'status': t.status,
                'phase': phase.name if phase else 'Unphased',
                'color': phase.color if phase else '#94a3b8',
                'assignees': ', '.join(t.assignee_names),
                'deps': [d.depends_on_id for d in t.predecessors],
            })

    view = request.args.get('view', 'gantt')
    return render_template('schedule.html',
                           project=project, client=client,
                           phases=phases, unphased_tasks=unphased_tasks,
                           all_tasks=all_tasks, gantt_tasks=gantt_tasks,
                           users=users, cost_codes=cost_codes,
                           task_statuses=TASK_STATUSES,
                           task_priorities=TASK_PRIORITIES,
                           view=view)


@app.route('/schedule/<int:project_id>/phases', methods=['POST'])
@require_login
def manage_phases(project_id):
    project = Project.query.get_or_404(project_id)
    action = request.form.get('action')

    if action == 'add':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '#6366f1').strip()
        if not name:
            flash('Phase name is required.', 'error')
            return redirect(url_for('project_schedule', project_id=project_id))
        max_order = db.session.query(func.max(SchedulePhase.sort_order)).filter_by(project_id=project_id).scalar() or 0
        phase = SchedulePhase(project_id=project_id, name=name, color=color, sort_order=max_order + 1)
        db.session.add(phase)
        db.session.commit()
        flash(f'Phase "{name}" added.', 'success')

    elif action == 'delete':
        phase_id = request.form.get('phase_id', type=int)
        phase = SchedulePhase.query.filter_by(id=phase_id, project_id=project_id).first_or_404()
        # Move tasks to unphased before deleting
        ScheduleTask.query.filter_by(phase_id=phase_id).update({'phase_id': None})
        db.session.delete(phase)
        db.session.commit()
        flash(f'Phase "{phase.name}" deleted. Tasks moved to unphased.', 'success')

    elif action == 'rename':
        phase_id = request.form.get('phase_id', type=int)
        new_name = request.form.get('name', '').strip()
        phase = SchedulePhase.query.filter_by(id=phase_id, project_id=project_id).first_or_404()
        if new_name:
            phase.name = new_name
            phase.color = request.form.get('color', phase.color).strip()
            db.session.commit()
            flash(f'Phase updated.', 'success')

    return redirect(url_for('project_schedule', project_id=project_id))


@app.route('/schedule/<int:project_id>/tasks/create', methods=['GET', 'POST'])
@require_login
def create_task(project_id):
    project = Project.query.get_or_404(project_id)
    client = Client.query.get_or_404(project.client_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Task name is required.', 'error')
            return redirect(url_for('create_task', project_id=project_id))

        phase_id = request.form.get('phase_id', type=int) or None
        cost_code_id = request.form.get('cost_code_id', type=int) or None
        start_date = request.form.get('start_date') or None
        end_date = request.form.get('end_date') or None

        max_order = db.session.query(func.max(ScheduleTask.sort_order)).filter_by(project_id=project_id).scalar() or 0
        task = ScheduleTask(
            project_id=project_id,
            phase_id=phase_id,
            cost_code_id=cost_code_id,
            name=name,
            description=request.form.get('description', '').strip() or None,
            start_date=date.fromisoformat(start_date) if start_date else None,
            end_date=date.fromisoformat(end_date) if end_date else None,
            status=request.form.get('status', 'Not Started'),
            priority=request.form.get('priority', 'Medium'),
            sort_order=max_order + 1,
            created_by_user_id=current_user.id,
        )
        db.session.add(task)
        db.session.flush()

        # Assignees
        _save_task_assignments(task, request.form)

        # Dependencies
        dep_ids = request.form.getlist('depends_on')
        for did in dep_ids:
            if did:
                dep = TaskDependency(task_id=task.id, depends_on_id=int(did))
                db.session.add(dep)

        db.session.flush()
        _notify_task(task, 'task_assigned', current_user)
        db.session.commit()
        flash(f'Task "{name}" created.', 'success')
        return redirect(url_for('project_schedule', project_id=project_id))

    phases = SchedulePhase.query.filter_by(project_id=project_id).order_by(SchedulePhase.sort_order).all()
    cost_codes = CostCode.query.filter_by(is_active=True, parent_id=None).order_by(CostCode.sort_order).all()
    users = User.query.order_by(User.first_name).all()
    existing_tasks = ScheduleTask.query.filter_by(project_id=project_id).order_by(ScheduleTask.name).all()

    return render_template('schedule_task_form.html',
                           project=project, client=client,
                           task=None, phases=phases,
                           cost_codes=cost_codes, users=users,
                           existing_tasks=existing_tasks,
                           task_statuses=TASK_STATUSES,
                           task_priorities=TASK_PRIORITIES)


@app.route('/schedule/<int:project_id>/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_task(project_id, task_id):
    project = Project.query.get_or_404(project_id)
    client = Client.query.get_or_404(project.client_id)
    task = ScheduleTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Task name is required.', 'error')
            return redirect(url_for('edit_task', project_id=project_id, task_id=task_id))

        old_status = task.status
        task.name = name
        task.phase_id = request.form.get('phase_id', type=int) or None
        task.cost_code_id = request.form.get('cost_code_id', type=int) or None
        task.description = request.form.get('description', '').strip() or None
        sd = request.form.get('start_date') or None
        ed = request.form.get('end_date') or None
        task.start_date = date.fromisoformat(sd) if sd else None
        task.end_date = date.fromisoformat(ed) if ed else None
        task.status = request.form.get('status', task.status)
        task.priority = request.form.get('priority', task.priority)

        # Rebuild assignments
        TaskAssignment.query.filter_by(task_id=task.id).delete()
        db.session.flush()
        _save_task_assignments(task, request.form)

        # Rebuild dependencies
        TaskDependency.query.filter_by(task_id=task.id).delete()
        dep_ids = request.form.getlist('depends_on')
        for did in dep_ids:
            if did and int(did) != task.id:
                dep = TaskDependency(task_id=task.id, depends_on_id=int(did))
                db.session.add(dep)

        db.session.flush()
        changes = []
        if task.status != old_status:
            changes.append(f'Status: {old_status} → {task.status}')
        _notify_task(task, 'task_changed', current_user, '; '.join(changes))
        db.session.commit()
        flash(f'Task "{name}" updated.', 'success')
        return redirect(url_for('project_schedule', project_id=project_id))

    phases = SchedulePhase.query.filter_by(project_id=project_id).order_by(SchedulePhase.sort_order).all()
    cost_codes = CostCode.query.filter_by(is_active=True, parent_id=None).order_by(CostCode.sort_order).all()
    users = User.query.order_by(User.first_name).all()
    existing_tasks = ScheduleTask.query.filter_by(project_id=project_id).filter(ScheduleTask.id != task_id).order_by(ScheduleTask.name).all()

    return render_template('schedule_task_form.html',
                           project=project, client=client,
                           task=task, phases=phases,
                           cost_codes=cost_codes, users=users,
                           existing_tasks=existing_tasks,
                           task_statuses=TASK_STATUSES,
                           task_priorities=TASK_PRIORITIES)


@app.route('/schedule/<int:project_id>/tasks/<int:task_id>/status', methods=['POST'])
@require_login
def update_task_status(project_id, task_id):
    task = ScheduleTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
    old_status = task.status
    new_status = request.form.get('status', task.status)
    if new_status in TASK_STATUSES:
        task.status = new_status
        if new_status != old_status:
            _notify_task(task, 'task_changed', current_user, f'Status: {old_status} → {new_status}')
        db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(ok=True, status=task.status)
    flash(f'Task status updated to {new_status}.', 'success')
    return redirect(url_for('project_schedule', project_id=project_id))


@app.route('/schedule/<int:project_id>/tasks/<int:task_id>/delete', methods=['POST'])
@require_login
def delete_task(project_id, task_id):
    task = ScheduleTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
    tname = task.name
    db.session.delete(task)
    db.session.commit()
    flash(f'Task "{tname}" deleted.', 'success')
    return redirect(url_for('project_schedule', project_id=project_id))


def _save_task_assignments(task, form):
    """Parse assignee fields from form and create TaskAssignment records."""
    user_ids = form.getlist('assignee_user_ids')
    sub_names = form.getlist('assignee_sub_names')
    roles = form.getlist('assignee_roles')

    for i in range(max(len(user_ids), len(sub_names))):
        uid = user_ids[i] if i < len(user_ids) else ''
        sname = sub_names[i].strip() if i < len(sub_names) else ''
        role = roles[i].strip() if i < len(roles) else ''
        if uid or sname:
            a = TaskAssignment(
                task_id=task.id,
                user_id=uid if uid else None,
                sub_name=sname if sname and not uid else None,
                role=role or None,
            )
            db.session.add(a)


# ── My Tasks (mobile "today / this week" view) ──────────────────────────────

@app.route('/my-tasks')
@require_login
def my_tasks():
    today = date.today()
    week_end = today + timedelta(days=(6 - today.weekday()))  # end of this week (Sun)

    # Tasks assigned to current user
    my_task_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=current_user.id).subquery()

    today_tasks = ScheduleTask.query.filter(
        ScheduleTask.id.in_(my_task_ids),
        ScheduleTask.start_date <= today,
        ScheduleTask.end_date >= today,
        ScheduleTask.status != 'Complete',
    ).order_by(ScheduleTask.priority.desc(), ScheduleTask.end_date).all()

    this_week_tasks = ScheduleTask.query.filter(
        ScheduleTask.id.in_(my_task_ids),
        ScheduleTask.start_date <= week_end,
        ScheduleTask.end_date >= today,
        ScheduleTask.status != 'Complete',
    ).order_by(ScheduleTask.start_date, ScheduleTask.priority.desc()).all()

    # Overdue
    overdue_tasks = ScheduleTask.query.filter(
        ScheduleTask.id.in_(my_task_ids),
        ScheduleTask.end_date < today,
        ScheduleTask.status.notin_(['Complete']),
    ).order_by(ScheduleTask.end_date).all()

    # Remove today duplicates from this_week
    today_ids = {t.id for t in today_tasks}
    this_week_tasks = [t for t in this_week_tasks if t.id not in today_ids]

    return render_template('my_tasks.html',
                           today_tasks=today_tasks,
                           this_week_tasks=this_week_tasks,
                           overdue_tasks=overdue_tasks,
                           today=today,
                           task_statuses=TASK_STATUSES)


# ── Notifications API ────────────────────────────────────────────────────────

@app.route('/api/notifications')
@require_login
def api_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify({
        'count': len(notifs),
        'items': [{
            'id': n.id,
            'type': n.type,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'created_at': n.created_at.isoformat() if n.created_at else None,
        } for n in notifs],
    })


@app.route('/api/notifications/mark-read', methods=['POST'])
@require_login
def mark_notifications_read():
    notif_ids = request.json.get('ids', []) if request.is_json else []
    if notif_ids:
        Notification.query.filter(
            Notification.id.in_(notif_ids),
            Notification.user_id == current_user.id,
        ).update({'is_read': True}, synchronize_session=False)
    else:
        # Mark all as read
        Notification.query.filter_by(user_id=current_user.id, is_read=False)\
            .update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return jsonify(ok=True)


@app.route('/settings/notifications', methods=['GET', 'POST'])
@require_login
def notification_settings():
    prefs = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=current_user.id)
        db.session.add(prefs)
        db.session.commit()

    if request.method == 'POST':
        prefs.task_assigned = 'task_assigned' in request.form
        prefs.task_changed = 'task_changed' in request.form
        prefs.task_reminder = 'task_reminder' in request.form
        db.session.commit()
        flash('Notification preferences saved.', 'success')
        return redirect(url_for('notification_settings'))

    return render_template('notification_settings.html', prefs=prefs)


# Inject unread notification count into all templates
@app.context_processor
def inject_notification_count():
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {'unread_notif_count': count}
    return {'unread_notif_count': 0}


# ──────────────────────────────────────────────────────────────────────────────
# DAILY LOGS
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/daily-logs')
@require_login
def daily_logs_list():
    """List daily logs across all clients, filterable."""
    client_id = request.args.get('client_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    q = DailyLog.query
    if client_id:
        q = q.filter_by(client_id=client_id)
    if date_from:
        q = q.filter(DailyLog.log_date >= date.fromisoformat(date_from))
    if date_to:
        q = q.filter(DailyLog.log_date <= date.fromisoformat(date_to))

    logs = q.order_by(DailyLog.log_date.desc(), DailyLog.created_at.desc()).limit(100).all()
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()

    return render_template('daily_logs_list.html',
                           logs=logs, clients=clients,
                           filter_client_id=client_id,
                           filter_date_from=date_from or '',
                           filter_date_to=date_to or '')


@app.route('/daily-logs/new', methods=['GET', 'POST'])
@app.route('/daily-logs/new/<int:client_id>', methods=['GET', 'POST'])
@require_login
def create_daily_log(client_id=None):
    if request.method == 'POST':
        cid = request.form.get('client_id', type=int)
        if not cid:
            flash('Client is required.', 'error')
            return redirect(url_for('create_daily_log'))

        client = Client.query.get_or_404(cid)
        log_date_str = request.form.get('log_date', '')
        try:
            log_date = date.fromisoformat(log_date_str) if log_date_str else date.today()
        except ValueError:
            log_date = date.today()

        # Check for duplicate
        existing = DailyLog.query.filter_by(
            client_id=cid, log_date=log_date,
            created_by_user_id=current_user.id).first()
        if existing:
            flash('A log already exists for this client/date. Editing it instead.', 'info')
            return redirect(url_for('edit_daily_log', log_id=existing.id))

        project = client.default_project()

        log = DailyLog(
            client_id=cid,
            project_id=project.id if project else None,
            log_date=log_date,
            created_by_user_id=current_user.id,
            client_uuid=request.form.get('client_uuid') or None,
        )
        _populate_daily_log(log, request.form)
        db.session.add(log)
        db.session.flush()

        # Also create a ClientActivity for timeline integration
        _create_log_activity(log, client)

        db.session.commit()
        flash('Daily log saved.', 'success')

        # Redirect back to edit for photo uploads
        return redirect(url_for('edit_daily_log', log_id=log.id))

    # GET
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    cost_codes = CostCode.query.filter_by(is_active=True, parent_id=None).order_by(CostCode.sort_order).all()
    preselected = Client.query.get(client_id) if client_id else None
    return render_template('daily_log_form.html',
                           log=None, clients=clients,
                           cost_codes=cost_codes,
                           preselected_client=preselected,
                           weather_conditions=WEATHER_CONDITIONS,
                           today=date.today())


@app.route('/daily-logs/<int:log_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_daily_log(log_id):
    log = DailyLog.query.get_or_404(log_id)
    client = Client.query.get_or_404(log.client_id)

    if request.method == 'POST':
        _populate_daily_log(log, request.form)
        db.session.commit()
        flash('Daily log updated.', 'success')
        return redirect(url_for('edit_daily_log', log_id=log.id))

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    cost_codes = CostCode.query.filter_by(is_active=True, parent_id=None).order_by(CostCode.sort_order).all()
    return render_template('daily_log_form.html',
                           log=log, client=client, clients=clients,
                           cost_codes=cost_codes,
                           preselected_client=client,
                           weather_conditions=WEATHER_CONDITIONS,
                           today=date.today())


@app.route('/daily-logs/<int:log_id>/delete', methods=['POST'])
@require_login
def delete_daily_log(log_id):
    log = DailyLog.query.get_or_404(log_id)
    # Clean up R2 photos
    from r2_storage_helper import delete_file as r2_delete
    for photo in log.photos:
        r2_delete(photo.storage_key)
    db.session.delete(log)
    db.session.commit()
    flash('Daily log deleted.', 'success')
    return redirect(url_for('daily_logs_list'))


@app.route('/daily-logs/<int:log_id>/finalize', methods=['POST'])
@require_login
def finalize_daily_log(log_id):
    log = DailyLog.query.get_or_404(log_id)
    log.status = 'Final'
    db.session.commit()
    flash('Daily log finalized.', 'success')
    return redirect(url_for('view_daily_log', log_id=log.id))


def _populate_daily_log(log, form):
    """Fill DailyLog fields from form data."""
    log.crew_count = form.get('crew_count', type=int) or None
    log.crew_names = form.get('crew_names', '').strip() or None
    hrs_reg = form.get('hours_regular', '').strip()
    hrs_ot = form.get('hours_overtime', '').strip()
    log.hours_regular = Decimal(hrs_reg) if hrs_reg else Decimal('0')
    log.hours_overtime = Decimal(hrs_ot) if hrs_ot else Decimal('0')
    log.work_completed = form.get('work_completed', '').strip() or None
    log.weather_condition = form.get('weather_condition', '').strip() or None
    temp = form.get('weather_temp_f', '').strip()
    log.weather_temp_f = int(temp) if temp else None
    log.weather_notes = form.get('weather_notes', '').strip() or None
    log.delays = form.get('delays', '').strip() or None
    log.safety_incidents = form.get('safety_incidents', '').strip() or None
    log.visitors = form.get('visitors', '').strip() or None
    log.materials_delivered = form.get('materials_delivered', '').strip() or None
    if form.get('status') in DAILY_LOG_STATUSES:
        log.status = form.get('status')


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


# ── Daily Log Photos ─────────────────────────────────────────────────────────

@app.route('/daily-logs/<int:log_id>/photos', methods=['POST'])
@require_login
def upload_daily_log_photo(log_id):
    """Upload photo(s) to a daily log. Returns JSON for AJAX."""
    import mimetypes
    from werkzeug.utils import secure_filename
    from r2_storage_helper import upload_file as r2_upload, build_client_prefix

    log = DailyLog.query.get_or_404(log_id)
    client = Client.query.get_or_404(log.client_id)

    if not client.storage_prefix:
        client.storage_prefix = build_client_prefix(client.name, client.address)
        db.session.flush()

    uploaded = []
    files = request.files.getlist('photos')
    captions = request.form.getlist('captions')
    cost_code_ids = request.form.getlist('cost_code_ids')

    for i, f in enumerate(files):
        if not f or not f.filename:
            continue
        filename = secure_filename(f.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'}:
            continue

        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        unique_name = f"log_{log.log_date.isoformat()}_{ts}_{i}_{filename}"
        key = f"{client.storage_prefix}/daily-logs/{unique_name}"
        mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

        r2_upload(f.read(), key, mime)

        caption = captions[i].strip() if i < len(captions) else ''
        cc_id = int(cost_code_ids[i]) if i < len(cost_code_ids) and cost_code_ids[i] else None

        photo = DailyLogPhoto(
            daily_log_id=log.id,
            client_id=client.id,
            cost_code_id=cc_id,
            storage_key=key,
            file_name=filename,
            caption=caption or None,
            sort_order=len(log.photos) + i,
            uploaded_by_user_id=current_user.id,
        )
        db.session.add(photo)
        db.session.flush()
        uploaded.append({'id': photo.id, 'file_name': filename, 'caption': caption})

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(ok=True, photos=uploaded)
    flash(f'{len(uploaded)} photo(s) uploaded.', 'success')
    return redirect(url_for('edit_daily_log', log_id=log.id))


@app.route('/daily-logs/photos/<int:photo_id>')
@require_login
def view_daily_log_photo(photo_id):
    from flask import send_file
    from r2_storage_helper import download_file
    photo = DailyLogPhoto.query.get_or_404(photo_id)
    import mimetypes
    mime = mimetypes.guess_type(photo.file_name)[0] or 'image/jpeg'
    content = download_file(photo.storage_key)
    return send_file(
        BytesIO(content),
        mimetype=mime,
        download_name=photo.file_name,
    )


@app.route('/daily-logs/photos/<int:photo_id>/delete', methods=['POST'])
@require_login
def delete_daily_log_photo(photo_id):
    from r2_storage_helper import delete_file as r2_delete
    photo = DailyLogPhoto.query.get_or_404(photo_id)
    log_id = photo.daily_log_id
    r2_delete(photo.storage_key)
    db.session.delete(photo)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(ok=True)
    flash('Photo deleted.', 'success')
    return redirect(url_for('edit_daily_log', log_id=log_id))


# ── Daily Log View (read-only) ──────────────────────────────────────────────

@app.route('/daily-logs/<int:log_id>')
@require_login
def view_daily_log(log_id):
    log = DailyLog.query.get_or_404(log_id)
    client = Client.query.get_or_404(log.client_id)
    return render_template('daily_log_view.html', log=log, client=client)


# ── Weather Auto-Fetch ───────────────────────────────────────────────────────

@app.route('/api/weather')
@require_login
def api_weather():
    """Fetch weather for a client's address on a given date using Open-Meteo (free, no key)."""
    import requests as http_requests

    client_id = request.args.get('client_id', type=int)
    log_date = request.args.get('date', '')

    if not client_id:
        return jsonify(ok=False, error='client_id required')

    client = Client.query.get(client_id)
    if not client or not client.address:
        return jsonify(ok=False, error='Client has no address')

    # Geocode address via Nominatim (free, no key)
    geo_url = 'https://nominatim.openstreetmap.org/search'
    try:
        geo_resp = http_requests.get(geo_url, params={
            'q': client.address, 'format': 'json', 'limit': 1,
        }, headers={'User-Agent': 'ADUPortal/1.0'}, timeout=5)
        geo_data = geo_resp.json()
        if not geo_data:
            return jsonify(ok=False, error='Could not geocode address')
        lat = float(geo_data[0]['lat'])
        lon = float(geo_data[0]['lon'])
    except Exception:
        return jsonify(ok=False, error='Geocoding failed')

    # Fetch weather from Open-Meteo
    try:
        target = log_date or date.today().isoformat()
        weather_url = 'https://api.open-meteo.com/v1/forecast'
        w_resp = http_requests.get(weather_url, params={
            'latitude': lat, 'longitude': lon,
            'daily': 'temperature_2m_max,temperature_2m_min,weathercode',
            'temperature_unit': 'fahrenheit',
            'start_date': target, 'end_date': target,
            'timezone': 'America/Los_Angeles',
        }, timeout=5)
        w_data = w_resp.json()

        daily = w_data.get('daily', {})
        if not daily.get('temperature_2m_max'):
            return jsonify(ok=False, error='No weather data for date')

        hi = round(daily['temperature_2m_max'][0])
        lo = round(daily['temperature_2m_min'][0])
        code = daily.get('weathercode', [0])[0]

        # WMO weather code → condition text
        wmo_map = {
            0: 'Clear', 1: 'Partly Cloudy', 2: 'Partly Cloudy', 3: 'Cloudy',
            45: 'Fog', 48: 'Fog',
            51: 'Rain', 53: 'Rain', 55: 'Rain',
            61: 'Rain', 63: 'Rain', 65: 'Heavy Rain',
            71: 'Snow', 73: 'Snow', 75: 'Snow',
            80: 'Rain', 81: 'Rain', 82: 'Heavy Rain',
            95: 'Heavy Rain', 96: 'Heavy Rain', 99: 'Heavy Rain',
        }
        condition = wmo_map.get(code, 'Clear')

        return jsonify(ok=True, condition=condition, temp_hi=hi, temp_lo=lo,
                       notes=f"{condition}, Hi {hi}F / Lo {lo}F")
    except Exception:
        return jsonify(ok=False, error='Weather fetch failed')


# ── Offline Sync API ─────────────────────────────────────────────────────────

@app.route('/api/daily-logs/sync', methods=['POST'])
@require_login
@csrf.exempt
def sync_daily_logs():
    """Accept queued daily logs from offline-capable clients.

    Expects JSON array of log objects with client_uuid for dedup.
    """
    if not request.is_json:
        return jsonify(ok=False, error='JSON required'), 400

    entries = request.json if isinstance(request.json, list) else [request.json]
    results = []

    for entry in entries:
        client_uuid = entry.get('client_uuid')
        if not client_uuid:
            results.append({'client_uuid': None, 'status': 'error', 'error': 'missing client_uuid'})
            continue

        # Dedup by client_uuid
        existing = DailyLog.query.filter_by(client_uuid=client_uuid).first()
        if existing:
            results.append({'client_uuid': client_uuid, 'status': 'duplicate', 'id': existing.id})
            continue

        cid = entry.get('client_id')
        if not cid:
            results.append({'client_uuid': client_uuid, 'status': 'error', 'error': 'missing client_id'})
            continue

        client = Client.query.get(cid)
        if not client:
            results.append({'client_uuid': client_uuid, 'status': 'error', 'error': 'client not found'})
            continue

        try:
            log_date = date.fromisoformat(entry.get('log_date', date.today().isoformat()))
        except ValueError:
            log_date = date.today()

        project = client.default_project()
        log = DailyLog(
            client_id=cid,
            project_id=project.id if project else None,
            log_date=log_date,
            created_by_user_id=current_user.id,
            client_uuid=client_uuid,
        )
        # Populate fields from entry dict
        log.crew_count = entry.get('crew_count')
        log.crew_names = entry.get('crew_names')
        log.hours_regular = Decimal(str(entry.get('hours_regular', 0)))
        log.hours_overtime = Decimal(str(entry.get('hours_overtime', 0)))
        log.work_completed = entry.get('work_completed')
        log.weather_condition = entry.get('weather_condition')
        log.weather_temp_f = entry.get('weather_temp_f')
        log.weather_notes = entry.get('weather_notes')
        log.delays = entry.get('delays')
        log.safety_incidents = entry.get('safety_incidents')
        log.visitors = entry.get('visitors')
        log.materials_delivered = entry.get('materials_delivered')
        log.status = entry.get('status', 'Draft')

        db.session.add(log)
        db.session.flush()
        _create_log_activity(log, client)
        results.append({'client_uuid': client_uuid, 'status': 'created', 'id': log.id})

    db.session.commit()
    return jsonify(ok=True, results=results)


# ── PDF Generation ───────────────────────────────────────────────────────────

@app.route('/daily-logs/<int:log_id>/pdf')
@require_login
def daily_log_pdf(log_id):
    """Generate a PDF for a single daily log."""
    log = DailyLog.query.get_or_404(log_id)
    client = Client.query.get_or_404(log.client_id)
    pdf_bytes = _generate_daily_log_pdf([log], client,
                                        title=f"Daily Log — {log.log_date.strftime('%m/%d/%Y')}")
    return Response(pdf_bytes, mimetype='application/pdf',
                    headers={'Content-Disposition':
                             f'inline; filename="daily-log-{client.name}-{log.log_date.isoformat()}.pdf"'})


@app.route('/daily-logs/weekly-pdf')
@require_login
def weekly_log_pdf():
    """Generate a weekly summary PDF for a client."""
    client_id = request.args.get('client_id', type=int)
    if not client_id:
        flash('Client is required.', 'error')
        return redirect(url_for('daily_logs_list'))

    client = Client.query.get_or_404(client_id)
    week_of = request.args.get('week_of', '')
    try:
        ref = date.fromisoformat(week_of) if week_of else date.today()
    except ValueError:
        ref = date.today()

    # Monday to Sunday of that week
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)

    logs = DailyLog.query.filter(
        DailyLog.client_id == client_id,
        DailyLog.log_date >= monday,
        DailyLog.log_date <= sunday,
    ).order_by(DailyLog.log_date).all()

    if not logs:
        flash('No logs found for that week.', 'warning')
        return redirect(url_for('daily_logs_list', client_id=client_id))

    title = f"Weekly Report — {monday.strftime('%m/%d')} to {sunday.strftime('%m/%d/%Y')}"
    pdf_bytes = _generate_daily_log_pdf(logs, client, title=title)
    return Response(pdf_bytes, mimetype='application/pdf',
                    headers={'Content-Disposition':
                             f'inline; filename="weekly-log-{client.name}-{monday.isoformat()}.pdf"'})


def _generate_daily_log_pdf(logs, client, title='Daily Log'):
    """Build a PDF from one or more DailyLog records using fpdf2."""
    from fpdf import FPDF
    from r2_storage_helper import download_file
    import tempfile, os

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_font('Helvetica', size=10)

    for log in logs:
        pdf.add_page()

        # Header
        pdf.set_font('Helvetica', 'B', 16)
        pdf.cell(0, 10, 'All Inclusive ADU', ln=True, align='C')
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, title, ln=True, align='C')
        pdf.ln(4)

        # Client info bar
        pdf.set_fill_color(241, 245, 249)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(95, 7, f'Client: {client.name}', fill=True)
        pdf.cell(95, 7, f'Date: {log.log_date.strftime("%m/%d/%Y")}', fill=True, align='R', ln=True)
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(95, 6, f'Address: {client.address or "N/A"}')
        pdf.cell(95, 6, f'Status: {log.status}', align='R', ln=True)
        pdf.ln(4)

        # Section helper
        def section(label, value):
            if not value:
                return
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_fill_color(241, 245, 249)
            pdf.cell(0, 6, label, fill=True, ln=True)
            pdf.set_font('Helvetica', '', 9)
            pdf.multi_cell(0, 5, str(value))
            pdf.ln(2)

        # Weather
        weather_parts = []
        if log.weather_condition:
            weather_parts.append(log.weather_condition)
        if log.weather_temp_f is not None:
            weather_parts.append(f'{log.weather_temp_f}°F')
        if log.weather_notes:
            weather_parts.append(log.weather_notes)
        section('Weather', ' — '.join(weather_parts) if weather_parts else None)

        # Crew
        crew_parts = []
        if log.crew_count:
            crew_parts.append(f'{log.crew_count} on site')
        if log.crew_names:
            crew_parts.append(log.crew_names)
        section('Crew', ' | '.join(crew_parts) if crew_parts else None)

        # Hours
        if log.hours_regular or log.hours_overtime:
            section('Hours', f'Regular: {log.hours_regular or 0}  |  OT: {log.hours_overtime or 0}  |  Total: {log.total_hours}')

        section('Work Completed', log.work_completed)
        section('Materials Delivered', log.materials_delivered)
        section('Delays / Issues', log.delays)
        section('Safety Incidents', log.safety_incidents)
        section('Visitors / Inspections', log.visitors)

        # Photos
        if log.photos:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_fill_color(241, 245, 249)
            pdf.cell(0, 6, f'Photos ({len(log.photos)})', fill=True, ln=True)
            pdf.ln(2)

            for photo in log.photos:
                try:
                    img_bytes = download_file(photo.storage_key)
                    ext = photo.file_name.rsplit('.', 1)[-1].lower() if '.' in photo.file_name else 'jpg'
                    if ext in ('jpg', 'jpeg', 'png', 'gif'):
                        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                            tmp.write(img_bytes)
                            tmp_path = tmp.name
                        try:
                            # Check if enough space for image
                            if pdf.get_y() > 200:
                                pdf.add_page()
                            pdf.image(tmp_path, w=80)
                        finally:
                            os.unlink(tmp_path)
                except Exception:
                    pdf.set_font('Helvetica', 'I', 8)
                    pdf.cell(0, 5, f'[Could not load: {photo.file_name}]', ln=True)

                if photo.caption:
                    pdf.set_font('Helvetica', 'I', 8)
                    pdf.cell(0, 5, photo.caption, ln=True)
                if photo.cost_code:
                    pdf.set_font('Helvetica', '', 7)
                    pdf.cell(0, 4, f'Cost Code: {photo.cost_code.code} {photo.cost_code.name}', ln=True)
                pdf.ln(3)

        # Footer
        pdf.set_font('Helvetica', 'I', 7)
        pdf.cell(0, 5, f'Generated {datetime.now(timezone.utc).strftime("%m/%d/%Y %I:%M %p")} UTC  |  Logged by {log.created_by.display_name}',
                 ln=True, align='C')

    return pdf.output()


# ── Share token for client portal PDF ────────────────────────────────────────

@app.route('/daily-logs/<int:log_id>/share')
@require_login
def share_daily_log(log_id):
    """Generate a share link. Uses log_id + simple HMAC token."""
    import hashlib, hmac
    log = DailyLog.query.get_or_404(log_id)
    secret = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    token = hmac.new(secret, f'dailylog-{log.id}'.encode(), hashlib.sha256).hexdigest()[:16]
    share_url = url_for('public_daily_log', log_id=log.id, token=token, _external=True)
    return jsonify(ok=True, url=share_url)


@app.route('/dl/<int:log_id>/<token>')
@csrf.exempt
def public_daily_log(log_id, token):
    """Public view of a daily log PDF (no auth, token-protected)."""
    import hashlib, hmac
    log = DailyLog.query.get_or_404(log_id)
    secret = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    expected = hmac.new(secret, f'dailylog-{log.id}'.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(token, expected):
        abort(403)
    client = Client.query.get_or_404(log.client_id)
    pdf_bytes = _generate_daily_log_pdf([log], client,
                                        title=f"Daily Log — {log.log_date.strftime('%m/%d/%Y')}")
    return Response(pdf_bytes, mimetype='application/pdf',
                    headers={'Content-Disposition':
                             f'inline; filename="daily-log-{log.log_date.isoformat()}.pdf"'})


# ═══════════════════════════════════════════════════════════════════════════════
#  CHANGE ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/change-orders')
@require_login
def change_orders_list():
    """List change orders, optionally filtered."""
    filter_client_id = request.args.get('client_id', type=int)
    filter_status = request.args.get('status', '')
    show_unbilled = request.args.get('unbilled', '') == '1'

    q = ChangeOrder.query.options(
        joinedload(ChangeOrder.client),
        joinedload(ChangeOrder.project),
    )
    if filter_client_id:
        q = q.filter(ChangeOrder.client_id == filter_client_id)
    if filter_status:
        q = q.filter(ChangeOrder.status == filter_status)
    if show_unbilled:
        q = q.filter(ChangeOrder.status == 'Approved', ChangeOrder.billed.is_(False))

    cos = q.order_by(ChangeOrder.created_at.desc()).limit(200).all()
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()

    return render_template('change_orders_list.html',
                           change_orders=cos, clients=clients,
                           filter_client_id=filter_client_id,
                           filter_status=filter_status,
                           show_unbilled=show_unbilled,
                           statuses=CHANGE_ORDER_STATUSES)


@app.route('/change-orders/new', methods=['GET', 'POST'])
@app.route('/change-orders/new/<int:client_id>', methods=['GET', 'POST'])
@require_login
def create_change_order(client_id=None):
    if request.method == 'POST':
        return _save_change_order(None)

    client = Client.query.get(client_id) if client_id else None
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()

    # Generate next CO number for selected client
    next_number = _next_co_number(client_id) if client_id else 'CO-001'

    return render_template('change_order_form.html',
                           co=None, client=client, clients=clients,
                           cost_codes=cost_codes, cost_types=COST_TYPES,
                           next_number=next_number)


@app.route('/change-orders/<int:co_id>', methods=['GET'])
@require_login
def view_change_order(co_id):
    co = ChangeOrder.query.get_or_404(co_id)
    return render_template('change_order_view.html', co=co)


@app.route('/change-orders/<int:co_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_change_order(co_id):
    co = ChangeOrder.query.get_or_404(co_id)
    if request.method == 'POST':
        return _save_change_order(co)

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()
    return render_template('change_order_form.html',
                           co=co, client=co.client, clients=clients,
                           cost_codes=cost_codes, cost_types=COST_TYPES,
                           next_number=co.co_number)


def _next_co_number(client_id):
    """Generate next CO number for a client: CO-001, CO-002, etc."""
    count = ChangeOrder.query.filter_by(client_id=client_id).count()
    return f'CO-{count + 1:03d}'


def _save_change_order(co):
    """Create or update a change order from form POST."""
    client_id = request.form.get('client_id', type=int)
    if not client_id:
        flash('Client is required.', 'error')
        return redirect(request.url)

    client = Client.query.get_or_404(client_id)
    project = client.default_project()

    title = request.form.get('title', '').strip()
    if not title:
        flash('Title is required.', 'error')
        return redirect(request.url)

    is_new = co is None
    if is_new:
        co = ChangeOrder(
            client_id=client_id,
            project_id=project.id,
            co_number=request.form.get('co_number', _next_co_number(client_id)).strip(),
            created_by_user_id=current_user.id,
        )
        db.session.add(co)

    co.title = title
    co.description = request.form.get('description', '').strip() or None

    try:
        co.price_to_client = Decimal(request.form.get('price_to_client', '0'))
    except (InvalidOperation, ValueError):
        co.price_to_client = Decimal('0')

    # Handle line items
    if not is_new:
        ChangeOrderItem.query.filter_by(change_order_id=co.id).delete()
        db.session.flush()

    descriptions = request.form.getlist('item_description')
    amounts = request.form.getlist('item_amount')
    cost_code_ids = request.form.getlist('item_cost_code_id')
    cost_types = request.form.getlist('item_cost_type')

    for i, desc in enumerate(descriptions):
        desc = desc.strip()
        if not desc:
            continue
        try:
            amt = Decimal(amounts[i]) if i < len(amounts) else Decimal('0')
        except (InvalidOperation, ValueError):
            amt = Decimal('0')
        cc_id = int(cost_code_ids[i]) if i < len(cost_code_ids) and cost_code_ids[i] else None
        ct = cost_types[i] if i < len(cost_types) and cost_types[i] else 'Other'

        item = ChangeOrderItem(
            change_order_id=co.id if co.id else None,
            cost_code_id=cc_id,
            cost_type=ct,
            description=desc,
            amount=amt,
            sort_order=i,
        )
        if co.id:
            item.change_order_id = co.id
            db.session.add(item)
        else:
            co.items.append(item)

    db.session.commit()

    if is_new:
        activity = ClientActivity(
            client_id=client_id,
            user_id=current_user.id,
            activity_type='Change Order Created',
            note_text=f'{co.co_number}: {co.title} — ${co.price_to_client:,.2f}',
            activity_date=datetime.now(timezone.utc),
        )
        db.session.add(activity)
        db.session.commit()

    flash(f'Change order {co.co_number} {"created" if is_new else "updated"}.', 'success')
    return redirect(url_for('view_change_order', co_id=co.id))


@app.route('/change-orders/<int:co_id>/send', methods=['POST'])
@require_login
def send_change_order(co_id):
    """Mark CO as Sent and generate share token."""
    co = ChangeOrder.query.get_or_404(co_id)
    if co.status not in ('Draft',):
        flash('Only draft change orders can be sent.', 'error')
        return redirect(url_for('view_change_order', co_id=co.id))

    co.status = 'Sent'
    if not co.share_token:
        co.share_token = _generate_token()

    activity = ClientActivity(
        client_id=co.client_id,
        user_id=current_user.id,
        activity_type='Change Order Sent',
        note_text=f'{co.co_number}: {co.title}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'Change order {co.co_number} sent. Share link generated.', 'success')
    return redirect(url_for('view_change_order', co_id=co.id))


@app.route('/change-orders/<int:co_id>/approve-internal', methods=['POST'])
@require_login
def approve_change_order_internal(co_id):
    """Internal approval (supervisor approves on behalf of client)."""
    co = ChangeOrder.query.get_or_404(co_id)
    if co.status not in ('Draft', 'Sent'):
        flash('This change order cannot be approved.', 'error')
        return redirect(url_for('view_change_order', co_id=co.id))

    _apply_change_order_approval(co, approved_name=current_user.display_name,
                                  approved_ip=request.remote_addr)

    flash(f'Change order {co.co_number} approved. Budget and contract value updated.', 'success')
    return redirect(url_for('view_change_order', co_id=co.id))


@app.route('/change-orders/<int:co_id>/reject', methods=['POST'])
@require_login
def reject_change_order(co_id):
    co = ChangeOrder.query.get_or_404(co_id)
    co.status = 'Rejected'

    activity = ClientActivity(
        client_id=co.client_id,
        user_id=current_user.id,
        activity_type='Change Order Rejected',
        note_text=f'{co.co_number}: {co.title}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'Change order {co.co_number} rejected.', 'info')
    return redirect(url_for('view_change_order', co_id=co.id))


@app.route('/change-orders/<int:co_id>/mark-billed', methods=['POST'])
@require_login
def mark_change_order_billed(co_id):
    co = ChangeOrder.query.get_or_404(co_id)
    if co.status != 'Approved':
        flash('Only approved change orders can be billed.', 'error')
        return redirect(url_for('view_change_order', co_id=co.id))

    co.billed = True
    co.billed_at = datetime.now(timezone.utc)

    activity = ClientActivity(
        client_id=co.client_id,
        user_id=current_user.id,
        activity_type='Change Order Billed',
        note_text=f'{co.co_number}: ${co.price_to_client:,.2f}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'Change order {co.co_number} marked as billed.', 'success')
    return redirect(url_for('view_change_order', co_id=co.id))


def _apply_change_order_approval(co, approved_name=None, approved_email=None,
                                  approved_ip=None, signature_data=None):
    """Apply approval: update budget, contract value, log activity."""
    now = datetime.now(timezone.utc)
    co.status = 'Approved'
    co.approved_at = now
    co.approved_name = approved_name
    co.approved_email = approved_email
    co.approved_ip = approved_ip
    if signature_data:
        co.signature_data = signature_data

    project = co.project
    client = co.client

    # Add CO items to budget (additive — add to existing amounts)
    for item in co.items.all():
        if not item.cost_code_id:
            continue
        existing = Budget.query.filter_by(
            project_id=project.id,
            cost_code_id=item.cost_code_id,
            cost_type=item.cost_type,
        ).first()
        if existing:
            existing.amount += item.amount
            existing.notes = (existing.notes or '') + f' +CO#{co.co_number}'
        else:
            db.session.add(Budget(
                project_id=project.id,
                cost_code_id=item.cost_code_id,
                cost_type=item.cost_type,
                amount=item.amount,
                notes=f'From CO#{co.co_number}',
            ))

    # Adjust contract values
    if project.contract_value:
        project.contract_value += co.price_to_client
    else:
        project.contract_value = co.price_to_client

    if client.final_contract_value:
        client.final_contract_value += co.price_to_client
    else:
        client.final_contract_value = co.price_to_client

    # Log activity
    activity = ClientActivity(
        client_id=co.client_id,
        user_id=co.created_by_user_id,
        activity_type='Change Order Approved',
        note_text=f'{co.co_number}: {co.title} — ${co.price_to_client:,.2f} '
                  f'(approved by {approved_name or "internal"})',
        activity_date=now,
    )
    db.session.add(activity)
    db.session.commit()


# ── Public Change Order Portal ──────────────────────────────────────────────

@app.route('/co/<token>', methods=['GET', 'POST'])
@csrf.exempt
def public_change_order(token):
    """Public approval page for a change order."""
    co = ChangeOrder.query.filter_by(share_token=token).first_or_404()

    if request.method == 'POST' and co.status == 'Sent':
        signed_name = request.form.get('name', '').strip()
        signed_email = request.form.get('email', '').strip()
        sig_data = request.form.get('signature_data', '').strip()

        if not signed_name:
            flash('Name is required to approve.', 'error')
            return redirect(url_for('public_change_order', token=token))

        _apply_change_order_approval(
            co,
            approved_name=signed_name,
            approved_email=signed_email,
            approved_ip=request.remote_addr,
            signature_data=sig_data or None,
        )

        flash('Change order approved! Thank you.', 'success')
        return redirect(url_for('public_change_order', token=token))

    return render_template('change_order_public.html', co=co)


@app.route('/change-orders/<int:co_id>/share-link')
@require_login
def change_order_share_link(co_id):
    """Get or generate the share link for a change order."""
    co = ChangeOrder.query.get_or_404(co_id)
    if not co.share_token:
        co.share_token = _generate_token()
        db.session.commit()
    url = url_for('public_change_order', token=co.share_token, _external=True)
    return jsonify(ok=True, url=url)


# ── Billing / Invoicing ──────────────────────────────────────────────

def _next_invoice_number(contract):
    count = Invoice.query.filter_by(contract_id=contract.id).count()
    return f"{contract.contract_number}-INV-{count + 1:03d}"


def _get_stripe():
    """Return configured stripe module or None."""
    import os
    key = os.environ.get('STRIPE_SECRET_KEY')
    if not key:
        return None
    import stripe
    stripe.api_key = key
    return stripe


@app.route('/contracts/<int:contract_id>/billing')
@require_login
def contract_billing(contract_id):
    """Billing hub for a contract — invoices, payments, draw progress."""
    contract = Contract.query.get_or_404(contract_id)
    draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()
    invoices = contract.invoices.order_by(Invoice.created_at.desc()).all()

    # Approved, unbilled change orders
    unbilled_cos = ChangeOrder.query.filter(
        ChangeOrder.client_id == contract.client_id,
        ChangeOrder.status == 'Approved',
        ChangeOrder.billed == False,
    ).order_by(ChangeOrder.co_number).all()

    # Calculate draw progress: how much of each draw has been invoiced
    draw_invoiced = {}
    for draw in draws:
        billed = db.session.query(func.sum(InvoiceLineItem.amount)).filter(
            InvoiceLineItem.draw_item_id == draw.id,
        ).scalar() or Decimal('0')
        draw_invoiced[draw.id] = billed

    # Overall billing summary
    total_invoiced = sum((inv.subtotal for inv in invoices), Decimal('0'))
    total_paid = sum((inv.amount_paid for inv in invoices), Decimal('0'))
    total_retainage = sum((inv.retainage_amount for inv in invoices), Decimal('0'))
    co_total = sum((co.price_to_client for co in contract.client.change_orders.filter_by(
        status='Approved').all()), Decimal('0'))
    adjusted_contract = contract.total_price + co_total

    return render_template('billing_hub.html',
        contract=contract, draws=draws, invoices=invoices,
        unbilled_cos=unbilled_cos, draw_invoiced=draw_invoiced,
        total_invoiced=total_invoiced, total_paid=total_paid,
        total_retainage=total_retainage, co_total=co_total,
        adjusted_contract=adjusted_contract)


@app.route('/contracts/<int:contract_id>/invoices/new', methods=['GET', 'POST'])
@require_login
def create_invoice(contract_id):
    """Create a new draw invoice."""
    contract = Contract.query.get_or_404(contract_id)
    draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()

    # Calculate what's already been billed per draw
    draw_billed = {}
    for draw in draws:
        billed = db.session.query(func.sum(InvoiceLineItem.amount)).filter(
            InvoiceLineItem.draw_item_id == draw.id,
        ).scalar() or Decimal('0')
        draw_billed[draw.id] = billed

    unbilled_cos = ChangeOrder.query.filter(
        ChangeOrder.client_id == contract.client_id,
        ChangeOrder.status == 'Approved',
        ChangeOrder.billed == False,
    ).order_by(ChangeOrder.co_number).all()

    if request.method == 'GET':
        return render_template('invoice_create.html',
            contract=contract, draws=draws, draw_billed=draw_billed,
            unbilled_cos=unbilled_cos,
            invoice_number=_next_invoice_number(contract),
            retainage_pct=contract.retainage_pct)

    # POST — create invoice
    invoice = Invoice(
        contract_id=contract.id,
        client_id=contract.client_id,
        invoice_number=request.form.get('invoice_number', _next_invoice_number(contract)).strip(),
        share_token=_generate_token(),
        retainage_pct=Decimal(request.form.get('retainage_pct', '0').replace('%', '') or '0'),
        notes=request.form.get('notes', '').strip() or None,
        created_by_user_id=current_user.id,
    )

    due_date = request.form.get('due_date', '').strip()
    if due_date:
        try:
            invoice.due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.add(invoice)
    db.session.flush()

    sort = 0
    # Add draw lines
    for draw in draws:
        field_name = f'draw_{draw.id}_amount'
        amt_str = request.form.get(field_name, '0').strip().replace(',', '').replace('$', '')
        try:
            amt = Decimal(amt_str)
        except (InvalidOperation, ValueError):
            amt = Decimal('0')
        if amt <= 0:
            continue

        pct_field = f'draw_{draw.id}_pct'
        pct_str = request.form.get(pct_field, '').strip().replace('%', '')
        pct = None
        if pct_str:
            try:
                pct = Decimal(pct_str)
            except (InvalidOperation, ValueError):
                pass

        sort += 10
        db.session.add(InvoiceLineItem(
            invoice_id=invoice.id,
            source_type='draw',
            draw_item_id=draw.id,
            description=draw.milestone,
            amount=amt,
            pct_complete=pct,
            sort_order=sort,
        ))

    # Add change order lines
    co_ids = request.form.getlist('co_ids')
    for co_id_str in co_ids:
        try:
            co_id = int(co_id_str)
        except ValueError:
            continue
        co = ChangeOrder.query.get(co_id)
        if not co or co.billed:
            continue
        sort += 10
        db.session.add(InvoiceLineItem(
            invoice_id=invoice.id,
            source_type='change_order',
            change_order_id=co.id,
            description=f'CO #{co.co_number}: {co.title}',
            amount=co.price_to_client,
            sort_order=sort,
        ))
        co.billed = True
        co.billed_at = datetime.now(timezone.utc)

    invoice.recalculate()

    activity = ClientActivity(
        client_id=contract.client_id,
        user_id=current_user.id,
        activity_type='Invoice created',
        note_text=f'Invoice {invoice.invoice_number} for ${invoice.total_due:,.2f}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'Invoice {invoice.invoice_number} created for ${invoice.total_due:,.2f}.', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


@app.route('/invoices/<int:invoice_id>')
@require_login
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    contract = invoice.contract
    line_items = invoice.line_items.all()
    payments = invoice.payments.all()
    has_stripe = bool(_get_stripe())
    return render_template('invoice_view.html', invoice=invoice,
                           contract=contract, line_items=line_items,
                           payments=payments, has_stripe=has_stripe,
                           today_str=date.today().strftime('%Y-%m-%d'))


@app.route('/invoices/<int:invoice_id>/send', methods=['POST'])
@require_login
def send_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.status == 'Draft':
        invoice.status = 'Sent'
        invoice.issued_date = date.today()
        if not invoice.due_date:
            invoice.due_date = date.today() + timedelta(days=30)

        # Create Stripe payment link if configured
        stripe = _get_stripe()
        if stripe and not invoice.stripe_payment_intent_id:
            try:
                session = stripe.checkout.Session.create(
                    mode='payment',
                    line_items=[{
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': f'Invoice {invoice.invoice_number}',
                                'description': f'{invoice.contract.contract_number} — {invoice.contract.client.name}',
                            },
                            'unit_amount': int(invoice.balance_due * 100),
                        },
                        'quantity': 1,
                    }],
                    payment_intent_data={
                        'metadata': {
                            'invoice_id': str(invoice.id),
                            'invoice_number': invoice.invoice_number,
                        },
                    },
                    success_url=url_for('public_invoice', token=invoice.share_token, _external=True) + '?paid=1',
                    cancel_url=url_for('public_invoice', token=invoice.share_token, _external=True),
                    metadata={
                        'invoice_id': str(invoice.id),
                    },
                )
                invoice.stripe_payment_url = session.url
                invoice.stripe_payment_intent_id = session.payment_intent
            except Exception as e:
                current_app.logger.error(f'Stripe session creation failed: {e}')

        activity = ClientActivity(
            client_id=invoice.client_id,
            user_id=current_user.id,
            activity_type='Invoice sent',
            note_text=f'Invoice {invoice.invoice_number} sent — ${invoice.total_due:,.2f}',
            activity_date=datetime.now(timezone.utc),
        )
        db.session.add(activity)
        db.session.commit()
        flash('Invoice marked as sent.', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


@app.route('/invoices/<int:invoice_id>/void', methods=['POST'])
@require_login
def void_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.status not in ('Paid',):
        # Un-bill any change orders
        for li in invoice.line_items.filter_by(source_type='change_order').all():
            if li.change_order_id:
                co = ChangeOrder.query.get(li.change_order_id)
                if co:
                    co.billed = False
                    co.billed_at = None
        invoice.status = 'Voided'
        db.session.commit()
        flash('Invoice voided.', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


@app.route('/invoices/<int:invoice_id>/record-payment', methods=['POST'])
@require_login
def record_payment(invoice_id):
    """Manually record a payment (check, wire, cash, etc.)."""
    invoice = Invoice.query.get_or_404(invoice_id)

    amt_str = request.form.get('amount', '0').strip().replace(',', '').replace('$', '')
    try:
        amount = Decimal(amt_str)
    except (InvalidOperation, ValueError):
        flash('Invalid amount.', 'error')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

    if amount <= 0:
        flash('Amount must be positive.', 'error')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

    method = request.form.get('method', 'other')
    if method not in PAYMENT_METHODS:
        method = 'other'

    received_date = None
    rd = request.form.get('received_date', '').strip()
    if rd:
        try:
            received_date = datetime.strptime(rd, '%Y-%m-%d').date()
        except ValueError:
            received_date = date.today()
    else:
        received_date = date.today()

    payment = Payment(
        invoice_id=invoice.id,
        client_id=invoice.client_id,
        amount=amount,
        method=method,
        status='succeeded',
        reference=request.form.get('reference', '').strip() or None,
        is_deposit=request.form.get('is_deposit') == 'on',
        received_date=received_date,
        note=request.form.get('note', '').strip() or None,
        recorded_by_user_id=current_user.id,
    )
    db.session.add(payment)

    invoice.recalculate()

    # Mark draw items as paid if fully billed
    for li in invoice.line_items.filter_by(source_type='draw').all():
        if li.draw_item_id and invoice.status == 'Paid':
            draw = DrawScheduleItem.query.get(li.draw_item_id)
            if draw and not draw.paid_at:
                draw.paid_at = datetime.now(timezone.utc)
                draw.paid_amount = (draw.paid_amount or Decimal('0')) + amount

    activity = ClientActivity(
        client_id=invoice.client_id,
        user_id=current_user.id,
        activity_type='Payment received',
        note_text=f'${amount:,.2f} {method} payment on Invoice {invoice.invoice_number}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()

    flash(f'Payment of ${amount:,.2f} recorded.', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


# ── Public Invoice + Stripe ──────────────────────────────────────────

@app.route('/inv/<token>')
def public_invoice(token):
    """Client-facing invoice view with optional Stripe payment."""
    invoice = Invoice.query.filter_by(share_token=token).first_or_404()
    if invoice.status == 'Draft':
        abort(404)  # Don't show unsent invoices
    line_items = invoice.line_items.all()
    contract = invoice.contract
    paid_success = request.args.get('paid') == '1'
    return render_template('invoice_public.html', invoice=invoice,
                           contract=contract, line_items=line_items,
                           token=token, paid_success=paid_success)


@app.route('/stripe/webhook', methods=['POST'])
@csrf.exempt
def stripe_webhook():
    """Handle Stripe webhooks for payment confirmation."""
    import os
    stripe = _get_stripe()
    if not stripe:
        abort(400)

    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError):
            abort(400)
    else:
        event = stripe.Event.construct_from(
            request.get_json(), stripe.api_key
        )

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        invoice_id = session.get('metadata', {}).get('invoice_id')
        if invoice_id:
            invoice = Invoice.query.get(int(invoice_id))
            if invoice:
                payment = Payment(
                    invoice_id=invoice.id,
                    client_id=invoice.client_id,
                    amount=Decimal(str(session['amount_total'] / 100)),
                    method='stripe',
                    status='succeeded',
                    stripe_payment_intent_id=session.get('payment_intent'),
                    received_date=date.today(),
                    note='Online payment via Stripe',
                )
                db.session.add(payment)
                invoice.recalculate()

                activity = ClientActivity(
                    client_id=invoice.client_id,
                    user_id=invoice.created_by_user_id,
                    activity_type='Online payment received',
                    note_text=f'Stripe payment ${payment.amount:,.2f} on Invoice {invoice.invoice_number}',
                    activity_date=datetime.now(timezone.utc),
                )
                db.session.add(activity)
                db.session.commit()

    elif event['type'] == 'charge.refunded':
        charge = event['data']['object']
        pi_id = charge.get('payment_intent')
        if pi_id:
            payment = Payment.query.filter_by(stripe_payment_intent_id=pi_id).first()
            if payment:
                payment.status = 'refunded'
                payment.invoice.recalculate()
                db.session.commit()

    return jsonify(received=True), 200


# ═══════════════════════════════════════════════════════════════════════════════
#  QUICKBOOKS ONLINE — TWO-WAY SYNC
# ═══════════════════════════════════════════════════════════════════════════════

def _get_qbo_client():
    """Build a QBOClient from the stored token, or return None."""
    tok = QBOToken.query.first()
    if not tok:
        return None

    def _on_refreshed(data):
        tok.access_token = data['access_token']
        tok.refresh_token = data['refresh_token']
        tok.access_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=data.get('expires_in', 3600))
        db.session.commit()

    return qbo_helper.QBOClient(
        realm_id=tok.realm_id,
        access_token=tok.access_token,
        refresh_tok=tok.refresh_token,
        token_expires_at=tok.access_token_expires_at.replace(
            tzinfo=timezone.utc).timestamp() if tok.access_token_expires_at else 0,
        on_token_refreshed=_on_refreshed,
    )


def _get_or_create_mapping(entity_type, local_id):
    m = QBOMapping.query.filter_by(entity_type=entity_type, local_id=str(local_id)).first()
    if not m:
        m = QBOMapping(entity_type=entity_type, local_id=str(local_id))
        db.session.add(m)
        db.session.flush()
    return m


def _log_sync(direction, entity_type, entity_id, qbo_id, action, status, detail=None):
    entry = QBOSyncLog(
        direction=direction, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        qbo_id=str(qbo_id) if qbo_id else None,
        action=action, status=status, detail=detail,
    )
    db.session.add(entry)
    return entry


# ── OAuth Connect ───────────────────────────────────────────────────────

@app.route('/settings/qbo/connect')
@require_supervisor
def qbo_connect():
    """Redirect to Intuit OAuth 2.0 consent page."""
    if not qbo_helper.is_configured():
        flash('QBO credentials not configured. Set QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REDIRECT_URI.', 'error')
        return redirect(url_for('integrations_settings'))
    import secrets
    state = secrets.token_urlsafe(16)
    session['qbo_oauth_state'] = state
    return redirect(qbo_helper.auth_url(state))


@app.route('/settings/qbo/callback')
@require_supervisor
def qbo_callback():
    """Handle the OAuth 2.0 callback from Intuit."""
    error = request.args.get('error')
    if error:
        flash(f'QBO authorization failed: {error}', 'error')
        return redirect(url_for('integrations_settings'))

    state = request.args.get('state', '')
    if state != session.pop('qbo_oauth_state', ''):
        flash('Invalid OAuth state. Try again.', 'error')
        return redirect(url_for('integrations_settings'))

    code = request.args.get('code')
    realm_id = request.args.get('realmId')
    if not code or not realm_id:
        flash('Missing authorization code.', 'error')
        return redirect(url_for('integrations_settings'))

    try:
        data = qbo_helper.exchange_code(code)
    except Exception as e:
        flash(f'Token exchange failed: {e}', 'error')
        return redirect(url_for('integrations_settings'))

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=data.get('expires_in', 3600))
    refresh_expires = now + timedelta(days=100)  # QBO refresh tokens last ~100 days

    # Upsert the token (only one row)
    tok = QBOToken.query.first()
    if tok:
        tok.realm_id = realm_id
        tok.access_token = data['access_token']
        tok.refresh_token = data['refresh_token']
        tok.access_token_expires_at = expires_at
        tok.refresh_token_expires_at = refresh_expires
        tok.connected_at = now
    else:
        tok = QBOToken(
            realm_id=realm_id,
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            access_token_expires_at=expires_at,
            refresh_token_expires_at=refresh_expires,
            connected_at=now,
        )
        db.session.add(tok)

    # Fetch company name
    try:
        client = _get_qbo_client()
        if not client:
            # Token was just added, create client manually
            client = qbo_helper.QBOClient(
                realm_id=realm_id,
                access_token=data['access_token'],
                refresh_tok=data['refresh_token'],
                token_expires_at=expires_at.timestamp(),
            )
        info = client.company_info()
        tok.company_name = info.get('CompanyName', 'Connected')
    except Exception:
        tok.company_name = 'Connected'

    db.session.commit()
    flash(f'QuickBooks Online connected: {tok.company_name}', 'success')
    return redirect(url_for('integrations_settings'))


@app.route('/settings/qbo/disconnect', methods=['POST'])
@require_supervisor
def qbo_disconnect():
    """Remove QBO tokens (disconnect)."""
    QBOToken.query.delete()
    db.session.commit()
    flash('QuickBooks Online disconnected.', 'info')
    return redirect(url_for('integrations_settings'))


# ── Cost Code → QBO Account/Item Mapping ────────────────────────────────

@app.route('/settings/qbo/mappings')
@require_supervisor
def qbo_mappings():
    """Configure cost code → QBO account/item mappings."""
    client = _get_qbo_client()
    if not client:
        flash('Connect to QuickBooks first.', 'error')
        return redirect(url_for('integrations_settings'))

    cost_codes = CostCode.query.filter_by(is_active=True).order_by(CostCode.sort_order, CostCode.code).all()

    # Current mappings
    cc_mappings = {}
    for cc in cost_codes:
        m = QBOMapping.query.filter_by(entity_type='cost_code', local_id=str(cc.id)).first()
        cc_mappings[cc.id] = m

    # Fetch QBO accounts and items
    try:
        qbo_income_accounts = client.get_accounts('Income')
        qbo_expense_accounts = client.get_accounts('Expense')
        qbo_items = client.get_items()
    except Exception as e:
        flash(f'Failed to fetch QBO data: {e}', 'error')
        qbo_income_accounts = []
        qbo_expense_accounts = []
        qbo_items = []

    return render_template('qbo_mappings.html',
                           cost_codes=cost_codes, cc_mappings=cc_mappings,
                           qbo_income_accounts=qbo_income_accounts,
                           qbo_expense_accounts=qbo_expense_accounts,
                           qbo_items=qbo_items)


@app.route('/settings/qbo/mappings/save', methods=['POST'])
@require_supervisor
def qbo_mappings_save():
    """Save cost code → QBO item mappings."""
    cost_codes = CostCode.query.filter_by(is_active=True).all()
    for cc in cost_codes:
        qbo_item_id = request.form.get(f'cc_{cc.id}_item_id', '').strip()
        qbo_item_name = request.form.get(f'cc_{cc.id}_item_name', '').strip()
        if qbo_item_id:
            m = _get_or_create_mapping('cost_code', cc.id)
            m.qbo_id = qbo_item_id
            m.qbo_name = qbo_item_name or None
        else:
            # Remove mapping if cleared
            existing = QBOMapping.query.filter_by(entity_type='cost_code', local_id=str(cc.id)).first()
            if existing:
                db.session.delete(existing)
    db.session.commit()
    flash('QBO mappings saved.', 'success')
    return redirect(url_for('qbo_mappings'))


# ── Sync Engine ─────────────────────────────────────────────────────────

def _push_customer(client_obj, qbo_client):
    """Push a Client → QBO Customer.  Idempotent."""
    m = _get_or_create_mapping('customer', client_obj.id)

    if m.qbo_id:
        # Already synced — update
        try:
            existing = qbo_client.get_customer(m.qbo_id)
            qbo_cust = qbo_client.update_customer(
                m.qbo_id, existing['SyncToken'],
                DisplayName=client_obj.name,
                PrimaryEmailAddr={'Address': client_obj.email} if client_obj.email else None,
                PrimaryPhone={'FreeFormNumber': client_obj.phone} if client_obj.phone else None,
            )
            m.qbo_sync_token = qbo_cust['SyncToken']
            m.qbo_name = qbo_cust['DisplayName']
            m.last_synced_at = datetime.now(timezone.utc)
            _log_sync('push', 'customer', client_obj.id, m.qbo_id, 'update', 'success')
            return m
        except Exception as e:
            _log_sync('push', 'customer', client_obj.id, m.qbo_id, 'update', 'error', str(e))
            raise

    # Check if customer already exists by name (prevent duplicates)
    try:
        existing = qbo_client.find_customer_by_name(client_obj.name)
        if existing:
            m.qbo_id = str(existing['Id'])
            m.qbo_sync_token = existing.get('SyncToken')
            m.qbo_name = existing['DisplayName']
            m.last_synced_at = datetime.now(timezone.utc)
            _log_sync('push', 'customer', client_obj.id, m.qbo_id, 'skip', 'success',
                       'Already exists in QBO')
            return m
    except Exception:
        pass

    # Create new
    try:
        addr_parts = (client_obj.address or '').split(',')
        qbo_cust = qbo_client.create_customer(
            display_name=client_obj.name,
            email=client_obj.email,
            phone=client_obj.phone,
            address_line=addr_parts[0].strip() if addr_parts else None,
        )
        m.qbo_id = str(qbo_cust['Id'])
        m.qbo_sync_token = qbo_cust.get('SyncToken')
        m.qbo_name = qbo_cust['DisplayName']
        m.last_synced_at = datetime.now(timezone.utc)
        _log_sync('push', 'customer', client_obj.id, m.qbo_id, 'create', 'success')
        return m
    except Exception as e:
        _log_sync('push', 'customer', client_obj.id, None, 'create', 'error', str(e))
        raise


def _push_invoice(invoice_obj, qbo_client):
    """Push an Invoice → QBO Invoice.  Idempotent."""
    m = _get_or_create_mapping('invoice', invoice_obj.id)

    if m.qbo_id:
        _log_sync('push', 'invoice', invoice_obj.id, m.qbo_id, 'skip', 'skipped',
                   'Already synced')
        return m

    # Ensure customer is synced
    cust_mapping = _get_or_create_mapping('customer', invoice_obj.client_id)
    if not cust_mapping.qbo_id:
        client_obj = Client.query.get(invoice_obj.client_id)
        _push_customer(client_obj, qbo_client)
        cust_mapping = QBOMapping.query.filter_by(
            entity_type='customer', local_id=str(invoice_obj.client_id)).first()

    if not cust_mapping or not cust_mapping.qbo_id:
        _log_sync('push', 'invoice', invoice_obj.id, None, 'create', 'error',
                   'Customer not synced to QBO')
        raise ValueError('Customer not synced to QBO')

    # Build line items
    lines = []
    for li in invoice_obj.line_items.all():
        line = {'description': li.description, 'amount': li.amount}
        # Check for cost code → QBO item mapping
        if li.source_type == 'draw' and li.draw_item_id:
            pass  # Use description as-is
        if li.source_type == 'change_order' and li.change_order_id:
            co = li.change_order
            if co:
                for co_item in co.items.all():
                    if co_item.cost_code_id:
                        cc_map = QBOMapping.query.filter_by(
                            entity_type='cost_code', local_id=str(co_item.cost_code_id)).first()
                        if cc_map and cc_map.qbo_id:
                            line['item_id'] = cc_map.qbo_id
                            break
        lines.append(line)

    try:
        qbo_inv = qbo_client.create_invoice(
            customer_id=cust_mapping.qbo_id,
            line_items=lines,
            doc_number=invoice_obj.invoice_number,
            due_date=invoice_obj.due_date.isoformat() if invoice_obj.due_date else None,
            txn_date=invoice_obj.issued_date.isoformat() if invoice_obj.issued_date else None,
            memo=invoice_obj.notes,
        )
        m.qbo_id = str(qbo_inv['Id'])
        m.qbo_sync_token = qbo_inv.get('SyncToken')
        m.last_synced_at = datetime.now(timezone.utc)
        _log_sync('push', 'invoice', invoice_obj.id, m.qbo_id, 'create', 'success')
        return m
    except Exception as e:
        _log_sync('push', 'invoice', invoice_obj.id, None, 'create', 'error', str(e))
        raise


def _push_payment(payment_obj, qbo_client):
    """Push a Payment → QBO Payment.  Idempotent."""
    m = _get_or_create_mapping('payment', payment_obj.id)

    if m.qbo_id:
        _log_sync('push', 'payment', payment_obj.id, m.qbo_id, 'skip', 'skipped',
                   'Already synced')
        return m

    # Ensure invoice is synced
    inv_mapping = QBOMapping.query.filter_by(
        entity_type='invoice', local_id=str(payment_obj.invoice_id)).first()
    invoice_qbo_id = inv_mapping.qbo_id if inv_mapping else None

    # Ensure customer is synced
    cust_mapping = QBOMapping.query.filter_by(
        entity_type='customer', local_id=str(payment_obj.client_id)).first()
    if not cust_mapping or not cust_mapping.qbo_id:
        _log_sync('push', 'payment', payment_obj.id, None, 'create', 'error',
                   'Customer not synced to QBO')
        raise ValueError('Customer not synced to QBO')

    try:
        qbo_pmt = qbo_client.create_payment(
            customer_id=cust_mapping.qbo_id,
            amount=payment_obj.amount,
            invoice_qbo_id=invoice_qbo_id,
            txn_date=payment_obj.received_date.isoformat() if payment_obj.received_date else None,
            memo=payment_obj.note or f'{payment_obj.method} payment',
        )
        m.qbo_id = str(qbo_pmt['Id'])
        m.qbo_sync_token = qbo_pmt.get('SyncToken')
        m.last_synced_at = datetime.now(timezone.utc)
        _log_sync('push', 'payment', payment_obj.id, m.qbo_id, 'create', 'success')
        return m
    except Exception as e:
        _log_sync('push', 'payment', payment_obj.id, None, 'create', 'error', str(e))
        raise


def _pull_payments(qbo_client, since_date=None):
    """Pull payments from QBO → local.  Match by invoice mapping."""
    if not since_date:
        last = AppSetting.get('qbo_last_pull_payments')
        since_date = last or '2020-01-01'

    pulled = 0
    try:
        qbo_payments = qbo_client.get_payments_since(since_date)
    except Exception as e:
        _log_sync('pull', 'payment', None, None, 'fetch', 'error', str(e))
        return 0

    for qbo_pmt in qbo_payments:
        qbo_id = str(qbo_pmt['Id'])
        # Already mapped?
        existing_map = QBOMapping.query.filter_by(entity_type='payment', qbo_id=qbo_id).first()
        if existing_map:
            continue  # Already linked

        # Find linked invoice
        invoice_id = None
        for line in qbo_pmt.get('Line', []):
            for txn in line.get('LinkedTxn', []):
                if txn.get('TxnType') == 'Invoice':
                    inv_qbo_id = txn['TxnId']
                    inv_map = QBOMapping.query.filter_by(
                        entity_type='invoice', qbo_id=str(inv_qbo_id)).first()
                    if inv_map:
                        invoice_id = int(inv_map.local_id)

        if not invoice_id:
            _log_sync('pull', 'payment', None, qbo_id, 'skip', 'skipped',
                       'No matching local invoice')
            continue

        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            continue

        # Check if we already have this payment
        existing_pmt = Payment.query.filter_by(
            invoice_id=invoice_id,
            stripe_payment_intent_id=f'qbo:{qbo_id}',  # Use this field as dedup key
        ).first()
        if existing_pmt:
            continue

        amount = Decimal(str(qbo_pmt.get('TotalAmt', 0)))
        txn_date = qbo_pmt.get('TxnDate')
        received = None
        if txn_date:
            try:
                received = datetime.strptime(txn_date, '%Y-%m-%d').date()
            except ValueError:
                received = date.today()

        payment = Payment(
            invoice_id=invoice_id,
            client_id=invoice.client_id,
            amount=amount,
            method='other',
            status='succeeded',
            reference=f'QBO Payment #{qbo_id}',
            stripe_payment_intent_id=f'qbo:{qbo_id}',
            received_date=received or date.today(),
            note='Synced from QuickBooks',
        )
        db.session.add(payment)
        invoice.recalculate()

        # Create mapping
        m = QBOMapping(entity_type='payment', local_id=str(payment.id), qbo_id=qbo_id)
        db.session.add(m)

        _log_sync('pull', 'payment', payment.id, qbo_id, 'create', 'success')
        pulled += 1

    AppSetting.set('qbo_last_pull_payments', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'))
    db.session.commit()
    return pulled


def _pull_customers(qbo_client, since_date=None):
    """Pull new/updated customers from QBO.  Creates local Clients only for
    customers that don't already have a mapping (no overwrite)."""
    if not since_date:
        last = AppSetting.get('qbo_last_pull_customers')
        since_date = last or '2020-01-01'

    pulled = 0
    try:
        qbo_custs = qbo_client.get_customers_since(since_date)
    except Exception as e:
        _log_sync('pull', 'customer', None, None, 'fetch', 'error', str(e))
        return 0

    for qbo_cust in qbo_custs:
        qbo_id = str(qbo_cust['Id'])
        existing_map = QBOMapping.query.filter_by(entity_type='customer', qbo_id=qbo_id).first()
        if existing_map:
            # Update name if changed
            local_client = Client.query.get(int(existing_map.local_id))
            if local_client:
                display = qbo_cust.get('DisplayName', '')
                if display and display != local_client.name:
                    local_client.name = display
                    existing_map.qbo_name = display
                    _log_sync('pull', 'customer', local_client.id, qbo_id, 'update', 'success')
            continue

        # New customer from QBO — create a local Client
        name = qbo_cust.get('DisplayName', qbo_cust.get('CompanyName', 'QBO Customer'))
        email = None
        if qbo_cust.get('PrimaryEmailAddr'):
            email = qbo_cust['PrimaryEmailAddr'].get('Address')
        phone = None
        if qbo_cust.get('PrimaryPhone'):
            phone = qbo_cust['PrimaryPhone'].get('FreeFormNumber')
        address = ''
        if qbo_cust.get('BillAddr'):
            addr = qbo_cust['BillAddr']
            parts = [addr.get('Line1', ''), addr.get('City', ''),
                     addr.get('CountrySubDivisionCode', ''), addr.get('PostalCode', '')]
            address = ', '.join(p for p in parts if p)

        new_client = Client(
            name=name,
            address=address or 'Imported from QBO',
            email=email,
            phone=phone,
            status='Lead',
        )
        db.session.add(new_client)
        db.session.flush()

        m = QBOMapping(entity_type='customer', local_id=str(new_client.id),
                        qbo_id=qbo_id, qbo_name=name,
                        last_synced_at=datetime.now(timezone.utc))
        db.session.add(m)
        _log_sync('pull', 'customer', new_client.id, qbo_id, 'create', 'success')
        pulled += 1

    AppSetting.set('qbo_last_pull_customers', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'))
    db.session.commit()
    return pulled


# ── Sync Trigger Routes ─────────────────────────────────────────────────

@app.route('/settings/qbo/sync', methods=['POST'])
@require_supervisor
def qbo_sync_all():
    """Run a full two-way sync."""
    qbo = _get_qbo_client()
    if not qbo:
        flash('QuickBooks not connected.', 'error')
        return redirect(url_for('integrations_settings'))

    results = {'push_customers': 0, 'push_invoices': 0, 'push_payments': 0,
               'pull_customers': 0, 'pull_payments': 0, 'errors': []}

    # 1. Push customers (all active clients)
    for client_obj in Client.query.filter_by(is_active=True).all():
        try:
            _push_customer(client_obj, qbo)
            results['push_customers'] += 1
        except Exception as e:
            results['errors'].append(f'Customer {client_obj.name}: {e}')

    # 2. Push invoices (Sent, Partial, Paid — skip Draft/Voided)
    for inv in Invoice.query.filter(Invoice.status.in_(['Sent', 'Viewed', 'Partial', 'Paid', 'Overdue'])).all():
        try:
            _push_invoice(inv, qbo)
            results['push_invoices'] += 1
        except Exception as e:
            results['errors'].append(f'Invoice {inv.invoice_number}: {e}')

    # 3. Push payments
    for pmt in Payment.query.filter_by(status='succeeded').all():
        try:
            _push_payment(pmt, qbo)
            results['push_payments'] += 1
        except Exception as e:
            results['errors'].append(f'Payment #{pmt.id}: {e}')

    # 4. Pull customers from QBO
    try:
        results['pull_customers'] = _pull_customers(qbo)
    except Exception as e:
        results['errors'].append(f'Pull customers: {e}')

    # 5. Pull payments from QBO
    try:
        results['pull_payments'] = _pull_payments(qbo)
    except Exception as e:
        results['errors'].append(f'Pull payments: {e}')

    db.session.commit()

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    AppSetting.set('qbo_last_sync', now_str)
    summary = (f"Push: {results['push_customers']} customers, {results['push_invoices']} invoices, "
               f"{results['push_payments']} payments. "
               f"Pull: {results['pull_customers']} customers, {results['pull_payments']} payments.")
    if results['errors']:
        summary += f" Errors: {len(results['errors'])}"
    AppSetting.set('qbo_sync_result', summary)
    AppSetting.set('qbo_sync_success', 'false' if results['errors'] else 'true')

    if results['errors']:
        flash(f'Sync completed with {len(results["errors"])} error(s). {summary}', 'warning')
    else:
        flash(f'Sync completed. {summary}', 'success')

    return redirect(url_for('qbo_sync_dashboard'))


@app.route('/settings/qbo/sync/customers', methods=['POST'])
@require_supervisor
def qbo_sync_customers():
    """Push all active clients to QBO."""
    qbo = _get_qbo_client()
    if not qbo:
        flash('QuickBooks not connected.', 'error')
        return redirect(url_for('integrations_settings'))

    count = 0
    errors = 0
    for client_obj in Client.query.filter_by(is_active=True).all():
        try:
            _push_customer(client_obj, qbo)
            count += 1
        except Exception:
            errors += 1
    db.session.commit()
    flash(f'Synced {count} customers to QBO. {errors} error(s).' if errors
          else f'Synced {count} customers to QBO.', 'success' if not errors else 'warning')
    return redirect(url_for('qbo_sync_dashboard'))


@app.route('/settings/qbo/sync/invoices', methods=['POST'])
@require_supervisor
def qbo_sync_invoices():
    """Push all non-draft invoices to QBO."""
    qbo = _get_qbo_client()
    if not qbo:
        flash('QuickBooks not connected.', 'error')
        return redirect(url_for('integrations_settings'))

    count = 0
    errors = 0
    for inv in Invoice.query.filter(Invoice.status.in_(['Sent', 'Viewed', 'Partial', 'Paid', 'Overdue'])).all():
        try:
            _push_invoice(inv, qbo)
            count += 1
        except Exception:
            errors += 1
    db.session.commit()
    flash(f'Synced {count} invoices to QBO. {errors} error(s).' if errors
          else f'Synced {count} invoices to QBO.', 'success' if not errors else 'warning')
    return redirect(url_for('qbo_sync_dashboard'))


@app.route('/settings/qbo/sync/pull-payments', methods=['POST'])
@require_supervisor
def qbo_pull_payments():
    """Pull new payments from QBO into local."""
    qbo = _get_qbo_client()
    if not qbo:
        flash('QuickBooks not connected.', 'error')
        return redirect(url_for('integrations_settings'))

    try:
        count = _pull_payments(qbo)
        flash(f'Pulled {count} new payment(s) from QBO.', 'success')
    except Exception as e:
        flash(f'Failed to pull payments: {e}', 'error')
    return redirect(url_for('qbo_sync_dashboard'))


# ── Sync Dashboard ──────────────────────────────────────────────────────

@app.route('/settings/qbo/dashboard')
@require_supervisor
def qbo_sync_dashboard():
    """Sync status dashboard with log history."""
    tok = QBOToken.query.first()
    connected = tok is not None

    # Mapping counts
    mapping_counts = {}
    for etype in ['customer', 'invoice', 'payment', 'cost_code']:
        mapping_counts[etype] = QBOMapping.query.filter_by(entity_type=etype).filter(
            QBOMapping.qbo_id.isnot(None)).count()

    # Recent logs
    recent_logs = QBOSyncLog.query.order_by(QBOSyncLog.created_at.desc()).limit(100).all()

    # Error summary
    error_count = QBOSyncLog.query.filter_by(status='error').count()
    recent_errors = QBOSyncLog.query.filter_by(status='error').order_by(
        QBOSyncLog.created_at.desc()).limit(20).all()

    # Unsynced counts
    synced_client_ids = {int(m.local_id) for m in QBOMapping.query.filter_by(entity_type='customer').filter(
        QBOMapping.qbo_id.isnot(None)).all()}
    unsynced_clients = Client.query.filter_by(is_active=True).filter(
        ~Client.id.in_(synced_client_ids) if synced_client_ids else Client.id.isnot(None)
    ).count()

    synced_inv_ids = {int(m.local_id) for m in QBOMapping.query.filter_by(entity_type='invoice').filter(
        QBOMapping.qbo_id.isnot(None)).all()}
    unsynced_invoices = Invoice.query.filter(
        Invoice.status.in_(['Sent', 'Viewed', 'Partial', 'Paid', 'Overdue']),
        ~Invoice.id.in_(synced_inv_ids) if synced_inv_ids else Invoice.id.isnot(None)
    ).count()

    return render_template('qbo_dashboard.html',
                           connected=connected, token=tok,
                           mapping_counts=mapping_counts,
                           recent_logs=recent_logs,
                           error_count=error_count,
                           recent_errors=recent_errors,
                           unsynced_clients=unsynced_clients,
                           unsynced_invoices=unsynced_invoices,
                           last_sync=AppSetting.get('qbo_last_sync'),
                           last_sync_result=AppSetting.get('qbo_sync_result'),
                           last_sync_success=AppSetting.get('qbo_sync_success') == 'true')


# ═══════════════════════════════════════════════════════════════════════════════
#  STAFF: CLIENT PORTAL USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/clients/<int:client_id>/portal-users', methods=['POST'])
@require_supervisor
def add_portal_user(client_id):
    """Create a ClientUser for the client portal."""
    client = Client.query.get_or_404(client_id)
    email = request.form.get('email', '').strip().lower()
    name = request.form.get('name', '').strip()
    if not email:
        flash('Email is required.', 'error')
        return redirect(url_for('view_client', client_id=client_id))

    existing = ClientUser.query.filter_by(email=email).first()
    if existing:
        flash(f'{email} already has portal access.', 'error')
        return redirect(url_for('view_client', client_id=client_id))

    cu = ClientUser(client_id=client.id, email=email, name=name or client.contact_name)
    db.session.add(cu)
    db.session.commit()
    flash(f'Portal access created for {email}.', 'success')
    return redirect(url_for('view_client', client_id=client_id))


@app.route('/clients/<int:client_id>/portal-users/<int:cu_id>/delete', methods=['POST'])
@require_supervisor
def remove_portal_user(client_id, cu_id):
    cu = ClientUser.query.get_or_404(cu_id)
    if cu.client_id != client_id:
        abort(403)
    cu.is_active = False
    db.session.commit()
    flash(f'Portal access revoked for {cu.email}.', 'info')
    return redirect(url_for('view_client', client_id=client_id))


@app.route('/clients/<int:client_id>/portal-message', methods=['POST'])
@require_login
def send_portal_message(client_id):
    """Staff sends a message to client via portal."""
    client = Client.query.get_or_404(client_id)
    text = request.form.get('message', '').strip()
    if not text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('view_client', client_id=client_id))

    msg = PortalMessage(
        client_id=client.id,
        sender_type='staff',
        sender_name=current_user.display_name,
        message=text,
    )
    db.session.add(msg)
    db.session.commit()
    flash('Message sent to client portal.', 'success')
    return redirect(url_for('view_client', client_id=client_id))


@app.route('/clients/<int:client_id>/selections/<int:sel_id>/approve', methods=['POST'])
@require_login
def approve_selection(client_id, sel_id):
    """Approve a client's selection — optionally create a change order for price delta."""
    sel = ClientSelection.query.get_or_404(sel_id)
    if sel.client_id != client_id:
        abort(403)

    sel.status = 'Approved'
    sel.approved_at = datetime.now(timezone.utc)

    option = sel.option
    if option.price_delta and option.price_delta != 0:
        # Auto-create a change order for the price delta
        from client_portal import _current_client_user  # not used here but keep import clean
        project = sel.client.default_project()
        co_number = f'CO-SEL-{sel.id:03d}'
        co = ChangeOrder(
            client_id=client_id,
            project_id=project.id,
            co_number=co_number,
            title=f'Selection: {sel.category.name} — {option.name}',
            description=f'Price adjustment for {sel.category.name} selection: {option.name}',
            price_to_client=option.price_delta,
            status='Approved',
            approved_at=datetime.now(timezone.utc),
            approved_name='Auto-approved via selection',
            created_by_user_id=current_user.id,
        )
        db.session.add(co)
        db.session.flush()
        sel.change_order_id = co.id

        # Apply budget/contract value adjustment (reuse the approval helper)
        from routes import _apply_change_order_approval
        # Budget + contract value already handled inline since CO is created as Approved
        if option.cost_code_id:
            from models import Budget
            existing = Budget.query.filter_by(
                project_id=project.id, cost_code_id=option.cost_code_id,
                cost_type='Material').first()
            if existing:
                existing.amount += option.price_delta
            else:
                db.session.add(Budget(
                    project_id=project.id, cost_code_id=option.cost_code_id,
                    cost_type='Material', amount=option.price_delta,
                    notes=f'Selection: {option.name}',
                ))
        if project.contract_value:
            project.contract_value += option.price_delta
        else:
            project.contract_value = option.price_delta
        client_obj = Client.query.get(client_id)
        if client_obj.final_contract_value:
            client_obj.final_contract_value += option.price_delta
        else:
            client_obj.final_contract_value = option.price_delta

    activity = ClientActivity(
        client_id=client_id,
        user_id=current_user.id,
        activity_type='Selection Approved',
        note_text=f'{sel.category.name}: {option.name}',
        activity_date=datetime.now(timezone.utc),
    )
    db.session.add(activity)
    db.session.commit()
    flash(f'Selection approved: {sel.category.name} — {option.name}', 'success')
    return redirect(url_for('view_client', client_id=client_id))


@app.route('/clients/<int:client_id>/selections/<int:sel_id>/reject', methods=['POST'])
@require_login
def reject_selection(client_id, sel_id):
    sel = ClientSelection.query.get_or_404(sel_id)
    if sel.client_id != client_id:
        abort(403)
    sel.status = 'Rejected'
    db.session.commit()
    flash(f'Selection rejected: {sel.category.name}', 'info')
    return redirect(url_for('view_client', client_id=client_id))
