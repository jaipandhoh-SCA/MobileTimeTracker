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

logging.basicConfig(level=logging.DEBUG)


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or os.environ.get("SECRET_KEY")
if not app.secret_key:
    if os.environ.get("RENDER") or os.environ.get("PRODUCTION"):
        raise RuntimeError("SESSION_SECRET environment variable is required in production")
    app.secret_key = "dev-secret-key-for-mobile-time-tracker"
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

db = SQLAlchemy(app, model_class=Base)
csrf = CSRFProtect(app)

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
    db.session.commit()
