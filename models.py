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

    time_entries = db.relationship('TimeEntry', backref='user', lazy='dynamic',
                                   foreign_keys='TimeEntry.user_id')
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

ADU_TYPES = ['Studio', '1BR', '2BR', 'Detached', 'Garage Conversion']
ESTIMATE_STATUSES = ['Draft', 'Sent', 'Accepted', 'Rejected', 'Expired']
PROPOSAL_STATUSES = ['Draft', 'Sent', 'Viewed', 'Accepted', 'Rejected', 'Expired']
CONTRACT_STATUSES = ['Draft', 'Sent', 'Signed', 'Executed', 'Voided']


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


class AssemblyItem(db.Model):
    """Maintainable cost/assembly database — unit costs for ADU construction."""
    __tablename__ = 'assembly_items'
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
