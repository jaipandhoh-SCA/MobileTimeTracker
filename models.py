from datetime import datetime, timezone
from decimal import Decimal
from app import db
from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.sql import func


def _utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=True)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='rep')
    hourly_rate = db.Column(db.Numeric(8, 2), nullable=True, default=0)
    burden_multiplier = db.Column(db.Numeric(5, 4), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    time_entries = db.relationship('TimeEntry', backref='user', lazy='dynamic')
    active_clock = db.relationship('ActiveClock', backref='user', uselist=False)

    def effective_burden_multiplier(self):
        if self.burden_multiplier is not None:
            return self.burden_multiplier
        val = AppSetting.get('labor_burden_multiplier', '1.25')
        return Decimal(val)

    @property
    def is_supervisor(self):
        return self.role == 'supervisor'

    @property
    def display_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.email:
            return self.email
        return "User"


class LeadSource(db.Model):
    __tablename__ = 'lead_sources'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    channel_type = db.Column(db.String(50), nullable=False)  # paid_ads, organic_social, website, phone, referral, other
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    CHANNEL_TYPES = ['paid_ads', 'organic_social', 'website', 'phone', 'referral', 'other']

    def __repr__(self):
        return f'<LeadSource {self.name}>'


class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    contact_name = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Lead')
    opportunity_value = db.Column(db.Numeric(12, 2), nullable=True, default=0)
    final_contract_value = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    assigned_to_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    
    lot_sqft = db.Column(db.String(50), nullable=True)
    sqft = db.Column(db.String(50), nullable=True)
    existing_sqft = db.Column(db.String(50), nullable=True)
    residential_zoning = db.Column(db.String(100), nullable=True)
    type_of_adu = db.Column(db.String(100), nullable=True)
    desired_adu_sqft = db.Column(db.String(50), nullable=True)
    number_of_bed = db.Column(db.String(20), nullable=True)
    number_of_bath = db.Column(db.String(20), nullable=True)
    style = db.Column(db.String(200), nullable=True)
    key_features = db.Column(db.Text, nullable=True)
    max_budget = db.Column(db.Numeric(12, 2), nullable=True)
    financing_option = db.Column(db.String(50), nullable=True)
    original_property_value = db.Column(db.Numeric(12, 2), nullable=True)
    expected_roi = db.Column(db.Numeric(12, 2), nullable=True)
    value_increase = db.Column(db.Numeric(12, 2), nullable=True)
    new_property_value = db.Column(db.Numeric(12, 2), nullable=True)
    estimated_start_date = db.Column(db.Date, nullable=True)
    estimated_end_date = db.Column(db.Date, nullable=True)
    permitting_status = db.Column(db.String(50), nullable=True)
    
    storage_prefix = db.Column(db.String(500), nullable=True)

    ghl_contact_id = db.Column(db.String(100), nullable=True, unique=True, index=True)

    lead_source_id = db.Column(db.Integer, db.ForeignKey('lead_sources.id'), nullable=True)
    source_detail = db.Column(db.String(500), nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id])
    lead_source = db.relationship('LeadSource', backref='clients')
    time_entries = db.relationship('TimeEntry', backref='client', lazy='dynamic')
    activities = db.relationship('ClientActivity', backref='client', lazy='dynamic', order_by='ClientActivity.activity_date.desc()')
    property_images = db.relationship('PropertyImage', backref='client', lazy='dynamic', order_by='PropertyImage.created_at.desc()', cascade='all, delete-orphan')
    projects = db.relationship('Project', backref='client', lazy='dynamic', order_by='Project.created_at')

    def default_project(self):
        """Return the default project, creating one if none exists."""
        proj = Project.query.filter_by(client_id=self.id, is_default=True).first()
        if proj is None:
            proj = Project(
                client_id=self.id,
                name=self.name,
                is_default=True,
                contract_value=self.final_contract_value,
                status='Planning',
            )
            db.session.add(proj)
            db.session.flush()
        return proj

    @property
    def total_contract_value(self):
        """Sum of all project contract values — the authoritative total."""
        result = db.session.query(func.sum(Project.contract_value)).filter(
            Project.client_id == self.id
        ).scalar()
        return result or Decimal('0')

    def __repr__(self):
        return f'<Client {self.name}>'


COST_TYPES = ['Labor', 'Material', 'Subcontractor', 'Equipment', 'Other']
PROJECT_STATUSES = ['Planning', 'Permitted', 'In Progress', 'Completed', 'On Hold']
COST_SOURCES = ['time', 'payroll', 'po', 'invoice', 'manual']


class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    contract_value = db.Column(db.Numeric(12, 2), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Planning')
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    budgets = db.relationship('Budget', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    cost_entries = db.relationship('CostEntry', backref='project', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_project_client', 'client_id'),
    )

    @property
    def total_budget(self):
        result = db.session.query(func.sum(Budget.amount)).filter(
            Budget.project_id == self.id
        ).scalar()
        return result or Decimal('0')

    @property
    def total_actual(self):
        result = db.session.query(func.sum(CostEntry.amount)).filter(
            CostEntry.project_id == self.id,
            CostEntry.committed.is_(False),
        ).scalar()
        return result or Decimal('0')

    @property
    def total_committed(self):
        result = db.session.query(func.sum(CostEntry.amount)).filter(
            CostEntry.project_id == self.id,
            CostEntry.committed.is_(True),
        ).scalar()
        return result or Decimal('0')

    @property
    def cost_to_complete(self):
        return self.total_budget - self.total_actual - self.total_committed

    @property
    def budget_used_pct(self):
        budget = self.total_budget
        if not budget:
            return Decimal('0')
        return (self.total_actual / budget * 100).quantize(Decimal('0.1'))

    def __repr__(self):
        return f'<Project {self.id} - {self.name}>'


class CostCode(db.Model):
    __tablename__ = 'cost_codes'
    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    default_cost_type = db.Column(db.String(20), nullable=False, default='Other')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    children = db.relationship('CostCode', backref=db.backref('parent', remote_side='CostCode.id'), lazy='dynamic')

    def __repr__(self):
        return f'<CostCode {self.code} - {self.name}>'


class Budget(db.Model):
    __tablename__ = 'budgets'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=False)
    cost_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    cost_code = db.relationship('CostCode')

    __table_args__ = (
        UniqueConstraint('project_id', 'cost_code_id', 'cost_type', name='uq_budget_project_code_type'),
        Index('idx_budget_project', 'project_id'),
    )

    def __repr__(self):
        return f'<Budget {self.id} - {self.cost_type} ${self.amount}>'


class CostEntry(db.Model):
    __tablename__ = 'cost_entries'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=False)
    cost_type = db.Column(db.String(20), nullable=False, server_default='Labor')
    source = db.Column(db.String(20), nullable=False, default='manual')
    time_entry_id = db.Column(db.Integer, db.ForeignKey('time_entries.id'), unique=True, nullable=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    raw_hours = db.Column(db.Numeric(5, 2), nullable=True)
    hourly_rate = db.Column(db.Numeric(8, 2), nullable=True)
    burden_multiplier = db.Column(db.Numeric(5, 4), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    entry_date = db.Column(db.Date, nullable=False)
    source_ref_type = db.Column(db.String(50), nullable=True)
    source_ref_id = db.Column(db.Integer, nullable=True)
    committed = db.Column(db.Boolean, default=False, nullable=False)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    cost_code = db.relationship('CostCode')
    employee = db.relationship('User', foreign_keys=[user_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    time_entry = db.relationship('TimeEntry', backref=db.backref('cost_entry', uselist=False))

    __table_args__ = (
        Index('idx_cost_entry_project', 'project_id', 'cost_code_id'),
        Index('idx_cost_entry_date', 'project_id', 'entry_date'),
        Index('idx_cost_entry_source', 'source_ref_type', 'source_ref_id'),
    )

    @classmethod
    def upsert_for_time_entry(cls, time_entry_id, **kwargs):
        """Insert or update a cost entry keyed by time_entry_id (unique).

        If an entry for this time_entry already exists, update it.
        Otherwise create a new one. Returns the CostEntry.
        """
        entry = cls.query.filter_by(time_entry_id=time_entry_id).first()
        if entry:
            for k, v in kwargs.items():
                setattr(entry, k, v)
        else:
            entry = cls(time_entry_id=time_entry_id, **kwargs)
            db.session.add(entry)
        return entry

    def __repr__(self):
        return f'<CostEntry {self.id} - {self.source} ${self.amount}>'


class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_hours = db.Column(db.Numeric(5, 2), nullable=True)
    work_description = db.Column(db.Text, nullable=False)
    is_manual = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), nullable=False, server_default='pending')
    rejection_reason = db.Column(db.Text, nullable=True)
    approved_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    cost_code = db.relationship('CostCode')
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id])

    __table_args__ = (
        Index('idx_user_date', 'user_id', 'date'),
        Index('idx_client_date', 'client_id', 'date'),
        Index('idx_te_status', 'status', 'date'),
    )

    def __repr__(self):
        return f'<TimeEntry {self.id} - {self.user_id} - {self.duration_hours}h>'


class ActiveClock(db.Model):
    __tablename__ = 'active_clocks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), unique=True, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    break_15_taken = db.Column(db.Boolean, default=False)
    lunch_taken = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f'<ActiveClock {self.user_id} - {self.start_time}>'


class ClientActivity(db.Model):
    __tablename__ = 'client_activities'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    note_text = db.Column(db.Text, nullable=False)
    activity_date = db.Column(db.DateTime, nullable=False)
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    next_step_description = db.Column(db.Text, nullable=True)
    next_step_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_client_activity', 'client_id', 'activity_date'),
    )

    def __repr__(self):
        return f'<ClientActivity {self.id} - {self.activity_type}>'


class PropertyImage(db.Model):
    __tablename__ = 'property_images'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(500), nullable=True)
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    
    __table_args__ = (
        Index('idx_client_images', 'client_id'),
    )
    
    def __repr__(self):
        return f'<PropertyImage {self.id} - {self.file_name}>'


class ClientStatusChange(db.Model):
    __tablename__ = 'client_status_changes'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    from_status = db.Column(db.String(20), nullable=True)  # null for initial creation
    to_status = db.Column(db.String(20), nullable=False)
    changed_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    client = db.relationship('Client', backref=db.backref('status_changes', lazy='dynamic', order_by='ClientStatusChange.changed_at'))
    changed_by = db.relationship('User', foreign_keys=[changed_by_user_id])

    __table_args__ = (
        Index('idx_status_change_client', 'client_id', 'changed_at'),
    )

    def __repr__(self):
        return f'<ClientStatusChange {self.from_status} -> {self.to_status}>'


class ChannelSpend(db.Model):
    __tablename__ = 'channel_spend'
    id = db.Column(db.Integer, primary_key=True)
    lead_source_id = db.Column(db.Integer, db.ForeignKey('lead_sources.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    period_month = db.Column(db.Date, nullable=False)  # always first of month
    note = db.Column(db.String(500), nullable=True)
    created_by = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    lead_source = db.relationship('LeadSource', backref='spend_entries')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        Index('idx_spend_month_source', 'period_month', 'lead_source_id'),
    )

    def __repr__(self):
        return f'<ChannelSpend {self.id} - {self.lead_source_id} - ${self.amount}>'


class AuthorizedUser(db.Model):
    __tablename__ = 'authorized_users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False, default='rep')
    hourly_rate = db.Column(db.Numeric(8, 2), nullable=True, default=0)
    added_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    
    added_by = db.relationship('User', foreign_keys=[added_by_user_id])
    
    def __repr__(self):
        return f'<AuthorizedUser {self.email}>'


class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        from app import db as _db
        row = cls.query.get(key)
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value)
            _db.session.add(row)
        _db.session.commit()
        return row

    def __repr__(self):
        return f'<AppSetting {self.key}>'
