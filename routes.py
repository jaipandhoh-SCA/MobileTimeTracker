from flask import render_template, request, redirect, url_for, session, jsonify, flash, Response, current_app, abort
from flask_login import current_user
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
import csv
from io import StringIO, BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from sqlalchemy.orm import joinedload

from collections import defaultdict

from app import app, db
from models import User, Client, TimeEntry, ActiveClock, ClientActivity, PropertyImage
from google_auth import require_login, require_supervisor, google_auth
from utils import (
    utc_to_pacific, pacific_to_utc, calculate_duration, round_to_quarter_hour,
    format_hours, format_date_for_display, format_datetime_for_display,
    get_pay_period_dates, get_next_pay_period_dates, get_previous_pay_period_dates,
    get_last_30_days_dates, get_month_to_date_dates
)


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

app.register_blueprint(google_auth)


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


@app.route('/home')
@require_login
def home():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    
    if active_clock and (datetime.utcnow() - active_clock.start_time).total_seconds() > 86400:
        long_running = True
    else:
        long_running = False
    
    recent_entries = TimeEntry.query.filter_by(user_id=current_user.id).order_by(
        TimeEntry.date.desc(), TimeEntry.created_at.desc()
    ).limit(5).all()
    
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
                ClientActivity.next_step_date >= datetime.utcnow()
            ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
            
            recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).filter(
                Client.assigned_to_user_id == filter_user_id
            ).order_by(ClientActivity.activity_date.desc()).limit(5).all()
        else:
            next_steps = ClientActivity.query.join(Client).filter(
                ClientActivity.next_step_date.isnot(None),
                ClientActivity.next_step_date >= datetime.utcnow()
            ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
            
            recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).order_by(
                ClientActivity.activity_date.desc()
            ).limit(5).all()
    else:
        next_steps = ClientActivity.query.join(Client).filter(
            Client.assigned_to_user_id == current_user.id,
            ClientActivity.next_step_date.isnot(None),
            ClientActivity.next_step_date >= datetime.utcnow()
        ).order_by(ClientActivity.next_step_date.asc()).limit(5).all()
        
        recent_activities = ClientActivity.query.options(joinedload(ClientActivity.user)).join(Client).filter(
            Client.assigned_to_user_id == current_user.id
        ).order_by(ClientActivity.activity_date.desc()).limit(5).all()
    
    # Build weekly hours for the last 7 days (for trend chart)
    today = date.today()
    week_start = today - timedelta(days=6)
    week_entries = TimeEntry.query.filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.date >= week_start,
        TimeEntry.date <= today
    ).all()
    weekly_hours = build_daily_hours(week_entries, week_start, today)

    return render_template('home.html',
                         active_clock=active_clock,
                         long_running=long_running,
                         recent_entries=recent_entries,
                         my_clients=my_clients,
                         recent_clients=recent_clients,
                         status_counts=status_counts,
                         status_values=status_values,
                         total_value=total_value,
                         next_steps=next_steps,
                         recent_activities=recent_activities,
                         all_users=all_users,
                         selected_user=selected_user,
                         weekly_hours=weekly_hours)


@app.route('/clock/start', methods=['POST'])
@require_login
def start_clock():
    existing = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if existing:
        flash('You already have an active clock running.', 'warning')
        return redirect(url_for('home'))
    
    new_clock = ActiveClock(user_id=current_user.id, start_time=datetime.utcnow())
    db.session.add(new_clock)
    db.session.commit()
    
    flash('Clock started successfully!', 'success')
    return redirect(url_for('home'))


@app.route('/clock/status')
@require_login
def clock_status():
    active_clock = ActiveClock.query.filter_by(user_id=current_user.id).first()
    if active_clock:
        elapsed = (datetime.utcnow() - active_clock.start_time).total_seconds()
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
    
    elapsed = (datetime.utcnow() - active_clock.start_time).total_seconds()
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
    
    elapsed = (datetime.utcnow() - active_clock.start_time).total_seconds()
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
        duration = calculate_duration(active_clock.start_time, datetime.utcnow())
        return render_template('stop_clock.html', 
                             active_clock=active_clock,
                             clients=clients,
                             duration=duration)
    
    client_id = request.form.get('client_id')
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
    
    end_time = datetime.utcnow()
    duration = calculate_duration(active_clock.start_time, end_time)
    
    break_deduction = 0
    if active_clock.break_15_taken:
        break_deduction += 0.25
    if active_clock.lunch_taken:
        break_deduction += 1.0
    
    final_duration = max(0, duration - break_deduction)
    
    entry = TimeEntry(
        user_id=current_user.id,
        client_id=client_id,
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
        return render_template('quick_log.html', clients=clients, today=date.today())
    
    entry_date = request.form.get('date')
    client_id = request.form.get('client_id')
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
    
    summary_entries = TimeEntry.query.filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.date >= summary_start,
        TimeEntry.date <= summary_end
    ).all()
    
    summary_hours = sum((e.duration_hours or 0) for e in summary_entries)
    summary_billable = sum((e.duration_hours or 0) for e in summary_entries if e.client_id)
    summary_entry_count = len(summary_entries)
    summary_unique_clients = len(set(e.client_id for e in summary_entries if e.client_id))
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


@app.route('/clients')
@require_login
def clients():
    search = request.args.get('search', '')
    show_all = request.args.get('show_all', 'false') == 'true'
    
    query = Client.query
    
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
        return render_template('client_form.html', client=None)
    
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
        created_by_user_id=current_user.id,
        assigned_to_user_id=current_user.id
    )
    db.session.add(client)
    db.session.commit()
    
    from r2_storage_helper import build_client_prefix
    client.storage_prefix = build_client_prefix(client.name, client.address)
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
        return render_template('client_form.html', client=client, activities=activities, all_users=all_users)
    
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
    
    client.name = name
    client.address = address
    client.contact_name = contact_name if contact_name else None
    client.phone = phone if phone else None
    client.email = email if email else None
    client.status = status
    client.notes = notes if notes else None
    
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
    
    client.status = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'status': new_status})


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

            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
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

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
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

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
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
            activity_date=datetime.utcnow(),
            file_path=key,
            file_name=filename
        )

        db.session.add(activity)
        db.session.commit()

        return jsonify({'success': True, 'file_name': filename})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to upload file: {str(e)}'}), 500


@app.route('/admin')
@require_supervisor
def admin_dashboard():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rep_id = request.args.get('rep_id')
    client_id = request.args.get('client_id')
    
    # Determine default dates for comparison
    first_day_of_month = date.today().replace(day=1)
    default_date_from = first_day_of_month.strftime('%Y-%m-%d')
    
    # Check if filters are actively applied (different from defaults)
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
    
    total_hours = sum((e.duration_hours or 0) for e in entries)
    total_billable = sum((e.duration_hours or 0) for e in entries if e.client_id)
    entry_count = len(entries)
    unique_clients = len(set(e.client_id for e in entries if e.client_id))
    
    reps = User.query.filter_by(role='rep').order_by(User.first_name).all()
    supervisors = User.query.filter_by(role='supervisor').order_by(User.first_name).all()
    all_users = reps + supervisors
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    
    current_period_start, current_period_end, current_pay_date = get_pay_period_dates()
    next_period_start, next_period_end, next_pay_date = get_next_pay_period_dates()
    
    # Calculate Current Pay Period payroll (always shown)
    payroll_data = []
    for rep in reps:
        current_hours = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end
        ).all()
        current_total_hours = sum((e.duration_hours or 0) for e in current_hours)
        current_pay = float(current_total_hours) * float(rep.hourly_rate or 0)
        
        next_hours = TimeEntry.query.filter(
            TimeEntry.user_id == rep.id,
            TimeEntry.date >= next_period_start,
            TimeEntry.date <= next_period_end
        ).all()
        next_total_hours = sum((e.duration_hours or 0) for e in next_hours)
        next_pay = float(next_total_hours) * float(rep.hourly_rate or 0)
        
        payroll_data.append({
            'rep': rep,
            'current_hours': float(current_total_hours),
            'current_pay': current_pay,
            'next_hours': float(next_total_hours),
            'next_pay': next_pay
        })
    
    # Calculate Filtered Period payroll (only when filters are applied)
    filtered_payroll_data = None
    filtered_date_from = None
    filtered_date_to = None
    
    if filters_applied:
        # Parse the filter dates
        try:
            filtered_date_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
        except:
            filtered_date_from = None
        
        try:
            filtered_date_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        except:
            filtered_date_to = None
        
        # Determine which reps to include (single rep or all reps)
        if rep_id:
            filtered_reps = [User.query.get(rep_id)] if User.query.get(rep_id) else []
        else:
            filtered_reps = reps
        
        filtered_payroll_data = []
        for rep in filtered_reps:
            # Build filtered query for this rep
            filtered_query = TimeEntry.query.filter_by(user_id=rep.id)
            
            if filtered_date_from:
                filtered_query = filtered_query.filter(TimeEntry.date >= filtered_date_from)
            
            if filtered_date_to:
                filtered_query = filtered_query.filter(TimeEntry.date <= filtered_date_to)
            
            if client_id:
                filtered_query = filtered_query.filter_by(client_id=client_id)
            
            filtered_hours = filtered_query.all()
            filtered_total_hours = sum((e.duration_hours or 0) for e in filtered_hours)
            filtered_pay = float(filtered_total_hours) * float(rep.hourly_rate or 0)
            
            # Only include reps with hours in the filtered period
            if filtered_total_hours > 0:
                filtered_payroll_data.append({
                    'rep': rep,
                    'hours': float(filtered_total_hours),
                    'pay': filtered_pay
                })
    
    # Build daily totals for the current pay period (company-wide trend chart)
    daily_totals = build_daily_hours(
        TimeEntry.query.filter(
            TimeEntry.date >= current_period_start,
            TimeEntry.date <= current_period_end
        ).all(),
        current_period_start, current_period_end
    )

    return render_template('admin_dashboard.html',
                         entries=entries,
                         total_hours=total_hours,
                         total_billable=total_billable,
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
                         daily_totals=daily_totals)


@app.route('/admin/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@require_supervisor
def edit_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    return_url = request.args.get('return_url') or request.form.get('return_url')
    
    if request.method == 'GET':
        clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
        return render_template('edit_entry.html', entry=entry, clients=clients, return_url=return_url)
    
    entry_date = request.form.get('date')
    client_id = request.form.get('client_id')
    work_description = request.form.get('work_description', '').strip()
    duration_hours = request.form.get('duration_hours')
    
    try:
        entry.date = datetime.strptime(entry_date, '%Y-%m-%d').date()
        entry.client_id = client_id if client_id else None
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


@app.route('/admin/export')
@require_supervisor
def export_csv():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rep_id = request.args.get('rep_id')
    client_id = request.args.get('client_id')
    
    query = TimeEntry.query
    
    if date_from:
        try:
            query = query.filter(TimeEntry.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except:
            pass
    
    if date_to:
        try:
            query = query.filter(TimeEntry.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except:
            pass
    
    if rep_id:
        query = query.filter_by(user_id=rep_id)
    
    if client_id:
        query = query.filter_by(client_id=client_id)
    
    entries = query.order_by(TimeEntry.date).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Client Name', 'Client Address', 'Work completed', 'Time (hours)', 'Rep'])
    
    for entry in entries:
        client = Client.query.get(entry.client_id) if entry.client_id else None
        user = User.query.get(entry.user_id)
        
        writer.writerow([
            format_date_for_display(entry.date),
            client.name if client else 'N/A',
            client.address if client else 'N/A',
            entry.work_description,
            format_hours(entry.duration_hours),
            user.display_name if user else 'Unknown'
        ])
    
    output.seek(0)
    filename = f"time_entries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


def generate_time_entries_pdf(user, entries, summary_data, timeframe_label):
    """Helper function to generate PDF for time entries"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1f2937'), spaceAfter=12, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#4b5563'), spaceAfter=6, alignment=TA_CENTER)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#1f2937'), spaceBefore=12, spaceAfter=6)
    
    # Title
    title = Paragraph(f"{user.display_name}'s Time Entries", title_style)
    story.append(title)
    
    # Timeframe and rate info
    subtitle = Paragraph(f"Rate: ${user.hourly_rate}/hr | {timeframe_label}", subtitle_style)
    story.append(subtitle)
    
    story.append(Spacer(1, 0.3*inch))
    
    # Activity Summary Section
    story.append(Paragraph("Activity Summary", heading_style))
    
    # Summary info paragraph
    summary_text = f"{summary_data['timeframe_header']}"
    if summary_data.get('pay_date'):
        summary_text += f"<br/>Pay Date: {summary_data['pay_date']}"
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Summary stats table
    summary_table_data = [
        ['Total Hours', 'Billable Hours', 'Entries', 'Clients'],
        [
            format_hours(summary_data['total_hours']),
            format_hours(summary_data['billable_hours']),
            str(summary_data['num_entries']),
            str(summary_data['num_clients'])
        ]
    ]
    
    summary_table = Table(summary_table_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    
    story.append(summary_table)
    
    # Total Pay (large)
    story.append(Spacer(1, 0.2*inch))
    total_pay_text = f"<b>Total Pay: ${summary_data['summary_pay']:.2f}</b>"
    total_pay = Paragraph(total_pay_text, ParagraphStyle('TotalPay', parent=styles['Normal'], fontSize=16, textColor=colors.HexColor('#3b82f6'), alignment=TA_CENTER))
    story.append(total_pay)
    
    story.append(Spacer(1, 0.3*inch))
    
    # All Time Entries Section
    story.append(Paragraph("All Time Entries", heading_style))
    story.append(Spacer(1, 0.1*inch))
    
    if entries:
        # Time entries table
        table_data = [['Date', 'Client', 'Work Description', 'Hours']]
        
        for entry in entries:
            client = Client.query.get(entry.client_id) if entry.client_id else None
            client_name = client.name if client else 'N/A'
            
            # Truncate work description if too long
            work_desc = entry.work_description
            if len(work_desc) > 60:
                work_desc = work_desc[:57] + '...'
            
            table_data.append([
                format_date_for_display(entry.date),
                client_name,
                work_desc,
                format_hours(entry.duration_hours)
            ])
        
        entries_table = Table(table_data, colWidths=[1.2*inch, 1.8*inch, 3*inch, 0.8*inch])
        entries_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]))
        
        story.append(entries_table)
    else:
        story.append(Paragraph("No time entries found for this period.", styles['Normal']))
    
    # Footer with generated timestamp
    story.append(Spacer(1, 0.3*inch))
    footer_text = f"<i>Generated on {datetime.now().strftime('%m/%d/%Y at %I:%M %p PST')}</i>"
    footer = Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER))
    story.append(footer)
    
    # Build PDF
    doc.build(story)
    
    buffer.seek(0)
    return buffer


@app.route('/rep/<user_id>/export_pdf')
@require_supervisor
def export_rep_time_entries_pdf(user_id):
    """Export a rep's time entries as PDF (supervisor view)"""
    user = User.query.get_or_404(user_id)
    
    # Get filters from URL
    timeframe = request.args.get('timeframe', 'current_period')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    client_id = request.args.get('client_id')
    
    # Determine timeframe dates
    if timeframe == 'current_period':
        summary_start, summary_end, period_pay_date = get_pay_period_dates()
        timeframe_label = f"Current Pay Period: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = period_pay_date.strftime('%m/%d/%Y') if period_pay_date else None
    elif timeframe == 'previous_period':
        summary_start, summary_end, period_pay_date = get_previous_pay_period_dates()
        timeframe_label = f"Previous Pay Period: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = period_pay_date.strftime('%m/%d/%Y') if period_pay_date else None
    elif timeframe == 'month_to_date':
        summary_start, summary_end, _ = get_month_to_date_dates()
        timeframe_label = f"Month-to-Date: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = None
    else:
        summary_start, summary_end, _ = get_last_30_days_dates()
        timeframe_label = f"Last 30 Days: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = None
    
    # Build entries query
    query = TimeEntry.query.filter_by(user_id=user_id)
    
    # Apply date filters (manual filters override timeframe)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date >= from_date)
        except:
            query = query.filter(TimeEntry.date >= summary_start)
    else:
        query = query.filter(TimeEntry.date >= summary_start)
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date <= to_date)
        except:
            query = query.filter(TimeEntry.date <= summary_end)
    else:
        query = query.filter(TimeEntry.date <= summary_end)
    
    if client_id:
        query = query.filter_by(client_id=client_id)
    
    entries = query.order_by(TimeEntry.date.desc()).all()
    
    # Calculate summary stats
    total_hours = sum(entry.duration_hours for entry in entries)
    billable_hours = sum(entry.duration_hours for entry in entries if entry.client_id)
    num_entries = len(entries)
    num_clients = len(set(entry.client_id for entry in entries if entry.client_id))
    summary_pay = total_hours * user.hourly_rate if user.hourly_rate else Decimal('0')
    
    summary_data = {
        'timeframe_header': timeframe_label.split(': ')[0],
        'pay_date': pay_date,
        'total_hours': total_hours,
        'billable_hours': billable_hours,
        'num_entries': num_entries,
        'num_clients': num_clients,
        'summary_pay': summary_pay
    }
    
    # Generate PDF
    pdf_buffer = generate_time_entries_pdf(user, entries, summary_data, timeframe_label)
    
    filename = f"{user.display_name.replace(' ', '_')}_time_entries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        pdf_buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/my_logs/export_pdf')
@require_login
def export_my_logs_pdf():
    """Export current user's time entries as PDF (rep self-view)"""
    user = current_user
    
    # Get filters from URL
    timeframe = request.args.get('timeframe', 'current_period')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    client_id = request.args.get('client_id')
    
    # Determine timeframe dates
    if timeframe == 'current_period':
        summary_start, summary_end, period_pay_date = get_pay_period_dates()
        timeframe_label = f"Current Pay Period: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = period_pay_date.strftime('%m/%d/%Y') if period_pay_date else None
    elif timeframe == 'previous_period':
        summary_start, summary_end, period_pay_date = get_previous_pay_period_dates()
        timeframe_label = f"Previous Pay Period: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = period_pay_date.strftime('%m/%d/%Y') if period_pay_date else None
    elif timeframe == 'month_to_date':
        summary_start, summary_end, _ = get_month_to_date_dates()
        timeframe_label = f"Month-to-Date: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = None
    else:
        summary_start, summary_end, _ = get_last_30_days_dates()
        timeframe_label = f"Last 30 Days: {summary_start.strftime('%m/%d/%Y')} - {summary_end.strftime('%m/%d/%Y')}"
        pay_date = None
    
    # Build entries query
    query = TimeEntry.query.filter_by(user_id=user.id)
    
    # Apply date filters (manual filters override timeframe)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date >= from_date)
        except:
            query = query.filter(TimeEntry.date >= summary_start)
    else:
        query = query.filter(TimeEntry.date >= summary_start)
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date <= to_date)
        except:
            query = query.filter(TimeEntry.date <= summary_end)
    else:
        query = query.filter(TimeEntry.date <= summary_end)
    
    if client_id:
        query = query.filter_by(client_id=client_id)
    
    entries = query.order_by(TimeEntry.date.desc()).all()
    
    # Calculate summary stats
    total_hours = sum(entry.duration_hours for entry in entries)
    billable_hours = sum(entry.duration_hours for entry in entries if entry.client_id)
    num_entries = len(entries)
    num_clients = len(set(entry.client_id for entry in entries if entry.client_id))
    summary_pay = total_hours * user.hourly_rate if user.hourly_rate else Decimal('0')
    
    summary_data = {
        'timeframe_header': timeframe_label.split(': ')[0],
        'pay_date': pay_date,
        'total_hours': total_hours,
        'billable_hours': billable_hours,
        'num_entries': num_entries,
        'num_clients': num_clients,
        'summary_pay': summary_pay
    }
    
    # Generate PDF
    pdf_buffer = generate_time_entries_pdf(user, entries, summary_data, timeframe_label)
    
    filename = f"my_time_entries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        pdf_buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


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


@app.route('/admin/users/<user_id>/update-rate', methods=['POST'])
@require_supervisor
def update_user_rate(user_id):
    user = User.query.get_or_404(user_id)
    
    hourly_rate = request.form.get('hourly_rate', '').strip()
    
    try:
        rate = Decimal(hourly_rate)
        if rate < 0 or rate > 999.99:
            flash('Hourly rate must be between $0.00 and $999.99.', 'error')
            return redirect(url_for('manage_users'))
        
        user.hourly_rate = rate
        db.session.commit()
        
        flash(f'Hourly rate for {user.display_name} updated to ${rate:.2f}/hr.', 'success')
    except (ValueError, TypeError):
        flash('Invalid hourly rate value.', 'error')
    
    return redirect(url_for('manage_users'))


@app.route('/admin/users/add-authorized', methods=['POST'])
@require_supervisor
def add_authorized_user():
    from models import AuthorizedUser
    
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'rep').strip()
    hourly_rate_str = request.form.get('hourly_rate', '0').strip()
    
    if not email:
        flash('Email address is required.', 'error')
        return redirect(url_for('manage_users'))
    
    if role not in ['rep', 'supervisor']:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('manage_users'))
    
    try:
        hourly_rate = Decimal(hourly_rate_str) if hourly_rate_str else Decimal('0')
        if hourly_rate < 0 or hourly_rate > 999.99:
            flash('Hourly rate must be between $0.00 and $999.99.', 'error')
            return redirect(url_for('manage_users'))
    except (ValueError, TypeError):
        flash('Invalid hourly rate value.', 'error')
        return redirect(url_for('manage_users'))
    
    existing = AuthorizedUser.query.filter_by(email=email).first()
    if existing:
        flash(f'{email} is already authorized.', 'error')
        return redirect(url_for('manage_users'))
    
    auth_user = AuthorizedUser(
        email=email,
        role=role,
        hourly_rate=hourly_rate,
        added_by_user_id=current_user.id
    )
    db.session.add(auth_user)
    db.session.commit()
    
    flash(f'Successfully authorized {email} as {role.title()} with ${hourly_rate:.2f}/hr rate.', 'success')
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
        hourly_rate_str = request.form.get('hourly_rate', '').strip() if current_user.is_supervisor else None
        
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
        
        if current_user.is_supervisor and hourly_rate_str:
            try:
                hourly_rate = Decimal(hourly_rate_str)
                if hourly_rate < 0:
                    flash('Hourly rate cannot be negative.', 'error')
                    return redirect(url_for('edit_profile'))
                current_user.hourly_rate = hourly_rate
            except (ValueError, InvalidOperation):
                flash('Invalid hourly rate. Please enter a valid number.', 'error')
                return redirect(url_for('edit_profile'))
        
        current_user.updated_at = datetime.utcnow()
        
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
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
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
        current_user.updated_at = datetime.utcnow()
        
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
        hourly_rate_str = request.form.get('hourly_rate', '').strip()
        
        if not first_name or not last_name or not email or not phone or not address:
            flash('All fields (except hourly rate) are required.', 'error')
            return redirect(url_for('edit_user_profile', user_id=user_id))
        
        if email != user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('This email is already in use by another user.', 'error')
                return redirect(url_for('edit_user_profile', user_id=user_id))
        
        if role not in ['rep', 'supervisor']:
            flash('Invalid role selected.', 'error')
            return redirect(url_for('edit_user_profile', user_id=user_id))
        
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.phone = phone
        user.address = address
        user.role = role
        
        if hourly_rate_str:
            try:
                hourly_rate = Decimal(hourly_rate_str)
                if hourly_rate < 0:
                    flash('Hourly rate cannot be negative.', 'error')
                    return redirect(url_for('edit_user_profile', user_id=user_id))
                user.hourly_rate = hourly_rate
            except (ValueError, InvalidOperation):
                flash('Invalid hourly rate format.', 'error')
                return redirect(url_for('edit_user_profile', user_id=user_id))
        else:
            user.hourly_rate = Decimal('0.00')
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'Profile for {user.display_name} updated successfully!', 'success')
        return redirect(url_for('edit_user_profile', user_id=user_id))
    
    all_users = User.query.order_by(User.first_name, User.last_name).all()
    clients_assigned_count = Client.query.filter_by(assigned_to_user_id=user.id, is_active=True).count()
    
    return render_template('edit_user_profile.html', user=user, editing_user=user, 
                          all_users=all_users, clients_assigned_count=clients_assigned_count)


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
    
    TimeEntry.query.filter_by(user_id=user.id).delete()
    ActiveClock.query.filter_by(user_id=user.id).delete()
    Client.query.filter_by(created_by_user_id=user.id).update({'created_by_user_id': None})
    
    from models import AuthorizedUser
    AuthorizedUser.query.filter_by(email=user.email).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    flash(flash_message, 'success')
    return redirect(url_for('manage_users'))


@app.template_filter('format_hours')
def format_hours_filter(value):
    return format_hours(value)


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


from utils import PACIFIC_TZ
