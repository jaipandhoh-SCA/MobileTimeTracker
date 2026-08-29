from datetime import datetime, date, timezone
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
    is_external = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default='true')

    __internal_fields__ = {'hourly_rate', 'burden_multiplier'}

    time_entries = db.relationship('TimeEntry', backref='user', lazy='dynamic',
                                   foreign_keys='TimeEntry.user_id')
    active_clock = db.relationship('ActiveClock', backref='user', uselist=False)
    user_roles = db.relationship('UserRole', backref='user', lazy='dynamic',
                                 foreign_keys='UserRole.user_id')
    job_assignments = db.relationship('UserJobAssignment', backref='user', lazy='dynamic',
                                      foreign_keys='UserJobAssignment.user_id')

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

    jobsite_latitude = db.Column(db.Float, nullable=True)
    jobsite_longitude = db.Column(db.Float, nullable=True)

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

ADU_TYPES = ['Studio', '1BR', '2BR', 'Detached', 'Garage Conversion']
ESTIMATE_STATUSES = ['Draft', 'Sent', 'Accepted', 'Rejected', 'Expired']
PROPOSAL_STATUSES = ['Draft', 'Sent', 'Viewed', 'Accepted', 'Rejected', 'Expired']
CONTRACT_STATUSES = ['Draft', 'Sent', 'Signed', 'Executed', 'Voided']
CHANGE_ORDER_STATUSES = ['Draft', 'Sent', 'Approved', 'Rejected']


class Project(db.Model):
    __tablename__ = 'projects'
    __internal_fields__ = {
        'contract_value', 'total_budget', 'total_actual',
        'total_committed', 'cost_to_complete', 'budget_used_pct',
    }
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
    __internal_fields__ = '__all__'
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
    __internal_fields__ = '__all__'
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


class AssemblyItem(db.Model):
    """Maintainable cost/assembly database — unit costs for ADU construction."""
    __tablename__ = 'assembly_items'
    __internal_fields__ = {'unit_cost', 'labor_pct', 'material_pct', 'waste_pct'}
    id = db.Column(db.Integer, primary_key=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    unit = db.Column(db.String(20), nullable=False, default='EA')
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    labor_pct = db.Column(db.Numeric(5, 2), nullable=False, default=50)
    material_pct = db.Column(db.Numeric(5, 2), nullable=False, default=50)
    waste_pct = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    default_qty = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    cost_code = db.relationship('CostCode')

    __table_args__ = (
        Index('idx_assembly_cost_code', 'cost_code_id'),
    )

    @property
    def labor_cost(self):
        return (self.unit_cost * self.labor_pct / 100).quantize(Decimal('0.01'))

    @property
    def material_cost(self):
        return (self.unit_cost * self.material_pct / 100).quantize(Decimal('0.01'))


class EstimateTemplate(db.Model):
    """Reusable ADU estimate templates (Studio, 1BR, etc.)."""
    __tablename__ = 'estimate_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    adu_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    default_sqft = db.Column(db.Integer, nullable=True)
    default_markup_pct = db.Column(db.Numeric(5, 2), nullable=False, default=15)
    default_overhead_pct = db.Column(db.Numeric(5, 2), nullable=False, default=10)
    default_contingency_pct = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    items = db.relationship('EstimateTemplateItem', backref='template',
                            lazy='dynamic', cascade='all, delete-orphan',
                            order_by='EstimateTemplateItem.sort_order')


class EstimateTemplateItem(db.Model):
    """Line items preloaded into a template."""
    __tablename__ = 'estimate_template_items'
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('estimate_templates.id'), nullable=False)
    assembly_item_id = db.Column(db.Integer, db.ForeignKey('assembly_items.id'), nullable=False)
    default_qty = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    assembly_item = db.relationship('AssemblyItem')

    __table_args__ = (
        Index('idx_eti_template', 'template_id'),
    )


class Estimate(db.Model):
    """A concrete estimate for a client."""
    __tablename__ = 'estimates'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('estimate_templates.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft')
    adu_type = db.Column(db.String(50), nullable=True)
    sqft = db.Column(db.Integer, nullable=True)
    markup_pct = db.Column(db.Numeric(5, 2), nullable=False, default=15)
    overhead_pct = db.Column(db.Numeric(5, 2), nullable=False, default=10)
    contingency_pct = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    notes = db.Column(db.Text, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', backref=db.backref('estimates', lazy='dynamic'))
    template = db.relationship('EstimateTemplate')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    line_items = db.relationship('EstimateLineItem', backref='estimate',
                                lazy='dynamic', cascade='all, delete-orphan',
                                order_by='EstimateLineItem.sort_order')

    __table_args__ = (
        Index('idx_estimate_client', 'client_id'),
    )

    @property
    def subtotal(self):
        """Sum of all line item extended costs (with waste)."""
        total = Decimal('0')
        for li in self.line_items.all():
            total += li.extended_cost
        return total

    @property
    def overhead_amount(self):
        return (self.subtotal * self.overhead_pct / 100).quantize(Decimal('0.01'))

    @property
    def markup_amount(self):
        return (self.subtotal * self.markup_pct / 100).quantize(Decimal('0.01'))

    @property
    def contingency_amount(self):
        return (self.subtotal * self.contingency_pct / 100).quantize(Decimal('0.01'))

    @property
    def total(self):
        return self.subtotal + self.overhead_amount + self.markup_amount + self.contingency_amount

    @property
    def internal_cost(self):
        """Cost before markup — what it actually costs us."""
        return self.subtotal + self.overhead_amount + self.contingency_amount

    def labor_subtotal(self):
        total = Decimal('0')
        for li in self.line_items.all():
            total += li.labor_amount
        return total

    def material_subtotal(self):
        total = Decimal('0')
        for li in self.line_items.all():
            total += li.material_amount
        return total


class EstimateLineItem(db.Model):
    """A single line item on an estimate."""
    __tablename__ = 'estimate_line_items'
    __internal_fields__ = {
        'labor_pct', 'material_pct', 'waste_pct',
        'unit_cost', 'labor_amount', 'material_amount',
    }
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimates.id'), nullable=False)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=False)
    assembly_item_id = db.Column(db.Integer, db.ForeignKey('assembly_items.id'), nullable=True)
    description = db.Column(db.String(300), nullable=False)
    unit = db.Column(db.String(20), nullable=False, default='EA')
    qty = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    labor_pct = db.Column(db.Numeric(5, 2), nullable=False, default=50)
    material_pct = db.Column(db.Numeric(5, 2), nullable=False, default=50)
    waste_pct = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)

    cost_code = db.relationship('CostCode')
    assembly_item = db.relationship('AssemblyItem')

    __table_args__ = (
        Index('idx_eli_estimate', 'estimate_id'),
    )

    @property
    def base_extended(self):
        """qty * unit_cost."""
        return (self.qty * self.unit_cost).quantize(Decimal('0.01'))

    @property
    def waste_amount(self):
        return (self.base_extended * self.waste_pct / 100).quantize(Decimal('0.01'))

    @property
    def extended_cost(self):
        """qty * unit_cost * (1 + waste_pct/100)."""
        return self.base_extended + self.waste_amount

    @property
    def labor_amount(self):
        return (self.extended_cost * self.labor_pct / 100).quantize(Decimal('0.01'))

    @property
    def material_amount(self):
        return (self.extended_cost * self.material_pct / 100).quantize(Decimal('0.01'))


class Proposal(db.Model):
    """Client-facing branded proposal generated from an estimate."""
    __tablename__ = 'proposals'
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimates.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft')
    share_token = db.Column(db.String(64), unique=True, nullable=False)
    # Content overrides (if None, pulled from estimate/client)
    cover_note = db.Column(db.Text, nullable=True)
    scope_text = db.Column(db.Text, nullable=True)
    exclusions_text = db.Column(db.Text, nullable=True)
    validity_days = db.Column(db.Integer, nullable=False, default=30)
    # Tracking
    viewed_at = db.Column(db.DateTime, nullable=True)
    viewed_ip = db.Column(db.String(45), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    accepted_ip = db.Column(db.String(45), nullable=True)
    accepted_name = db.Column(db.String(200), nullable=True)
    # Storage
    pdf_storage_key = db.Column(db.String(500), nullable=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    estimate = db.relationship('Estimate', backref=db.backref('proposals', lazy='dynamic'))
    client = db.relationship('Client', backref=db.backref('proposals', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index('idx_proposal_client', 'client_id'),
        Index('idx_proposal_token', 'share_token'),
    )

    @property
    def is_expired(self):
        if not self.created_at or not self.validity_days:
            return False
        from datetime import timedelta
        return datetime.now(timezone.utc) > self.created_at.replace(tzinfo=timezone.utc) + timedelta(days=self.validity_days)

    @property
    def expires_on(self):
        if not self.created_at or not self.validity_days:
            return None
        from datetime import timedelta
        return (self.created_at + timedelta(days=self.validity_days)).date()


class Contract(db.Model):
    """Contract generated from an accepted proposal."""
    __tablename__ = 'contracts'
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposals.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimates.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft')
    share_token = db.Column(db.String(64), unique=True, nullable=False)
    # Contract content
    contract_number = db.Column(db.String(50), nullable=False)
    scope_text = db.Column(db.Text, nullable=True)
    terms_text = db.Column(db.Text, nullable=True)
    total_price = db.Column(db.Numeric(12, 2), nullable=False)
    retainage_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    # Signature
    signed_at = db.Column(db.DateTime, nullable=True)
    signed_ip = db.Column(db.String(45), nullable=True)
    signed_name = db.Column(db.String(200), nullable=True)
    signed_email = db.Column(db.String(200), nullable=True)
    signature_data = db.Column(db.Text, nullable=True)  # Base64 canvas signature
    # Storage
    pdf_storage_key = db.Column(db.String(500), nullable=True)
    signed_pdf_key = db.Column(db.String(500), nullable=True)
    # PandaDoc (stub for future integration)
    pandadoc_id = db.Column(db.String(100), nullable=True)
    pandadoc_status = db.Column(db.String(50), nullable=True)
    # Meta
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    proposal = db.relationship('Proposal', backref=db.backref('contract', uselist=False))
    client = db.relationship('Client', backref=db.backref('contracts', lazy='dynamic'))
    estimate = db.relationship('Estimate')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index('idx_contract_client', 'client_id'),
        Index('idx_contract_token', 'share_token'),
    )

    @property
    def is_signed(self):
        return self.signed_at is not None


class DrawScheduleItem(db.Model):
    """Payment/draw schedule line item on a contract."""
    __tablename__ = 'draw_schedule_items'
    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    milestone = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    pct_of_total = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_amount = db.Column(db.Numeric(12, 2), nullable=True)

    contract = db.relationship('Contract', backref=db.backref(
        'draw_schedule', lazy='dynamic', cascade='all, delete-orphan',
        order_by='DrawScheduleItem.sort_order'))

    __table_args__ = (
        Index('idx_draw_contract', 'contract_id'),
    )


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
    client_uuid = db.Column(db.String(36), nullable=True, unique=True)

    clock_in_lat = db.Column(db.Float, nullable=True)
    clock_in_lng = db.Column(db.Float, nullable=True)
    clock_out_lat = db.Column(db.Float, nullable=True)
    clock_out_lng = db.Column(db.Float, nullable=True)

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
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    clock_in_lat = db.Column(db.Float, nullable=True)
    clock_in_lng = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client = db.relationship('Client', foreign_keys=[client_id])
    cost_code = db.relationship('CostCode', foreign_keys=[cost_code_id])

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
    client_uuid = db.Column(db.String(36), nullable=True, unique=True)

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
    
    auth_role_name = db.Column(db.String(50), nullable=True)

    added_by = db.relationship('User', foreign_keys=[added_by_user_id])

    def __repr__(self):
        return f'<AuthorizedUser {self.email}>'


WEATHER_CONDITIONS = [
    'Clear', 'Partly Cloudy', 'Cloudy', 'Rain', 'Heavy Rain',
    'Wind', 'Fog', 'Hot', 'Cold', 'Snow',
]

DAILY_LOG_STATUSES = ['Draft', 'Final']


class DailyLog(db.Model):
    """Field daily log: one per client per date."""
    __tablename__ = 'daily_logs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    log_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False, default='Draft')
    # Crew on site
    crew_count = db.Column(db.Integer, nullable=True)
    crew_names = db.Column(db.Text, nullable=True)  # comma-separated or free text
    # Hours
    hours_regular = db.Column(db.Numeric(5, 2), nullable=True, default=0)
    hours_overtime = db.Column(db.Numeric(5, 2), nullable=True, default=0)
    # Work performed
    work_completed = db.Column(db.Text, nullable=True)
    # Weather
    weather_condition = db.Column(db.String(30), nullable=True)
    weather_temp_f = db.Column(db.Integer, nullable=True)
    weather_notes = db.Column(db.String(300), nullable=True)
    # Delays / issues
    delays = db.Column(db.Text, nullable=True)
    safety_incidents = db.Column(db.Text, nullable=True)
    # Visitors / inspections
    visitors = db.Column(db.Text, nullable=True)
    # Materials delivered
    materials_delivered = db.Column(db.Text, nullable=True)
    # Meta
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    # Offline sync
    client_uuid = db.Column(db.String(36), nullable=True, unique=True)

    client = db.relationship('Client', backref=db.backref(
        'daily_logs', lazy='dynamic', order_by='DailyLog.log_date.desc()'))
    project = db.relationship('Project')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    photos = db.relationship('DailyLogPhoto', backref='daily_log',
                             cascade='all, delete-orphan',
                             order_by='DailyLogPhoto.sort_order')

    __table_args__ = (
        UniqueConstraint('client_id', 'log_date', 'created_by_user_id',
                         name='uq_daily_log_client_date_user'),
        Index('idx_daily_log_client', 'client_id', 'log_date'),
        Index('idx_daily_log_date', 'log_date'),
    )

    @property
    def total_hours(self):
        return (self.hours_regular or 0) + (self.hours_overtime or 0)

    @property
    def photo_count(self):
        return len(self.photos)

    def __repr__(self):
        return f'<DailyLog {self.id} - {self.log_date}>'


class DailyLogPhoto(db.Model):
    """Photo attached to a daily log, stored in R2."""
    __tablename__ = 'daily_log_photos'
    id = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_logs.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    storage_key = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(500), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    client_visible = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client = db.relationship('Client')
    cost_code = db.relationship('CostCode')
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])

    __table_args__ = (
        Index('idx_dlp_log', 'daily_log_id'),
        Index('idx_dlp_client', 'client_id'),
    )

    def __repr__(self):
        return f'<DailyLogPhoto {self.id} - {self.file_name}>'


TASK_STATUSES = ['Not Started', 'In Progress', 'Complete', 'Blocked']
TASK_PRIORITIES = ['Low', 'Medium', 'High']

# ── Camera-first photo capture constants ────────────────────────────────────
PHOTO_CATEGORIES = [
    'progress', 'delivery', 'issue', 'safety',
    'inspection', 'before_after', 'uncategorized',
]
FIELD_ISSUE_STATUSES = ['Open', 'In Progress', 'Resolved', 'Closed']
FIELD_ISSUE_PRIORITIES = ['Low', 'Medium', 'High', 'Critical']


class FieldIssue(db.Model):
    """Lightweight field issue tracker, often created from photo capture."""
    __tablename__ = 'field_issues'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Open')
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    reported_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    assigned_to_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    client_uuid = db.Column(db.String(36), nullable=True, unique=True)

    client = db.relationship('Client', backref=db.backref('field_issues', lazy='dynamic'))
    project = db.relationship('Project')
    cost_code = db.relationship('CostCode')
    reported_by = db.relationship('User', foreign_keys=[reported_by_user_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id])
    photos = db.relationship('JobPhoto', backref='field_issue', lazy='dynamic')

    __table_args__ = (
        Index('idx_fi_client_status', 'client_id', 'status'),
        Index('idx_fi_assigned_status', 'assigned_to_user_id', 'status'),
    )

    def __repr__(self):
        return f'<FieldIssue {self.id} - {self.title}>'


class JobPhoto(db.Model):
    """Independent job photo — not tied to a daily log."""
    __tablename__ = 'job_photos'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    field_issue_id = db.Column(db.Integer, db.ForeignKey('field_issues.id'), nullable=True)
    batch_uuid = db.Column(db.String(36), nullable=True)
    category = db.Column(db.String(30), nullable=False, default='uncategorized')
    storage_key = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(500), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    taken_at = db.Column(db.DateTime, nullable=False)
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    media_uuid = db.Column(db.String(36), nullable=True, unique=True)

    client = db.relationship('Client', backref=db.backref('job_photos', lazy='dynamic'))
    project = db.relationship('Project')
    cost_code = db.relationship('CostCode')
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])

    __table_args__ = (
        Index('idx_jp_client_taken', 'client_id', 'taken_at'),
        Index('idx_jp_batch', 'batch_uuid'),
        Index('idx_jp_client_cat', 'client_id', 'category'),
        Index('idx_jp_issue', 'field_issue_id'),
    )

    def __repr__(self):
        return f'<JobPhoto {self.id} - {self.file_name}>'


class SchedulePhase(db.Model):
    """A phase/stage within a project schedule (e.g. Foundation, Framing)."""
    __tablename__ = 'schedule_phases'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    color = db.Column(db.String(7), default='#6366f1')
    client_label = db.Column(db.String(200), nullable=True)
    client_description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    project = db.relationship('Project', backref=db.backref(
        'phases', lazy='dynamic', cascade='all, delete-orphan',
        order_by='SchedulePhase.sort_order'))
    tasks = db.relationship('ScheduleTask', backref='phase',
                            cascade='all, delete-orphan',
                            order_by='ScheduleTask.sort_order')

    __table_args__ = (
        Index('idx_phase_project', 'project_id'),
    )

    def __repr__(self):
        return f'<SchedulePhase {self.id} - {self.name}>'


class ScheduleTask(db.Model):
    """A schedulable task within a project, optionally grouped into a phase."""
    __tablename__ = 'schedule_tasks'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('schedule_phases.id'), nullable=True)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    name = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Not Started')
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    sort_order = db.Column(db.Integer, default=0)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    project = db.relationship('Project', backref=db.backref(
        'tasks', lazy='dynamic', order_by='ScheduleTask.sort_order'))
    cost_code = db.relationship('CostCode')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    assignments = db.relationship('TaskAssignment', backref='task',
                                  cascade='all, delete-orphan')
    predecessors = db.relationship('TaskDependency',
                                   foreign_keys='TaskDependency.task_id',
                                   backref='task', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_task_project', 'project_id'),
        Index('idx_task_phase', 'phase_id'),
        Index('idx_task_dates', 'start_date', 'end_date'),
        Index('idx_task_status', 'status'),
    )

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    @property
    def is_overdue(self):
        if self.end_date and self.status not in ('Complete',):
            return self.end_date < date.today()
        return False

    @property
    def assignee_names(self):
        names = []
        for a in self.assignments:
            if a.user:
                names.append(a.user.display_name)
            elif a.sub_name:
                names.append(a.sub_name)
        return names

    def __repr__(self):
        return f'<ScheduleTask {self.id} - {self.name}>'


class TaskDependency(db.Model):
    """Finish-to-Start (or other) dependency between two tasks."""
    __tablename__ = 'task_dependencies'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('schedule_tasks.id'), nullable=False)
    depends_on_id = db.Column(db.Integer, db.ForeignKey('schedule_tasks.id'), nullable=False)
    dependency_type = db.Column(db.String(5), nullable=False, default='FS')

    depends_on = db.relationship('ScheduleTask', foreign_keys=[depends_on_id])

    __table_args__ = (
        UniqueConstraint('task_id', 'depends_on_id', name='uq_task_dep'),
    )


class TaskAssignment(db.Model):
    """Assigns a user or named subcontractor to a task."""
    __tablename__ = 'task_assignments'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('schedule_tasks.id'), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    sub_name = db.Column(db.String(200), nullable=True)
    role = db.Column(db.String(50), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_assignment_user', 'user_id'),
    )


class Notification(db.Model):
    """In-app notification delivered to a user."""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    message = db.Column(db.Text, nullable=True)
    link = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    user = db.relationship('User', backref=db.backref(
        'notifications', lazy='dynamic',
        order_by='Notification.created_at.desc()'))

    __table_args__ = (
        Index('idx_notif_user_read', 'user_id', 'is_read'),
    )


class NotificationPreference(db.Model):
    """Per-user notification opt-in/out flags."""
    __tablename__ = 'notification_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False, unique=True)
    task_assigned = db.Column(db.Boolean, default=True, nullable=False)
    task_changed = db.Column(db.Boolean, default=True, nullable=False)
    task_reminder = db.Column(db.Boolean, default=True, nullable=False)
    # Financial events
    invoice_created = db.Column(db.Boolean, default=True, nullable=False)
    payment_received = db.Column(db.Boolean, default=True, nullable=False)
    estimate_accepted = db.Column(db.Boolean, default=True, nullable=False)
    # Client portal events
    portal_message = db.Column(db.Boolean, default=True, nullable=False)
    selection_made = db.Column(db.Boolean, default=True, nullable=False)
    # Smart prompts
    prompt_notifications_enabled = db.Column(db.Boolean, default=True, nullable=False)
    prompt_geo_clock_in = db.Column(db.Boolean, default=True, nullable=False)
    prompt_long_clock = db.Column(db.Boolean, default=True, nullable=False)
    prompt_no_daily_log = db.Column(db.Boolean, default=True, nullable=False)
    prompt_geo_left_clocked = db.Column(db.Boolean, default=True, nullable=False)
    prompt_unattached_photos = db.Column(db.Boolean, default=True, nullable=False)
    work_start_hour = db.Column(db.Integer, default=6, nullable=False)
    work_end_hour = db.Column(db.Integer, default=19, nullable=False)

    user = db.relationship('User', backref=db.backref('notification_prefs', uselist=False))


class PromptDismissal(db.Model):
    """Tracks when a user dismisses a contextual prompt card."""
    __tablename__ = 'prompt_dismissals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    rule_key = db.Column(db.String(50), nullable=False)
    dismissed_date = db.Column(db.Date, nullable=False)
    dismissed_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        Index('idx_pd_user_rule_date', 'user_id', 'rule_key', 'dismissed_date'),
    )


DOCUMENT_FOLDERS = [
    ('plans', 'Plans & Drawings'),
    ('permits', 'Permits'),
    ('specs', 'Specs & Engineering'),
    ('contracts', 'Contracts'),
    ('photos', 'Photos'),
    ('other', 'Other'),
]

DOCUMENT_FOLDER_KEYS = [k for k, _ in DOCUMENT_FOLDERS]

PERMIT_STATUSES = [
    'Not Started', 'In Preparation', 'Submitted', 'In Review',
    'Corrections Required', 'Approved', 'Issued', 'Expired', 'Denied',
]

PERMIT_TYPES = [
    'Building Permit', 'Grading Permit', 'Electrical Permit',
    'Plumbing Permit', 'Mechanical Permit', 'Demolition Permit',
    'Encroachment Permit', 'School Fee', 'Utility Connection',
    'HOA Approval', 'Other',
]


class Document(db.Model):
    """A managed file belonging to a client, organized into folders."""
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    folder = db.Column(db.String(30), nullable=False, default='other')
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    current_version_id = db.Column(db.Integer, nullable=True)  # FK added after DocumentVersion
    is_superseded = db.Column(db.Boolean, default=False)
    superseded_by_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    visibility = db.Column(db.String(20), nullable=False, default='team')  # team, supervisor, client
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', backref=db.backref('documents', lazy='dynamic'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    superseded_by = db.relationship('Document', remote_side='Document.id', foreign_keys=[superseded_by_id])
    versions = db.relationship('DocumentVersion', backref='document',
                               lazy='dynamic', cascade='all, delete-orphan',
                               order_by='DocumentVersion.version_number.desc()')

    __table_args__ = (
        Index('idx_doc_client_folder', 'client_id', 'folder'),
    )

    @property
    def current_version(self):
        if self.current_version_id:
            return DocumentVersion.query.get(self.current_version_id)
        return self.versions.first()

    @property
    def version_count(self):
        return self.versions.count()

    @property
    def is_drawing(self):
        return self.folder == 'plans'

    @property
    def is_pdf(self):
        return self.file_name.lower().endswith('.pdf') if self.file_name else False


class DocumentVersion(db.Model):
    """A specific version/revision of a document. Never overwritten."""
    __tablename__ = 'document_versions'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False, default=1)
    storage_key = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    change_note = db.Column(db.String(500), nullable=True)
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])

    __table_args__ = (
        UniqueConstraint('document_id', 'version_number', name='uq_doc_version'),
        Index('idx_docver_doc', 'document_id'),
    )


class Permit(db.Model):
    """Permit tracking for a client's ADU project."""
    __tablename__ = 'permits'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    permit_type = db.Column(db.String(50), nullable=False)
    jurisdiction = db.Column(db.String(200), nullable=True)
    permit_number = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), nullable=False, default='Not Started')
    # Key dates
    submitted_date = db.Column(db.Date, nullable=True)
    approved_date = db.Column(db.Date, nullable=True)
    issued_date = db.Column(db.Date, nullable=True)
    expiration_date = db.Column(db.Date, nullable=True)
    # Corrections
    corrections_due_date = db.Column(db.Date, nullable=True)
    corrections_note = db.Column(db.Text, nullable=True)
    # Fees
    fee_amount = db.Column(db.Numeric(10, 2), nullable=True)
    fee_paid = db.Column(db.Boolean, default=False)
    # Notes / docs
    notes = db.Column(db.Text, nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    # Meta
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', backref=db.backref('permits', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    document = db.relationship('Document')

    __table_args__ = (
        Index('idx_permit_client', 'client_id'),
        Index('idx_permit_status', 'status'),
    )

    @property
    def is_overdue(self):
        if self.corrections_due_date and self.status == 'Corrections Required':
            return self.corrections_due_date < date.today()
        if self.expiration_date and self.status == 'Issued':
            return self.expiration_date < date.today()
        return False

    @property
    def days_in_review(self):
        if self.submitted_date and self.status in ('Submitted', 'In Review'):
            return (date.today() - self.submitted_date).days
        return None


class ChangeOrder(db.Model):
    """Change order for a client's project, wired into job costing."""
    __tablename__ = 'change_orders'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    co_number = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Draft')
    price_to_client = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # Portal / signature
    share_token = db.Column(db.String(64), unique=True, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_ip = db.Column(db.String(45), nullable=True)
    approved_name = db.Column(db.String(200), nullable=True)
    approved_email = db.Column(db.String(200), nullable=True)
    signature_data = db.Column(db.Text, nullable=True)
    # Billing
    billed = db.Column(db.Boolean, default=False, nullable=False)
    billed_at = db.Column(db.DateTime, nullable=True)
    # Meta
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    client = db.relationship('Client', backref=db.backref('change_orders', lazy='dynamic'))
    project = db.relationship('Project', backref=db.backref('change_orders', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    items = db.relationship('ChangeOrderItem', backref='change_order',
                            lazy='dynamic', cascade='all, delete-orphan',
                            order_by='ChangeOrderItem.sort_order')

    __table_args__ = (
        Index('idx_co_client', 'client_id'),
        Index('idx_co_project', 'project_id'),
        Index('idx_co_token', 'share_token'),
        Index('idx_co_billed', 'billed'),
    )

    @property
    def item_total(self):
        result = db.session.query(func.sum(ChangeOrderItem.amount)).filter(
            ChangeOrderItem.change_order_id == self.id
        ).scalar()
        return result or Decimal('0')


class ChangeOrderItem(db.Model):
    """Cost breakdown line item on a change order."""
    __tablename__ = 'change_order_items'
    id = db.Column(db.Integer, primary_key=True)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_orders.id'), nullable=False)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    cost_type = db.Column(db.String(20), nullable=False, default='Other')
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    cost_code = db.relationship('CostCode')

    __table_args__ = (
        Index('idx_coi_co', 'change_order_id'),
    )


INVOICE_STATUSES = ['Draft', 'Sent', 'Viewed', 'Paid', 'Partial', 'Overdue', 'Voided']

PAYMENT_METHODS = ['stripe', 'check', 'wire', 'cash', 'other']


class Invoice(db.Model):
    """Residential draw invoice billed against contract milestones."""
    __tablename__ = 'invoices'
    __internal_fields__ = {'stripe_payment_intent_id', 'stripe_session_id'}
    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    invoice_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft')
    share_token = db.Column(db.String(64), unique=True, nullable=False)
    # Amounts
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    retainage_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    retainage_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # Dates
    issued_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    # Notes
    notes = db.Column(db.Text, nullable=True)
    # Stripe
    stripe_payment_intent_id = db.Column(db.String(200), nullable=True)
    stripe_payment_url = db.Column(db.String(500), nullable=True)
    # Meta
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    contract = db.relationship('Contract', backref=db.backref('invoices', lazy='dynamic',
                               order_by='Invoice.created_at.desc()'))
    client = db.relationship('Client', backref=db.backref('invoices', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    line_items = db.relationship('InvoiceLineItem', backref='invoice',
                                 lazy='dynamic', cascade='all, delete-orphan',
                                 order_by='InvoiceLineItem.sort_order')
    payments = db.relationship('Payment', backref='invoice',
                                lazy='dynamic', cascade='all, delete-orphan',
                                order_by='Payment.created_at.desc()')

    __table_args__ = (
        Index('idx_inv_contract', 'contract_id'),
        Index('idx_inv_client', 'client_id'),
        Index('idx_inv_token', 'share_token'),
        Index('idx_inv_status', 'status'),
    )

    def recalculate(self):
        """Recalculate totals from line items and payments."""
        sub = sum((li.amount for li in self.line_items.all()), Decimal('0'))
        self.subtotal = sub
        ret = (sub * self.retainage_pct / 100).quantize(Decimal('0.01')) if self.retainage_pct else Decimal('0')
        self.retainage_amount = ret
        self.total_due = sub - ret
        paid = sum((p.amount for p in self.payments.filter_by(status='succeeded').all()), Decimal('0'))
        self.amount_paid = paid
        self.balance_due = self.total_due - paid
        if self.balance_due <= 0 and paid > 0:
            self.status = 'Paid'
        elif paid > 0 and self.balance_due > 0:
            self.status = 'Partial'

    @property
    def is_overdue(self):
        if self.due_date and self.status in ('Sent', 'Viewed', 'Partial'):
            return self.due_date < date.today()
        return False


class InvoiceLineItem(db.Model):
    """Line on an invoice — either a draw schedule milestone or a change order."""
    __tablename__ = 'invoice_line_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    # Source: draw or change_order
    source_type = db.Column(db.String(20), nullable=False, default='draw')
    draw_item_id = db.Column(db.Integer, db.ForeignKey('draw_schedule_items.id'), nullable=True)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_orders.id'), nullable=True)
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    pct_complete = db.Column(db.Numeric(5, 2), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    draw_item = db.relationship('DrawScheduleItem')
    change_order = db.relationship('ChangeOrder')

    __table_args__ = (
        Index('idx_ili_invoice', 'invoice_id'),
    )


class Payment(db.Model):
    """Payment against an invoice."""
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False, default='other')
    status = db.Column(db.String(20), nullable=False, default='succeeded')  # succeeded, pending, failed, refunded
    reference = db.Column(db.String(200), nullable=True)  # check #, wire ref, etc.
    # Stripe
    stripe_payment_intent_id = db.Column(db.String(200), nullable=True)
    stripe_charge_id = db.Column(db.String(200), nullable=True)
    # Deposit tracking
    is_deposit = db.Column(db.Boolean, default=False)
    # Meta
    received_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.String(500), nullable=True)
    recorded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client = db.relationship('Client', backref=db.backref('payments_received', lazy='dynamic'))
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])

    __table_args__ = (
        Index('idx_pmt_invoice', 'invoice_id'),
        Index('idx_pmt_client', 'client_id'),
        Index('idx_pmt_stripe', 'stripe_payment_intent_id'),
    )


SELECTION_STATUSES = ['Pending', 'Approved', 'Rejected']


class ClientUser(db.Model):
    """Homeowner/client login identity — completely separate from staff User."""
    __tablename__ = 'client_users'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client = db.relationship('Client', backref=db.backref('client_users', lazy='dynamic'))

    __table_args__ = (
        Index('idx_cuser_client', 'client_id'),
        Index('idx_cuser_email', 'email'),
    )


class MagicLink(db.Model):
    """One-time magic login link for client users."""
    __tablename__ = 'magic_links'
    id = db.Column(db.Integer, primary_key=True)
    client_user_id = db.Column(db.Integer, db.ForeignKey('client_users.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client_user = db.relationship('ClientUser')

    __table_args__ = (
        Index('idx_magic_token', 'token'),
    )


class SelectionCategory(db.Model):
    """Category of finish/fixture selections (e.g., Flooring, Countertops)."""
    __tablename__ = 'selection_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    late_impact = db.Column(db.Text, nullable=True)

    options = db.relationship('SelectionOption', backref='category',
                               lazy='dynamic', order_by='SelectionOption.sort_order')


class SelectionOption(db.Model):
    """A specific finish/fixture option within a category."""
    __tablename__ = 'selection_options'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('selection_categories.id'), nullable=False)
    name = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_key = db.Column(db.String(500), nullable=True)  # R2 storage key
    price_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_code_id = db.Column(db.Integer, db.ForeignKey('cost_codes.id'), nullable=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    cost_code = db.relationship('CostCode')

    __table_args__ = (
        Index('idx_selopt_category', 'category_id'),
    )


class ClientSelection(db.Model):
    """A client's choice for a selection category — links to option + approval."""
    __tablename__ = 'client_selections'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('selection_categories.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('selection_options.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_orders.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    selected_at = db.Column(db.DateTime, default=_utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    client = db.relationship('Client', backref=db.backref('selections', lazy='dynamic'))
    category = db.relationship('SelectionCategory')
    option = db.relationship('SelectionOption')
    change_order = db.relationship('ChangeOrder')

    __table_args__ = (
        UniqueConstraint('client_id', 'category_id', name='uq_client_selection_category'),
        Index('idx_csel_client', 'client_id'),
    )


class PortalMessage(db.Model):
    """Message thread between client and staff via the portal."""
    __tablename__ = 'portal_messages'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    sender_type = db.Column(db.String(10), nullable=False)   # 'client' or 'staff'
    sender_name = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    client = db.relationship('Client', backref=db.backref('portal_messages', lazy='dynamic',
                             order_by='PortalMessage.created_at'))

    __table_args__ = (
        Index('idx_pmsg_client', 'client_id'),
        Index('idx_pmsg_unread', 'client_id', 'sender_type', 'is_read'),
    )


QBO_SYNC_DIRECTIONS = ['push', 'pull', 'both']
QBO_ENTITY_TYPES = ['customer', 'invoice', 'payment', 'account', 'item']
QBO_SYNC_STATUSES = ['success', 'error', 'skipped']


class QBOToken(db.Model):
    """OAuth 2.0 tokens for QuickBooks Online — single row."""
    __tablename__ = 'qbo_tokens'
    id = db.Column(db.Integer, primary_key=True)
    realm_id = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=False)
    access_token_expires_at = db.Column(db.DateTime, nullable=False)
    refresh_token_expires_at = db.Column(db.DateTime, nullable=True)
    company_name = db.Column(db.String(200), nullable=True)
    connected_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)


class QBOMapping(db.Model):
    """Map our cost codes to QBO accounts/items.  Also customer/invoice ID links."""
    __tablename__ = 'qbo_mappings'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(30), nullable=False)     # customer, invoice, payment, cost_code
    local_id = db.Column(db.String(50), nullable=False)        # our PK (string for flexibility)
    qbo_id = db.Column(db.String(50), nullable=True)           # QBO entity ID
    qbo_sync_token = db.Column(db.String(20), nullable=True)   # QBO SyncToken for updates
    qbo_name = db.Column(db.String(300), nullable=True)        # display label from QBO
    extra = db.Column(db.Text, nullable=True)                  # JSON blob for misc data
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint('entity_type', 'local_id', name='uq_qbo_mapping'),
        Index('idx_qbo_map_type', 'entity_type'),
        Index('idx_qbo_map_qbo_id', 'qbo_id'),
    )


class QBOSyncLog(db.Model):
    """Audit trail for every sync operation."""
    __tablename__ = 'qbo_sync_logs'
    id = db.Column(db.Integer, primary_key=True)
    direction = db.Column(db.String(10), nullable=False)       # push, pull
    entity_type = db.Column(db.String(30), nullable=False)     # customer, invoice, payment
    entity_id = db.Column(db.String(50), nullable=True)        # our local ID
    qbo_id = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(20), nullable=False)          # create, update, skip, error
    status = db.Column(db.String(20), nullable=False)          # success, error, skipped
    detail = db.Column(db.Text, nullable=True)                 # error message or summary
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        Index('idx_qbo_log_time', 'created_at'),
        Index('idx_qbo_log_type', 'entity_type', 'status'),
    )


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
