from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
import os
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

load_dotenv('.env.local')
load_dotenv('.env')

_log_level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logging.basicConfig(level=_log_level)


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
_secret = os.environ.get("SESSION_SECRET")
if not _secret:
    raise RuntimeError("SESSION_SECRET environment variable is required")
app.secret_key = _secret
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    'pool_pre_ping': True,
    "pool_recycle": 300,
}
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png', 'xls', 'xlsx', 'csv'}

# Needs Attention thresholds (days)
app.config['STALE_AMBER_DAYS'] = 14
app.config['STALE_RED_DAYS'] = 28
app.config['ALLOW_DEV_LOGIN'] = os.environ.get('ALLOW_DEV_LOGIN', '') == 'true'

db = SQLAlchemy(app, model_class=Base)
csrf = CSRFProtect(app)

# Register custom Jinja2 filters
app.jinja_env.filters['zip'] = lambda a, b: list(zip(a, b))

# Initialize Flask-Login
login_manager = LoginManager(app)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(user_id)

with app.app_context():
    import models
    db.create_all()
    logging.info("Database tables created")

    # Auto-migrate: add lead_source_id and source_detail to clients if missing
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    client_cols = [c['name'] for c in inspector.get_columns('clients')]
    if 'lead_source_id' not in client_cols:
        db.session.execute(text('ALTER TABLE clients ADD COLUMN lead_source_id INTEGER REFERENCES lead_sources(id)'))
        logging.info("Added lead_source_id column to clients")
    if 'source_detail' not in client_cols:
        db.session.execute(text('ALTER TABLE clients ADD COLUMN source_detail VARCHAR(500)'))
        logging.info("Added source_detail column to clients")
    if 'ghl_contact_id' not in client_cols:
        db.session.execute(text('ALTER TABLE clients ADD COLUMN ghl_contact_id VARCHAR(100) UNIQUE'))
        logging.info("Added ghl_contact_id column to clients")

    # Auto-migrate: add hourly_rate to users and authorized_users if missing
    user_cols = [c['name'] for c in inspector.get_columns('users')]
    if 'hourly_rate' not in user_cols:
        db.session.execute(text('ALTER TABLE users ADD COLUMN hourly_rate NUMERIC(8, 2) DEFAULT 0'))
        logging.info("Added hourly_rate column to users")

    auth_user_cols = [c['name'] for c in inspector.get_columns('authorized_users')]
    if 'hourly_rate' not in auth_user_cols:
        db.session.execute(text('ALTER TABLE authorized_users ADD COLUMN hourly_rate NUMERIC(8, 2) DEFAULT 0'))
        logging.info("Added hourly_rate column to authorized_users")


    # Auto-migrate: add payroll/job-costing columns to time_entries if missing
    te_cols = [c['name'] for c in inspector.get_columns('time_entries')]
    if 'cost_code_id' not in te_cols:
        db.session.execute(text('ALTER TABLE time_entries ADD COLUMN cost_code_id INTEGER REFERENCES cost_codes(id)'))
        logging.info("Added cost_code_id column to time_entries")
    if 'status' not in te_cols:
        db.session.execute(text("ALTER TABLE time_entries ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"))
        logging.info("Added status column to time_entries")
    if 'rejection_reason' not in te_cols:
        db.session.execute(text('ALTER TABLE time_entries ADD COLUMN rejection_reason TEXT'))
        logging.info("Added rejection_reason column to time_entries")
    if 'approved_by_user_id' not in te_cols:
        db.session.execute(text('ALTER TABLE time_entries ADD COLUMN approved_by_user_id VARCHAR REFERENCES users(id)'))
        logging.info("Added approved_by_user_id column to time_entries")
    if 'approved_at' not in te_cols:
        db.session.execute(text('ALTER TABLE time_entries ADD COLUMN approved_at TIMESTAMP'))
        logging.info("Added approved_at column to time_entries")

    db.session.commit()

    # Register demo blueprint
    from demo import demo_bp
    app.register_blueprint(demo_bp)
