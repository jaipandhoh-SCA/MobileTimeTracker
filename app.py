from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
import os
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

logging.basicConfig(level=logging.DEBUG)


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
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
