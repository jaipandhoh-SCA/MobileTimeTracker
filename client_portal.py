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
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from sqlalchemy.orm import joinedload

from app import app, csrf, db
from models import (
    ChangeOrder, Client, ClientActivity, ClientSelection, ClientUser,
    Contract, DailyLog, DailyLogPhoto, Document, DrawScheduleItem,
    Invoice, MagicLink, Notification, PortalMessage, SelectionCategory,
    SelectionOption, SELECTION_STATUSES,
)

log = logging.getLogger(__name__)

portal = Blueprint('portal', __name__, url_prefix='/portal')


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
        # Generate magic link
        token = secrets.token_urlsafe(32)
        ml = MagicLink(
            client_user_id=cu.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.session.add(ml)
        db.session.commit()

        link = url_for('portal.magic_login', token=token, _external=True)

        # In production, send via email.  For now, flash + log it.
        log.info('Magic link for %s: %s', email, link)
        flash(f'Login link sent to {email}. Check your email.', 'success')

        # Store the link in a dev-friendly way
        if app.debug:
            flash(f'DEV: {link}', 'info')
    else:
        # Don't reveal whether the email exists
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

    # Set client session — NOT flask-login
    session['client_user_id'] = cu.id
    session['_client_portal'] = True  # Tag for isolation checks

    return redirect(url_for('portal.dashboard'))


@portal.route('/logout')
def logout():
    session.pop('client_user_id', None)
    session.pop('_client_portal', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('portal.login_page'))


# ═══════════════════════════════════════════════════════════════════════════════
#  PORTAL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/')
@require_client_login
def dashboard():
    """Client portal home — project overview."""
    client = g.client
    project = client.default_project()

    # Progress phases from schedule
    from models import SchedulePhase, ScheduleTask
    phases = []
    if project:
        phases = SchedulePhase.query.filter_by(project_id=project.id).order_by(
            SchedulePhase.sort_order).all()
        for phase in phases:
            tasks = ScheduleTask.query.filter_by(project_id=project.id, phase_id=phase.id).all()
            phase._total = len(tasks)
            phase._done = sum(1 for t in tasks if t.status == 'Done')

    # Milestones (draw schedule)
    contract = client.contracts.filter_by(status='Signed').first() or \
               client.contracts.filter_by(status='Executed').first()
    draws = []
    if contract:
        draws = contract.draw_schedule.order_by(DrawScheduleItem.sort_order).all()

    # Recent shared photos
    shared_photos = DailyLogPhoto.query.filter_by(client_id=client.id).order_by(
        DailyLogPhoto.created_at.desc()).limit(6).all()

    # Unread messages
    unread_count = PortalMessage.query.filter_by(
        client_id=client.id, sender_type='staff', is_read=False).count()

    # Pending selections
    pending_selections = ClientSelection.query.filter_by(
        client_id=client.id, status='Pending').count()

    from r2_storage_helper import generate_presigned_url
    return render_template('portal/dashboard.html',
                           client=client, project=project,
                           phases=phases, draws=draws,
                           shared_photos=shared_photos,
                           unread_count=unread_count,
                           pending_selections=pending_selections,
                           generate_presigned_url=generate_presigned_url)


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/documents')
@require_client_login
def documents():
    """Shared documents — contracts, approved COs, invoices."""
    client = g.client

    contracts = client.contracts.all()
    approved_cos = client.change_orders.filter_by(status='Approved').all()
    invoices = client.invoices.filter(Invoice.status != 'Draft').all()

    # Shared documents (plans, specs, etc. marked for portal)
    shared_docs = Document.query.filter_by(client_id=client.id).filter(
        Document.folder.in_(['plans', 'contracts', 'specs'])
    ).order_by(Document.created_at.desc()).all()

    return render_template('portal/documents.html',
                           client=client, contracts=contracts,
                           approved_cos=approved_cos, invoices=invoices,
                           shared_docs=shared_docs)


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

    # Current selections by category
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

        # Log activity
        activity = ClientActivity(
            client_id=client.id,
            activity_type='Selection Made',
            note_text=f'{category.name}: {option.name}'
                      f'{" (+$" + str(option.price_delta) + ")" if option.price_delta else ""}',
            activity_date=datetime.now(timezone.utc),
        )
        db.session.add(activity)

        # Notify staff (respecting preferences)
        from models import User, NotificationPreference
        for staff in User.query.filter_by(role='supervisor').all():
            prefs = NotificationPreference.query.filter_by(user_id=staff.id).first()
            if prefs and not prefs.selection_made:
                continue
            notif = Notification(
                user_id=staff.id,
                type='selection_made',
                title=f'Selection: {client.name}',
                message=f'{category.name} → {option.name}',
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

            # Notify staff (respecting preferences)
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


# ═══════════════════════════════════════════════════════════════════════════════
#  PROGRESS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/progress')
@require_client_login
def progress():
    """Detailed project progress view."""
    client = g.client
    project = client.default_project()

    from models import SchedulePhase, ScheduleTask
    phases = []
    if project:
        phases = SchedulePhase.query.filter_by(project_id=project.id).order_by(
            SchedulePhase.sort_order).all()
        for phase in phases:
            phase._tasks = ScheduleTask.query.filter_by(
                project_id=project.id, phase_id=phase.id
            ).order_by(ScheduleTask.start_date).all()

    return render_template('portal/progress.html',
                           client=client, project=project, phases=phases)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHOTOS
# ═══════════════════════════════════════════════════════════════════════════════

@portal.route('/photos')
@require_client_login
def photos():
    """Shared construction photos."""
    client = g.client
    photos = DailyLogPhoto.query.filter_by(client_id=client.id).order_by(
        DailyLogPhoto.created_at.desc()).limit(50).all()

    from r2_storage_helper import generate_presigned_url
    return render_template('portal/photos.html',
                           client=client, photos=photos,
                           generate_presigned_url=generate_presigned_url)
