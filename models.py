from datetime import datetime
from decimal import Decimal
from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, Index


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    time_entries = db.relationship('TimeEntry', backref='user', lazy='dynamic')
    active_clock = db.relationship('ActiveClock', backref='user', uselist=False)

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


class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)


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
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    assigned_to_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    
    gdrive_client_folder_id = db.Column(db.String(255), nullable=True)
    gdrive_property_images_id = db.Column(db.String(255), nullable=True)
    gdrive_documents_id = db.Column(db.String(255), nullable=True)
    gdrive_contracts_id = db.Column(db.String(255), nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id])
    time_entries = db.relationship('TimeEntry', backref='client', lazy='dynamic')
    activities = db.relationship('ClientActivity', backref='client', lazy='dynamic', order_by='ClientActivity.activity_date.desc()')
    property_images = db.relationship('PropertyImage', backref='client', lazy='dynamic', order_by='PropertyImage.created_at.desc()', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Client {self.name}>'


class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_hours = db.Column(db.Numeric(5, 2), nullable=True)
    work_description = db.Column(db.Text, nullable=False)
    is_manual = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_user_date', 'user_id', 'date'),
        Index('idx_client_date', 'client_id', 'date'),
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    gdrive_file_id = db.Column(db.String(255), nullable=True)
    gdrive_web_view_link = db.Column(db.String(500), nullable=True)
    uploaded_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_user_id])
    
    __table_args__ = (
        Index('idx_client_images', 'client_id'),
    )
    
    def __repr__(self):
        return f'<PropertyImage {self.id} - {self.file_name}>'


class AuthorizedUser(db.Model):
    __tablename__ = 'authorized_users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False, default='rep')
    hourly_rate = db.Column(db.Numeric(8, 2), nullable=True, default=0)
    added_by_user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    added_by = db.relationship('User', foreign_keys=[added_by_user_id])
    
    def __repr__(self):
        return f'<AuthorizedUser {self.email}>'
