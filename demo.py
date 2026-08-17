"""Demo mode: seeds sample data, manages guided tour state.

All demo records are tagged with [DEMO] in their names and a
'demo_' prefix on user IDs so they can be cleanly removed.
"""

from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import secrets
import logging

from flask import Blueprint, redirect, url_for, session, flash, jsonify
from flask_login import login_user, current_user

from app import db, csrf
from models import (
    User, Client, Project, CostCode, Budget, CostEntry,
    Estimate, EstimateLineItem, Proposal, Contract, DrawScheduleItem,
    ChangeOrder, ChangeOrderItem, Invoice, InvoiceLineItem, Payment,
    SchedulePhase, ScheduleTask, TaskAssignment,
    DailyLog, TimeEntry, ClientActivity, ClientStatusChange,
    Notification, LeadSource, ChannelSpend,
    SelectionCategory, SelectionOption, ClientSelection,
    ClientUser, PortalMessage, AppSetting,
)

log = logging.getLogger(__name__)

demo_bp = Blueprint('demo', __name__, url_prefix='/demo')

DEMO_USER_ID = 'demo_supervisor_001'
DEMO_REP_ID = 'demo_rep_001'


def _today():
    return date.today()


def _now():
    return datetime.now(timezone.utc)


def _seed_demo_data():
    """Create a full set of demo records. Idempotent — skips if demo user exists."""

    # Check if already seeded
    if User.query.get(DEMO_USER_ID):
        return  # already seeded

    now = _now()
    today = _today()

    # ── Users ───────────────────────────────────────────────
    # Clean up any leftover emails from a partial seed
    User.query.filter(User.email.in_([
        'demo-supervisor@example.com', 'demo-rep@example.com'
    ])).delete(synchronize_session=False)

    sup = User(
        id=DEMO_USER_ID, email='demo-supervisor@example.com',
        first_name='[DEMO] Sarah', last_name='Martinez',
        role='supervisor', hourly_rate=Decimal('55.00'),
        last_login=now,
    )
    rep = User(
        id=DEMO_REP_ID, email='demo-rep@example.com',
        first_name='[DEMO] Jake', last_name='Thompson',
        role='rep', hourly_rate=Decimal('35.00'),
        last_login=now,
    )
    db.session.add_all([sup, rep])
    db.session.flush()

    # ── Lead Sources ────────────────────────────────────────
    ls_google = LeadSource.query.filter_by(name='Google Ads').first()
    ls_referral = LeadSource.query.filter_by(name='Referral').first()
    if not ls_google:
        ls_google = LeadSource(name='Google Ads', channel_type='paid_ads')
        db.session.add(ls_google)
    if not ls_referral:
        ls_referral = LeadSource(name='Referral', channel_type='referral')
        db.session.add(ls_referral)
    db.session.flush()

    # ── Cost Codes (use existing or create) ─────────────────
    def get_or_create_cc(code, name, cost_type='Labor', sort=0):
        cc = CostCode.query.filter_by(code=code).first()
        if not cc:
            cc = CostCode(code=code, name=name, default_cost_type=cost_type, sort_order=sort)
            db.session.add(cc)
            db.session.flush()
        return cc

    cc_gen = get_or_create_cc('01', 'General Conditions', 'Labor', 1)
    cc_demo = get_or_create_cc('02', 'Demolition', 'Labor', 2)
    cc_fnd = get_or_create_cc('03', 'Foundation', 'Material', 3)
    cc_frm = get_or_create_cc('06', 'Framing', 'Labor', 6)
    cc_elec = get_or_create_cc('16', 'Electrical', 'Subcontractor', 16)
    cc_plmb = get_or_create_cc('17', 'Plumbing', 'Subcontractor', 17)
    cc_roof = get_or_create_cc('07', 'Roofing', 'Material', 7)
    cc_fin = get_or_create_cc('09', 'Finishes', 'Material', 9)

    # ── Clients ─────────────────────────────────────────────
    client_active = Client(
        name='[DEMO] Johnson Residence', address='1234 Oak Lane, Pasadena, CA 91101',
        contact_name='Michael Johnson', phone='(626) 555-0142',
        email='mjohnson@example.com', status='Active',
        opportunity_value=Decimal('185000'), final_contract_value=Decimal('172500'),
        type_of_adu='Detached', desired_adu_sqft='650', number_of_bed='1',
        number_of_bath='1', style='Modern', max_budget=Decimal('200000'),
        created_by_user_id=DEMO_USER_ID, assigned_to_user_id=DEMO_REP_ID,
        lead_source_id=ls_google.id,
        estimated_start_date=today - timedelta(days=30),
        estimated_end_date=today + timedelta(days=90),
    )
    client_prospect = Client(
        name='[DEMO] Chen Property', address='567 Maple Drive, Arcadia, CA 91006',
        contact_name='Lisa Chen', phone='(626) 555-0298',
        email='lchen@example.com', status='Prospect',
        opportunity_value=Decimal('210000'),
        type_of_adu='2BR', desired_adu_sqft='800', number_of_bed='2',
        number_of_bath='1', style='Contemporary',
        created_by_user_id=DEMO_REP_ID, assigned_to_user_id=DEMO_REP_ID,
        lead_source_id=ls_referral.id,
    )
    client_lead = Client(
        name='[DEMO] Rivera Family', address='890 Palm Street, Monrovia, CA 91016',
        contact_name='Carlos Rivera', phone='(626) 555-0371',
        email='crivera@example.com', status='Lead',
        opportunity_value=Decimal('150000'),
        type_of_adu='Garage Conversion', desired_adu_sqft='400',
        created_by_user_id=DEMO_REP_ID, assigned_to_user_id=DEMO_REP_ID,
        lead_source_id=ls_google.id,
    )
    client_completed = Client(
        name='[DEMO] Park ADU (Completed)', address='2100 Birch Ave, Glendale, CA 91201',
        contact_name='David Park', phone='(818) 555-0455',
        email='dpark@example.com', status='Completed',
        opportunity_value=Decimal('165000'), final_contract_value=Decimal('158000'),
        type_of_adu='Studio', desired_adu_sqft='450', number_of_bed='0',
        number_of_bath='1',
        created_by_user_id=DEMO_USER_ID, assigned_to_user_id=DEMO_REP_ID,
        lead_source_id=ls_referral.id,
    )
    db.session.add_all([client_active, client_prospect, client_lead, client_completed])
    db.session.flush()

    # ── Projects ────────────────────────────────────────────
    proj_active = Project(
        client_id=client_active.id, name='[DEMO] Johnson ADU',
        contract_value=Decimal('172500'), status='In Progress',
        is_default=True, start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=90),
    )
    proj_completed = Project(
        client_id=client_completed.id, name='[DEMO] Park Studio ADU',
        contract_value=Decimal('158000'), status='Completed',
        is_default=True, start_date=today - timedelta(days=180),
        end_date=today - timedelta(days=15),
    )
    proj_prospect = Project(
        client_id=client_prospect.id, name='[DEMO] Chen 2BR ADU',
        status='Planning', is_default=True,
    )
    db.session.add_all([proj_active, proj_completed, proj_prospect])
    db.session.flush()

    # ── Budgets (for active project) ────────────────────────
    budgets_data = [
        (cc_gen, 'Labor', Decimal('8500')),
        (cc_demo, 'Labor', Decimal('4200')),
        (cc_fnd, 'Material', Decimal('18000')),
        (cc_fnd, 'Labor', Decimal('12000')),
        (cc_frm, 'Labor', Decimal('22000')),
        (cc_frm, 'Material', Decimal('15000')),
        (cc_elec, 'Subcontractor', Decimal('14000')),
        (cc_plmb, 'Subcontractor', Decimal('12000')),
        (cc_roof, 'Material', Decimal('9500')),
        (cc_fin, 'Material', Decimal('18000')),
    ]
    for cc, ct, amt in budgets_data:
        db.session.add(Budget(
            project_id=proj_active.id, cost_code_id=cc.id,
            cost_type=ct, amount=amt,
        ))

    # ── Cost Entries (actual costs posted) ──────────────────
    cost_entries_data = [
        (cc_gen, 'Labor', Decimal('6200'), today - timedelta(days=25)),
        (cc_demo, 'Labor', Decimal('4200'), today - timedelta(days=28)),
        (cc_fnd, 'Material', Decimal('16500'), today - timedelta(days=20)),
        (cc_fnd, 'Labor', Decimal('10800'), today - timedelta(days=18)),
        (cc_frm, 'Labor', Decimal('18500'), today - timedelta(days=10)),
        (cc_frm, 'Material', Decimal('13200'), today - timedelta(days=12)),
        (cc_elec, 'Subcontractor', Decimal('7000'), today - timedelta(days=5)),
    ]
    for cc, ct, amt, dt in cost_entries_data:
        db.session.add(CostEntry(
            project_id=proj_active.id, cost_code_id=cc.id,
            cost_type=ct, source='manual', amount=amt,
            entry_date=dt, description=f'[DEMO] {cc.name} costs',
            created_by_user_id=DEMO_USER_ID,
        ))

    # ── Estimate (for prospect) ─────────────────────────────
    estimate = Estimate(
        client_id=client_prospect.id, name='[DEMO] Chen 2BR ADU Estimate',
        status='Sent', adu_type='2BR', sqft=800,
        markup_pct=Decimal('15'), overhead_pct=Decimal('10'),
        contingency_pct=Decimal('5'),
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(estimate)
    db.session.flush()

    line_items_data = [
        (cc_gen, 'General conditions & supervision', 'LS', 1, Decimal('8500'), 80, 20, 0, 1),
        (cc_fnd, 'Concrete foundation — 800 SF slab', 'SF', 800, Decimal('22.50'), 40, 55, 5, 2),
        (cc_frm, 'Wood framing — walls, roof', 'SF', 800, Decimal('28.00'), 55, 40, 5, 3),
        (cc_roof, 'Roofing — comp shingle', 'SQ', 12, Decimal('450.00'), 45, 50, 5, 4),
        (cc_elec, 'Electrical rough + finish', 'LS', 1, Decimal('14000'), 70, 25, 5, 5),
        (cc_plmb, 'Plumbing rough + finish', 'LS', 1, Decimal('12500'), 65, 30, 5, 6),
        (cc_fin, 'Interior finishes — drywall, paint, trim', 'SF', 800, Decimal('18.00'), 50, 45, 5, 7),
    ]
    for cc, desc, unit, qty, uc, lab, mat, waste, sort in line_items_data:
        db.session.add(EstimateLineItem(
            estimate_id=estimate.id, cost_code_id=cc.id,
            description=desc, unit=unit, qty=Decimal(str(qty)),
            unit_cost=uc, labor_pct=Decimal(str(lab)),
            material_pct=Decimal(str(mat)), waste_pct=Decimal(str(waste)),
            sort_order=sort,
        ))

    # ── Accepted Estimate for active client ─────────────────
    est_accepted = Estimate(
        client_id=client_active.id, name='[DEMO] Johnson Detached ADU',
        status='Accepted', adu_type='Detached', sqft=650,
        markup_pct=Decimal('15'), overhead_pct=Decimal('10'),
        contingency_pct=Decimal('5'), accepted_at=now - timedelta(days=35),
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(est_accepted)
    db.session.flush()

    for cc, desc, unit, qty, uc, lab, mat, waste, sort in [
        (cc_gen, 'General conditions', 'LS', 1, Decimal('8500'), 80, 20, 0, 1),
        (cc_fnd, 'Foundation — 650 SF', 'SF', 650, Decimal('22.50'), 40, 55, 5, 2),
        (cc_frm, 'Framing package', 'SF', 650, Decimal('28.00'), 55, 40, 5, 3),
        (cc_elec, 'Electrical complete', 'LS', 1, Decimal('14000'), 70, 25, 5, 4),
        (cc_plmb, 'Plumbing complete', 'LS', 1, Decimal('12000'), 65, 30, 5, 5),
        (cc_fin, 'Finishes package', 'SF', 650, Decimal('18.00'), 50, 45, 5, 6),
    ]:
        db.session.add(EstimateLineItem(
            estimate_id=est_accepted.id, cost_code_id=cc.id,
            description=desc, unit=unit, qty=Decimal(str(qty)),
            unit_cost=uc, labor_pct=Decimal(str(lab)),
            material_pct=Decimal(str(mat)), waste_pct=Decimal(str(waste)),
            sort_order=sort,
        ))

    # ── Proposal + Contract (for active client) ─────────────
    proposal = Proposal(
        estimate_id=est_accepted.id, client_id=client_active.id,
        status='Accepted', share_token=secrets.token_urlsafe(32),
        cover_note='Thank you for choosing All Inclusive ADU!',
        scope_text='Complete detached ADU — 650 SF, 1 bed / 1 bath',
        validity_days=30,
        viewed_at=now - timedelta(days=33),
        accepted_at=now - timedelta(days=32),
        accepted_name='Michael Johnson',
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(proposal)
    db.session.flush()

    contract = Contract(
        proposal_id=proposal.id, client_id=client_active.id,
        estimate_id=est_accepted.id, status='Signed',
        share_token=secrets.token_urlsafe(32),
        contract_number='DEMO-2024-001',
        scope_text='Design and build a 650 SF detached ADU per accepted proposal.',
        terms_text='Standard residential construction agreement. Payment per draw schedule.',
        total_price=Decimal('172500'), retainage_pct=Decimal('10'),
        signed_at=now - timedelta(days=30),
        signed_name='Michael Johnson', signed_email='mjohnson@example.com',
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(contract)
    db.session.flush()

    # Draw schedule
    draws = [
        ('Deposit', 10, Decimal('17250'), 1),
        ('Foundation Complete', 20, Decimal('34500'), 2),
        ('Framing Complete', 25, Decimal('43125'), 3),
        ('Rough MEP', 20, Decimal('34500'), 4),
        ('Finish & Final', 25, Decimal('43125'), 5),
    ]
    draw_items = []
    for milestone, pct, amt, sort in draws:
        di = DrawScheduleItem(
            contract_id=contract.id, milestone=milestone,
            pct_of_total=Decimal(str(pct)), amount=amt,
            sort_order=sort,
        )
        db.session.add(di)
        draw_items.append(di)
    db.session.flush()

    # Mark first two draws as paid
    draw_items[0].paid_at = now - timedelta(days=29)
    draw_items[0].paid_amount = draw_items[0].amount
    draw_items[1].paid_at = now - timedelta(days=15)
    draw_items[1].paid_amount = draw_items[1].amount

    # ── Invoice (draw #3 — sent, partially paid) ────────────
    invoice = Invoice(
        contract_id=contract.id, client_id=client_active.id,
        invoice_number='DEMO-INV-003', status='Partial',
        share_token=secrets.token_urlsafe(32),
        subtotal=Decimal('43125'), retainage_pct=Decimal('10'),
        retainage_amount=Decimal('4312.50'),
        total_due=Decimal('38812.50'), amount_paid=Decimal('20000'),
        balance_due=Decimal('18812.50'),
        issued_date=today - timedelta(days=5),
        due_date=today + timedelta(days=25),
        notes='Draw #3 — Framing Complete',
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(invoice)
    db.session.flush()

    inv_li = InvoiceLineItem(
        invoice_id=invoice.id, source_type='draw',
        draw_item_id=draw_items[2].id,
        description='Draw #3 — Framing Complete',
        amount=Decimal('43125'), pct_complete=Decimal('100'),
        sort_order=1,
    )
    db.session.add(inv_li)

    payment = Payment(
        invoice_id=invoice.id, client_id=client_active.id,
        amount=Decimal('20000'), method='check', status='succeeded',
        reference='Check #4521', received_date=today - timedelta(days=2),
        note='Partial payment on Draw #3',
        recorded_by_user_id=DEMO_USER_ID,
    )
    db.session.add(payment)

    # ── Schedule (for active project) ───────────────────────
    phases_data = [
        ('Site Prep & Foundation', '#3b82f6', 1),
        ('Framing', '#f59e0b', 2),
        ('MEP Rough-In', '#8b5cf6', 3),
        ('Finishes', '#10b981', 4),
    ]
    phases = []
    for pname, color, sort in phases_data:
        ph = SchedulePhase(
            project_id=proj_active.id, name=pname,
            color=color, sort_order=sort,
        )
        db.session.add(ph)
        phases.append(ph)
    db.session.flush()

    tasks_data = [
        # (phase_idx, name, status, priority, start_offset, duration, cc)
        (0, 'Demolition & grading', 'Complete', 'High', -28, 3, cc_demo),
        (0, 'Footings & slab pour', 'Complete', 'High', -25, 5, cc_fnd),
        (0, 'Foundation inspection', 'Complete', 'Medium', -20, 1, cc_gen),
        (1, 'Wall framing', 'Complete', 'High', -19, 7, cc_frm),
        (1, 'Roof framing', 'In Progress', 'High', -12, 5, cc_frm),
        (1, 'Sheathing & WRB', 'Not Started', 'Medium', -7, 3, cc_frm),
        (2, 'Electrical rough', 'Not Started', 'High', -4, 5, cc_elec),
        (2, 'Plumbing rough', 'Not Started', 'High', -4, 5, cc_plmb),
        (2, 'MEP inspection', 'Not Started', 'Medium', 1, 1, cc_gen),
        (3, 'Drywall', 'Not Started', 'Medium', 2, 5, cc_fin),
        (3, 'Paint & trim', 'Not Started', 'Medium', 7, 4, cc_fin),
        (3, 'Flooring install', 'Not Started', 'Medium', 11, 3, cc_fin),
        (3, 'Final inspection', 'Not Started', 'High', 14, 1, cc_gen),
    ]
    for ph_idx, tname, status, priority, start_off, dur, cc in tasks_data:
        t = ScheduleTask(
            project_id=proj_active.id, phase_id=phases[ph_idx].id,
            cost_code_id=cc.id, name=tname, status=status,
            priority=priority, start_date=today + timedelta(days=start_off),
            end_date=today + timedelta(days=start_off + dur - 1),
            created_by_user_id=DEMO_USER_ID,
        )
        db.session.add(t)
        db.session.flush()
        # Assign the rep to some tasks
        if status in ('In Progress', 'Not Started') and ph_idx < 3:
            db.session.add(TaskAssignment(
                task_id=t.id, user_id=DEMO_REP_ID, role='Lead',
            ))

    # ── Daily Log ───────────────────────────────────────────
    log_entry = DailyLog(
        client_id=client_active.id, project_id=proj_active.id,
        log_date=today - timedelta(days=1), status='Final',
        crew_count=4, crew_names='Jake T., Marco R., Sam L., Tony G.',
        hours_regular=Decimal('8'), hours_overtime=Decimal('1.5'),
        work_completed='Completed wall framing on south and west elevations. Set window bucks for all openings. Started shear wall nailing.',
        weather_condition='Partly Cloudy', weather_temp_f=78,
        weather_notes='Light breeze, comfortable working conditions',
        materials_delivered='2x6 SPF lumber (40 pcs), Simpson strong-ties (1 box)',
        created_by_user_id=DEMO_REP_ID,
    )
    db.session.add(log_entry)

    # ── Change Order ────────────────────────────────────────
    co = ChangeOrder(
        client_id=client_active.id, project_id=proj_active.id,
        co_number='CO-001', title='[DEMO] Upgrade kitchen countertops to quartz',
        description='Client requested upgrade from laminate countertops to Caesarstone quartz in kitchen and bathroom.',
        status='Approved', price_to_client=Decimal('4800'),
        share_token=secrets.token_urlsafe(32),
        approved_at=now - timedelta(days=8),
        approved_name='Michael Johnson',
        created_by_user_id=DEMO_USER_ID,
    )
    db.session.add(co)
    db.session.flush()

    co_items = [
        ('Quartz countertop fabrication & install', cc_fin, 'Material', Decimal('3200')),
        ('Plumbing reconnection for undermount sink', cc_plmb, 'Labor', Decimal('850')),
        ('Template & cutout', cc_fin, 'Labor', Decimal('750')),
    ]
    for desc, cc, ct, amt in co_items:
        db.session.add(ChangeOrderItem(
            change_order_id=co.id, cost_code_id=cc.id,
            cost_type=ct, description=desc, amount=amt,
        ))

    # ── Time Entries ────────────────────────────────────────
    for days_ago in range(7):
        if days_ago in (5, 6):  # skip weekend-ish
            continue
        te = TimeEntry(
            user_id=DEMO_REP_ID, client_id=client_active.id,
            cost_code_id=cc_frm.id, date=today - timedelta(days=days_ago),
            start_time=datetime.combine(today - timedelta(days=days_ago),
                                         datetime.min.time().replace(hour=7)),
            end_time=datetime.combine(today - timedelta(days=days_ago),
                                       datetime.min.time().replace(hour=15, minute=30)),
            duration_hours=Decimal('8.00'),
            work_description=f'[DEMO] Framing — day {7 - days_ago}',
            status='approved' if days_ago > 1 else 'pending',
            approved_by_user_id=DEMO_USER_ID if days_ago > 1 else None,
            approved_at=now if days_ago > 1 else None,
        )
        db.session.add(te)

    # ── Client Activities (timeline) ────────────────────────
    activities_data = [
        ('Lead created', 'New lead from Google Ads campaign', -45),
        ('Call', 'Initial consultation call — discussed ADU goals, timeline, and budget range. Client wants rental income.', -42),
        ('Site Visit', 'Visited property, measured backyard. Good access for equipment. Zoning allows up to 800 SF.', -38),
        ('Proposal', 'Sent detailed proposal for 650 SF detached ADU. Client reviewing.', -35),
        ('Meeting', 'Reviewed proposal with client. Answered questions about timeline and finishes.', -33),
        ('Status change', 'Status changed from Prospect to Active — contract signed!', -30),
        ('Estimate accepted', 'Estimate "Johnson Detached ADU" accepted — contract value $172,500', -30),
        ('Daily Log', 'Foundation pour completed. Passed footing inspection.', -20),
    ]
    for atype, note, days_off in activities_data:
        db.session.add(ClientActivity(
            client_id=client_active.id, user_id=DEMO_USER_ID,
            activity_type=atype, note_text=note,
            activity_date=now + timedelta(days=days_off),
            next_step_description='Follow up on framing progress' if days_off == -20 else None,
            next_step_date=now + timedelta(days=days_off + 3) if days_off == -20 else None,
        ))

    # Activity for prospect
    db.session.add(ClientActivity(
        client_id=client_prospect.id, user_id=DEMO_REP_ID,
        activity_type='Call', note_text='Initial call — interested in 2BR ADU for aging parents.',
        activity_date=now - timedelta(days=5),
        next_step_description='Schedule site visit',
        next_step_date=now + timedelta(days=2),
    ))

    # ── Status Changes ──────────────────────────────────────
    db.session.add(ClientStatusChange(
        client_id=client_active.id, from_status='Lead', to_status='Prospect',
        changed_by_user_id=DEMO_REP_ID, changed_at=now - timedelta(days=38),
    ))
    db.session.add(ClientStatusChange(
        client_id=client_active.id, from_status='Prospect', to_status='Active',
        changed_by_user_id=DEMO_USER_ID, changed_at=now - timedelta(days=30),
    ))

    # ── Notifications ───────────────────────────────────────
    notifs = [
        ('task_assigned', 'Task Assigned', 'You were assigned to "Roof framing"', '/my-tasks'),
        ('payment_received', 'Payment Received', '$20,000 payment on Invoice DEMO-INV-003', None),
        ('portal_message', 'New Portal Message', 'Michael Johnson sent a message', None),
    ]
    for ntype, title, msg, link in notifs:
        db.session.add(Notification(
            user_id=DEMO_USER_ID, type=ntype,
            title=title, message=msg, link=link,
        ))

    # ── Channel Spend (for ROI report) ──────────────────────
    first_of_month = today.replace(day=1)
    cs = ChannelSpend.query.filter_by(
        lead_source_id=ls_google.id, period_month=first_of_month
    ).first()
    if not cs:
        db.session.add(ChannelSpend(
            lead_source_id=ls_google.id, amount=Decimal('2500'),
            period_month=first_of_month, note='[DEMO] Monthly Google Ads',
            created_by=DEMO_USER_ID,
        ))

    # ── Portal / Selection Data ─────────────────────────────
    cat_floor = SelectionCategory.query.filter_by(name='Flooring').first()
    if not cat_floor:
        cat_floor = SelectionCategory(name='Flooring', description='Select flooring material', sort_order=1)
        db.session.add(cat_floor)
        db.session.flush()
        db.session.add(SelectionOption(
            category_id=cat_floor.id, name='Luxury Vinyl Plank (Standard)',
            description='Waterproof LVP — included in base price',
            is_default=True, sort_order=1,
        ))
        db.session.add(SelectionOption(
            category_id=cat_floor.id, name='Engineered Hardwood (+$2,800)',
            description='Oak engineered hardwood — upgrade',
            price_delta=Decimal('2800'), sort_order=2,
        ))
        db.session.flush()

    cat_counter = SelectionCategory.query.filter_by(name='Countertops').first()
    if not cat_counter:
        cat_counter = SelectionCategory(name='Countertops', description='Kitchen & bath countertops', sort_order=2)
        db.session.add(cat_counter)
        db.session.flush()
        db.session.add(SelectionOption(
            category_id=cat_counter.id, name='Laminate (Standard)',
            description='Wilsonart HD laminate — included',
            is_default=True, sort_order=1,
        ))
        opt_quartz = SelectionOption(
            category_id=cat_counter.id, name='Quartz (+$4,800)',
            description='Caesarstone quartz — upgrade',
            price_delta=Decimal('4800'), sort_order=2,
        )
        db.session.add(opt_quartz)
        db.session.flush()

        # Client selected quartz (matches the change order)
        db.session.add(ClientSelection(
            client_id=client_active.id, category_id=cat_counter.id,
            option_id=opt_quartz.id, status='Approved',
            approved_at=now - timedelta(days=8),
        ))

    # Portal user and messages — clean up any leftover from partial seed
    ClientUser.query.filter_by(email='demo-client@example.com').delete(synchronize_session=False)

    cu = ClientUser(
        client_id=client_active.id, email='demo-client@example.com',
        name='Michael Johnson',
    )
    db.session.add(cu)
    db.session.flush()

    db.session.add(PortalMessage(
        client_id=client_active.id, sender_type='client',
        sender_name='Michael Johnson',
        message='Hi! When do you expect framing to be complete?',
        created_at=now - timedelta(days=3),
    ))
    db.session.add(PortalMessage(
        client_id=client_active.id, sender_type='staff',
        sender_name='Sarah Martinez',
        message='Hi Michael! Framing should be done by end of this week. We are right on schedule.',
        created_at=now - timedelta(days=3, hours=-2),
    ))
    db.session.add(PortalMessage(
        client_id=client_active.id, sender_type='client',
        sender_name='Michael Johnson',
        message='That\'s great to hear! Also, we decided on the quartz countertops. Can you send over the change order?',
        created_at=now - timedelta(days=2),
    ))

    # ── Burden multiplier setting ───────────────────────────
    if not AppSetting.query.get('labor_burden_multiplier'):
        db.session.add(AppSetting(key='labor_burden_multiplier', value='1.25'))

    db.session.commit()


def _cleanup_demo_data():
    """Remove all demo records from the database."""
    # Order matters for FK constraints — delete children first

    # Delete time entries by demo users
    TimeEntry.query.filter(
        TimeEntry.user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).delete(synchronize_session=False)

    # Delete cost entries by demo users
    CostEntry.query.filter(
        CostEntry.created_by_user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).delete(synchronize_session=False)

    # Delete notifications for demo users
    Notification.query.filter(
        Notification.user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).delete(synchronize_session=False)

    # Delete task assignments for demo users
    TaskAssignment.query.filter(
        TaskAssignment.user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).delete(synchronize_session=False)

    # Find demo clients by created_by user ID (more reliable than LIKE)
    demo_client_ids = [c.id for c in Client.query.filter(
        Client.created_by_user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).all()]

    if demo_client_ids:
        PortalMessage.query.filter(
            PortalMessage.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        ClientSelection.query.filter(
            ClientSelection.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        ClientUser.query.filter(
            ClientUser.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        ClientActivity.query.filter(
            ClientActivity.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        ClientStatusChange.query.filter(
            ClientStatusChange.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        DailyLog.query.filter(
            DailyLog.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Invoices, payments, line items
        demo_invoices = Invoice.query.filter(
            Invoice.client_id.in_(demo_client_ids)
        ).all()
        for inv in demo_invoices:
            Payment.query.filter_by(invoice_id=inv.id).delete(synchronize_session=False)
            InvoiceLineItem.query.filter_by(invoice_id=inv.id).delete(synchronize_session=False)
        Invoice.query.filter(
            Invoice.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Contracts, draw schedules
        demo_contracts = Contract.query.filter(
            Contract.client_id.in_(demo_client_ids)
        ).all()
        for c in demo_contracts:
            DrawScheduleItem.query.filter_by(contract_id=c.id).delete(synchronize_session=False)
        Contract.query.filter(
            Contract.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Proposals
        Proposal.query.filter(
            Proposal.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Estimates + line items
        demo_estimates = Estimate.query.filter(
            Estimate.client_id.in_(demo_client_ids)
        ).all()
        for est in demo_estimates:
            EstimateLineItem.query.filter_by(estimate_id=est.id).delete(synchronize_session=False)
        Estimate.query.filter(
            Estimate.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Change orders + items
        demo_cos = ChangeOrder.query.filter(
            ChangeOrder.client_id.in_(demo_client_ids)
        ).all()
        for co_obj in demo_cos:
            ChangeOrderItem.query.filter_by(change_order_id=co_obj.id).delete(synchronize_session=False)
        ChangeOrder.query.filter(
            ChangeOrder.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Projects (budgets, tasks, phases, cost entries)
        demo_projects = Project.query.filter(
            Project.client_id.in_(demo_client_ids)
        ).all()
        for p in demo_projects:
            Budget.query.filter_by(project_id=p.id).delete(synchronize_session=False)
            ScheduleTask.query.filter_by(project_id=p.id).delete(synchronize_session=False)
            SchedulePhase.query.filter_by(project_id=p.id).delete(synchronize_session=False)
            CostEntry.query.filter_by(project_id=p.id).delete(synchronize_session=False)
        Project.query.filter(
            Project.client_id.in_(demo_client_ids)
        ).delete(synchronize_session=False)

        # Clients
        Client.query.filter(
            Client.created_by_user_id.in_([DEMO_USER_ID, DEMO_REP_ID])
        ).delete(synchronize_session=False)

    # Also clean up any orphaned client user
    ClientUser.query.filter_by(email='demo-client@example.com').delete(synchronize_session=False)

    # Channel spend by demo user
    ChannelSpend.query.filter(
        ChannelSpend.created_by.in_([DEMO_USER_ID, DEMO_REP_ID])
    ).delete(synchronize_session=False)

    # Demo users
    User.query.filter(User.id.in_([DEMO_USER_ID, DEMO_REP_ID])).delete(
        synchronize_session=False)

    db.session.commit()


# ── Routes ──────────────────────────────────────────────────

@demo_bp.route('/start')
def start_demo():
    """Seed demo data, log in as demo supervisor, and start the guided tour."""
    try:
        _seed_demo_data()
        log.info('Demo data seeded successfully')
    except Exception as e:
        db.session.rollback()
        log.exception('Demo seed failed')
        flash(f'Demo setup failed: {e}', 'error')
        return redirect(url_for('index'))

    user = User.query.get(DEMO_USER_ID)
    if not user:
        flash('Demo setup failed — could not create demo user.', 'error')
        return redirect(url_for('index'))

    result = login_user(user)
    log.info(f'Demo login_user result: {result}, user.is_active: {user.is_active}')

    if not result:
        flash('Demo login failed — could not authenticate demo user.', 'error')
        return redirect(url_for('index'))

    session['_demo_mode'] = True
    session.pop('_demo_tour_step', None)
    session.pop('_demo_tour_page', None)

    flash('Welcome to the demo! Explore freely — hints on each page show you what to try.', 'info')
    return redirect(url_for('home'))


@demo_bp.route('/exit')
def exit_demo():
    """Leave demo mode and clean up demo data."""
    try:
        _cleanup_demo_data()
    except Exception as e:
        db.session.rollback()
        log.exception('Demo cleanup failed')
        flash(f'Demo cleanup error: {e}', 'error')
    session.pop('_demo_mode', None)
    session.pop('_demo_tour_step', None)
    session.pop('_demo_tour_page', None)
    flash('Demo data has been removed.', 'info')
    return redirect(url_for('index'))


@demo_bp.route('/tour/state')
def tour_state():
    """Return current tour state as JSON."""
    return jsonify({
        'active': session.get('_demo_mode', False),
        'step': session.get('_demo_tour_step', 0),
        'page': session.get('_demo_tour_page', 'home'),
    })


@demo_bp.route('/tour/update', methods=['POST'])
@csrf.exempt
def tour_update():
    """Update tour step/page from JS."""
    from flask import request
    data = request.get_json(silent=True) or {}
    if 'step' in data:
        session['_demo_tour_step'] = data['step']
    if 'page' in data:
        session['_demo_tour_page'] = data['page']
    return jsonify({'ok': True})
