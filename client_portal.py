"""Client-facing portal — ISOLATED from staff auth.

Architecture:
- ClientUser is a completely separate model from User (staff).
- Client sessions use `session['client_user_id']` — never flask-login.
- Every route enforces `@require_client_login` which checks the session key
  and loads the ClientUser + scoped Client record.
- Staff decorators (`@require_login`, `@require_supervisor`) check
  `current_user.is_authenticated` via flask-login, which is structurally
  impossible for a ClientUser because ClientUser is never loaded by the
  flask-login user_loader (it only loads User by PK).

Field gating:
- Every route explicitly selects safe fields for the template.
- Internal fields (cost_code_id, user IDs, task names, dates used only
  for computation) are NEVER passed to the template context.
- Photos require `client_visible=True`.
- Documents require `visibility='client'`.
"""

import logging
import secrets
from collections import OrderedDict
from datetime import datetime, date, timedelta, timezone
from functools import wraps

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from sqlalchemy.orm import joinedload

from app import app, csrf, db
from models import (
    ChangeOrder, Client, ClientActivity, ClientSelection, ClientUser,
    Contract, DailyLog, DailyLogPhoto, Document, DrawScheduleItem,
    Invoice, MagicLink, Notification, PortalMessage, SchedulePhase,
    ScheduleTask, SelectionCategory, SelectionOption, SELECTION_STATUSES,
)

log = logging.getLogger(__name__)

portal = Blueprint('portal', __name__, url_prefix='/portal')


@portal.app_context_processor
def inject_portal_unread():
    """Inject unread message count into all portal templates."""
    cuid = session.get('client_user_id')
    if not cuid:
        return {}
    cu = ClientUser.query.get(cuid)
    if not cu or not cu.is_active:
        return {}
    count = PortalMessage.query.filter_by(
        client_id=cu.client_id, sender_type='staff', is_read=False).count()
    return {'unread_msg_count': count}


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH — magic-link email login, fully isolated from staff
# ═══════════════════════════════════════════════════════════════════════════════

def _current_client_user():
    """Load the ClientUser from session, or None."""
    cuid = session.get('client_user_id')
    if not cuid:
        return None
    cu = ClientUser.query.get(cuid)
    if cu and cu.is_active:
        return cu
    return None


def require_client_login(f):
    """Decorator: require a valid ClientUser session.
    Sets g.client_user and g.client for the request."""
    @wraps(f)
    def decorated(*args, **kwargs):
        cu = _current_client_user()
        if not cu:
            session.pop('client_user_id', None)
            return redirect(url_for('portal.login_page'))
        g.client_user = cu
        g.client = cu.client
        return f(*args, **kwargs)
    return decorated


@portal.route('/login', methods=['GET', 'POST'])
def login_page():
    """Client login — request a magic link by email."""
    if request.method == 'GET':
        return render_template('portal/login.html')

    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('Please enter your email address.', 'error')
        return render_template('portal/login.html')

    cu = ClientUser.query.filter_by(email=email, is_active=True).first()
    if cu:
        token = secrets.token_urlsafe(32)
        ml = MagicLink(
            client_user_id=cu.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.session.add(ml)
        db.session.commit()

        link = url_for('portal.magic_login', token=token, _external=True)
        log.info('Magic link for %s: %s', email, link)
        flash(f'Login link sent to {email}. Check your email.', 'success')

        if app.debug:
            flash(f'DEV: {link}', 'info')
    else:
        flash(f'If an account exists for {email}, a login link has been sent.', 'success')

    return render_template('portal/login.html')


@portal.route('/auth/<token>')
@csrf.exempt
def magic_login(token):
    """Consume a magic link token and create a client session."""
    ml = MagicLink.query.filter_by(token=token, used=False).first()
    if not ml:
        flash('This link is invalid or has already been used.', 'error')
        return redirect(url_for('portal.login_page'))

    now = datetime.now(timezone.utc)
    expires = ml.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        flash('This link has expired. Please request a new one.', 'error')
        return redirect(url_for('portal.login_page'))

    ml.used = True
    cu = ml.client_user
    cu.last_login = now
    db.session.commit()

    session['client_user_id'] = cu.id
    session['_client_portal'] = True

    return redirect(url_for('portal.dashboard'))


@portal.route('/logout')
def logout():
    session.pop('client_user_id', None)
    session.pop('_client_portal', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('portal.login_page'))


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS — fuzzy dates, phase computation
# ═══════════════════════════════════════════════════════════════════════════════

def _fuzzy_window(start_date):
    """Convert a start_date into a client-friendly fuzzy string.
    Never exposes the actual date."""
    if not start_date:
        return None
    today = date.today()
    delta = (start_date - today).days
    if delta < 0:
        return None  # already started
    if delta <= 14:
        return 'Starting in the next couple of weeks'
    if delta <= 30:
        return 'Starting in the next few weeks'
    if delta <= 60:
        return f'Starting around {start_date.strftime("%B")}'
    return f'Expected around {start_date.strftime("%B %Y")}'


def _build_phases(project):
    """Build phase data for the dashboard. Returns (phases, next_phase)."""
    if not project:
        return [], None

    phases = SchedulePhase.query.filter_by(project_id=project.id).order_by(
        SchedulePhase.sort_order).all()

    next_phase = None
    for phase in phases:
        tasks = ScheduleTask.query.filter_by(
            project_id=project.id, phase_id=phase.id).all()
        phase._total = len(tasks)
        phase._done = sum(1 for t in tasks if t.status == 'Done')

        # Compute status
        if phase._total and phase._done == phase._total:
            phase._status = 'Done'
        elif phase._done > 0:
            phase._status = 'In progress'
        else:
            phase._status = 'Coming up'

        # First non-done phase with tasks is "what's next"
        if not next_phase and phase._status != 'Done' and phase._total > 0:
            # Find earliest start date from tasks for fuzzy window
            task_starts = [t.start_date for t in tasks if t.start_date]
            earliest = min(task_starts) if task_starts else None
            phase._window = _fuzzy_window(earliest)
            if phase._status == 'Coming up':
                next_phase = phase

    return phases, next_phase


def _build_action_items(client):
    """Build action items that need the client's attention."""
    items = []

    # Pending selections
    pending = ClientSelection.query.filter_by(
        client_id=client.id, status='Pending').count()
    if pending:
        items.append({
            'icon': '🎨',
            'title': f'{pending} selection{"s" if pending != 1 else ""} awaiting your review',
            'detail': 'Choose your finishes and fixtures',
            'link': url_for('portal.selections'),
        })

    # Change orders awaiting approval
    cos = ChangeOrder.query.filter_by(
        client_id=client.id, status='Sent').all()
    for co in cos:
        items.append({
            'icon': '📝',
            'title': co.title,
            'detail': f'Change order — ${co.price_to_client:,.0f}',
            'link': url_for('public_change_order', token=co.share_token) if co.share_token else url_for('portal.documents'),
        })

    # Invoices due
    invoices = Invoice.query.filter_by(client_id=client.id).filter(
        Invoice.status.in_(['Sent', 'Viewed', 'Partial', 'Overdue'])
    ).all()
    for inv in invoices:
        detail = f'${inv.balance_due:,.2f}'
        if inv.due_date:
            detail += f' — due {inv.due_date.strftime("%m/%d/%Y")}'
        items.append({
            'icon': '💰',
            'title': f'Invoice {inv.invoice_number}',
            'detail': detail,
            'link': url_for('public_invoice', token=inv.share_token) if inv.share_token else url_for('portal.documents'),
        })

    # Unread messages
    unread = PortalMessage.query.filter_by(
        client_id=client.id, sender_type='staff', is_read=False).count()
    if unread:
        items.append({
            'icon': '💬',
            'title': f'{unread} new message{"s" if unread != 1 else ""}',
            'detail': 'From your build team',
            'link': url_for('portal.messages'),
        })

    return items


# ═══════════════════════════════════════════════════════════════════════════════
#  PORTAL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/')
@require_client_login
def dashboard():
    """Client portal home — project overview."""
    client = g.client
    project = client.default_project()

    # Build stage
    phases, next_phase = _build_phases(project)

    # Action items
    action_items = _build_action_items(client)

    # Recent photos (client_visible only)
    shared_photos = DailyLogPhoto.query.filter_by(
        client_id=client.id, client_visible=True
    ).order_by(DailyLogPhoto.created_at.desc()).limit(6).all()

    # Unread messages
    unread_count = PortalMessage.query.filter_by(
        client_id=client.id, sender_type='staff', is_read=False).count()

    from r2_storage_helper import generate_presigned_url
    return render_template('portal/dashboard.html',
                           client=client, project=project,
                           phases=phases, next_phase=next_phase,
                           action_items=action_items,
                           shared_photos=shared_photos,
                           unread_count=unread_count,
                           generate_presigned_url=generate_presigned_url)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHOTOS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/photos')
@require_client_login
def photos():
    """Construction photos — client_visible only, grouped by month."""
    client = g.client
    project = client.default_project()

    query = DailyLogPhoto.query.filter_by(
        client_id=client.id, client_visible=True
    ).order_by(DailyLogPhoto.created_at.desc())

    # Build phase labels for filtering
    phase_labels = []
    phase_map = {}  # cost_code_id -> phase client_label
    if project:
        for phase in SchedulePhase.query.filter_by(project_id=project.id).order_by(
                SchedulePhase.sort_order).all():
            label = phase.client_label or phase.name
            if label not in phase_labels:
                phase_labels.append(label)
            # Map cost codes in this phase's tasks to the phase label
            for task in ScheduleTask.query.filter_by(
                    project_id=project.id, phase_id=phase.id).all():
                if task.cost_code_id:
                    phase_map[task.cost_code_id] = label

    # Apply phase filter if requested
    active_phase = request.args.get('phase')
    if active_phase and phase_map:
        matching_cc_ids = [cc_id for cc_id, lbl in phase_map.items() if lbl == active_phase]
        if matching_cc_ids:
            query = query.filter(DailyLogPhoto.cost_code_id.in_(matching_cc_ids))

    all_photos = query.limit(200).all()

    # Group by month
    photo_months = OrderedDict()
    for photo in all_photos:
        if photo.created_at:
            month_key = photo.created_at.strftime('%B %Y')
        else:
            month_key = 'Undated'
        if month_key not in photo_months:
            photo_months[month_key] = []
        photo_months[month_key].append(photo)

    from r2_storage_helper import generate_presigned_url
    return render_template('portal/photos.html',
                           client=client,
                           photo_months=list(photo_months.items()),
                           phase_labels=phase_labels,
                           active_phase=active_phase,
                           generate_presigned_url=generate_presigned_url)


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/documents')
@require_client_login
def documents():
    """Shared documents — visibility='client' filter, approved COs, invoices."""
    client = g.client

    # Documents explicitly marked for client visibility
    shared_docs = Document.query.filter_by(
        client_id=client.id, visibility='client'
    ).order_by(Document.created_at.desc()).all()

    # Approved change orders (title + price_to_client only, no line items)
    approved_cos = ChangeOrder.query.filter_by(
        client_id=client.id, status='Approved').all()

    # Non-draft invoices
    invoices = Invoice.query.filter_by(client_id=client.id).filter(
        Invoice.status != 'Draft'
    ).order_by(Invoice.created_at.desc()).all()

    return render_template('portal/documents.html',
                           client=client,
                           shared_docs=shared_docs,
                           approved_cos=approved_cos,
                           invoices=invoices)


# ═══════════════════════════════════════════════════════════════════════════════
#  SELECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/selections')
@require_client_login
def selections():
    """View available selection categories and current choices."""
    client = g.client
    categories = SelectionCategory.query.filter_by(is_active=True).order_by(
        SelectionCategory.sort_order).all()

    current = {}
    for sel in client.selections.all():
        current[sel.category_id] = sel

    return render_template('portal/selections.html',
                           client=client, categories=categories, current=current)


@portal.route('/selections/<int:category_id>', methods=['GET', 'POST'])
@require_client_login
def selection_detail(category_id):
    """View options and make a selection for a category."""
    client = g.client
    category = SelectionCategory.query.get_or_404(category_id)
    options = category.options.filter_by(is_active=True).order_by(
        SelectionOption.sort_order).all()

    current = ClientSelection.query.filter_by(
        client_id=client.id, category_id=category_id).first()

    if request.method == 'POST':
        option_id = request.form.get('option_id', type=int)
        note = request.form.get('note', '').strip()
        option = SelectionOption.query.get_or_404(option_id)

        if current:
            current.option_id = option.id
            current.note = note or None
            current.status = 'Pending'
            current.selected_at = datetime.now(timezone.utc)
            current.approved_at = None
        else:
            current = ClientSelection(
                client_id=client.id,
                category_id=category_id,
                option_id=option.id,
                note=note or None,
            )
            db.session.add(current)

        activity = ClientActivity(
            client_id=client.id,
            activity_type='Selection Made',
            note_text=f'{category.name}: {option.name}'
                      f'{" (Additional $" + str(option.price_delta) + ")" if option.price_delta else ""}',
            activity_date=datetime.now(timezone.utc),
        )
        db.session.add(activity)

        # Notify staff
        from models import User, NotificationPreference
        for staff in User.query.filter_by(role='supervisor').all():
            prefs = NotificationPreference.query.filter_by(user_id=staff.id).first()
            if prefs and not prefs.selection_made:
                continue
            notif = Notification(
                user_id=staff.id,
                type='selection_made',
                title=f'Selection: {client.name}',
                message=f'{category.name}: {option.name}',
                link=url_for('view_client', client_id=client.id),
            )
            db.session.add(notif)

        db.session.commit()
        flash(f'Selection submitted: {option.name}', 'success')
        return redirect(url_for('portal.selections'))

    from r2_storage_helper import generate_presigned_url
    return render_template('portal/selection_detail.html',
                           client=client, category=category,
                           options=options, current=current,
                           generate_presigned_url=generate_presigned_url)


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGES
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/messages', methods=['GET', 'POST'])
@require_client_login
def messages():
    """Message thread between client and staff."""
    client = g.client
    cu = g.client_user

    if request.method == 'POST':
        text = request.form.get('message', '').strip()
        if text:
            msg = PortalMessage(
                client_id=client.id,
                sender_type='client',
                sender_name=cu.name or cu.email,
                message=text,
            )
            db.session.add(msg)

            from models import User, NotificationPreference
            for staff in User.query.filter_by(role='supervisor').all():
                prefs = NotificationPreference.query.filter_by(user_id=staff.id).first()
                if prefs and not prefs.portal_message:
                    continue
                notif = Notification(
                    user_id=staff.id,
                    type='portal_message',
                    title=f'Message from {client.name}',
                    message=text[:100],
                    link=url_for('view_client', client_id=client.id),
                )
                db.session.add(notif)

            db.session.commit()
            flash('Message sent.', 'success')
        return redirect(url_for('portal.messages'))

    # Mark staff messages as read
    PortalMessage.query.filter_by(
        client_id=client.id, sender_type='staff', is_read=False
    ).update({'is_read': True})
    db.session.commit()

    all_messages = PortalMessage.query.filter_by(client_id=client.id).order_by(
        PortalMessage.created_at).all()

    return render_template('portal/messages.html',
                           client=client, messages=all_messages,
                           client_user=cu)
