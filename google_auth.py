# Google OAuth authentication implementation
# Based on blueprint:flask_google_oauth with custom modifications for multi-user switching

import json
import os
import requests
from functools import wraps
from flask import Blueprint, redirect, request, url_for, render_template, session
from flask_login import login_user, logout_user, login_required, current_user
from oauthlib.oauth2 import WebApplicationClient
from app import db
from models import User, AuthorizedUser
from datetime import datetime

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "dummy-google-client-id")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "dummy-google-client-secret")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

client = WebApplicationClient(GOOGLE_CLIENT_ID)

google_auth = Blueprint("google_auth", __name__)


@google_auth.route("/google_login")
def login():
    """Initiate Google OAuth login with account selection prompt"""
    import secrets
    
    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Generate CSRF state token for security
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state

    # Build the authorization request URI
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        # Replacing http:// with https:// is important as the external
        # protocol must be https to match the URI whitelisted
        redirect_uri=request.base_url.replace("http://", "https://") + "/callback",
        scope=["openid", "email", "profile"],
        # CRITICAL: Force account selection every time - enables multi-user switching
        prompt="select_account",
        state=state
    )
    return redirect(request_uri)


@google_auth.route("/google_login/callback")
def callback():
    """Handle the OAuth callback from Google"""
    # Verify CSRF state token
    state = request.args.get("state")
    if not state or state != session.get('oauth_state'):
        return "Invalid state parameter - possible CSRF attack", 400
    
    # Clear the state from session
    session.pop('oauth_state', None)
    
    code = request.args.get("code")
    
    # Get Google's provider configuration
    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    token_endpoint = google_provider_cfg["token_endpoint"]

    # Exchange authorization code for access token
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        # Replacing http:// with https:// is important as the external
        # protocol must be https to match the URI whitelisted
        authorization_response=request.url.replace("http://", "https://"),
        redirect_url=request.base_url.replace("http://", "https://"),
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    # Parse the tokens
    client.parse_request_body_response(json.dumps(token_response.json()))

    # Get user info from Google
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    userinfo = userinfo_response.json()
    
    # Verify email
    if not userinfo.get("email_verified"):
        return "User email not available or not verified by Google.", 400

    user_email = userinfo["email"]
    user_sub = userinfo["sub"]  # Google's unique user ID
    users_first_name = userinfo.get("given_name", "")
    users_last_name = userinfo.get("family_name", "")
    profile_picture = userinfo.get("picture", "")

    # CRITICAL: Look up user by EMAIL first to preserve existing data
    user = User.query.filter_by(email=user_email).first()
    
    if user is None:
        # New user - check authorization
        user_count = User.query.count()
        
        if user_count == 0:
            # First user automatically becomes supervisor
            pass
        else:
            # Check if user is in AuthorizedUser list
            authorized = AuthorizedUser.query.filter_by(email=user_email).first()
            if not authorized:
                # User not authorized
                return redirect(url_for('google_auth.access_denied'))
        
        # Create new user with Google sub as ID
        user = User()
        user.id = user_sub
        user.email = user_email
        user.first_name = users_first_name
        user.last_name = users_last_name
        user.profile_image_url = profile_picture
        
        # Set role based on authorization or first user
        if user_count == 0:
            user.role = 'supervisor'
        else:
            authorized_user = AuthorizedUser.query.filter_by(email=user_email).first()
            if authorized_user:
                user.role = authorized_user.role
        
        # Set last_login timestamp for new users
        user.last_login = datetime.utcnow()
        
        db.session.add(user)
        db.session.commit()
    else:
        # Existing user found by email - update last login and profile picture
        user.last_login = datetime.utcnow()
        if profile_picture and not user.profile_image_url:
            user.profile_image_url = profile_picture
        db.session.commit()

    # Log the user in
    login_user(user)
    
    # Honor the next_url if it was set
    next_url = session.pop("next_url", None)
    if next_url:
        return redirect(next_url)
    
    return redirect(url_for("index"))


@google_auth.route("/logout")
@login_required
def logout():
    """Logout the user and redirect to landing page"""
    logout_user()
    session.clear()
    return redirect(url_for("index"))


@google_auth.route("/access_denied")
def access_denied():
    """Show access denied page for unauthorized users"""
    return render_template("access_denied.html"), 403


@google_auth.route("/dev_login")
def dev_login():
    """Bypass Google login for development and log in as a supervisor"""
    # Look for an existing supervisor or dev user
    user = User.query.filter_by(role='supervisor').first()
    
    if user is None:
        # Create a new dev admin user
        user = User()
        user.id = "dev_admin_sub"
        user.email = "admin@example.com"
        user.first_name = "Dev"
        user.last_name = "Admin"
        user.role = "supervisor"
        user.profile_image_url = ""
        user.last_login = datetime.utcnow()
        db.session.add(user)
        db.session.commit()
        
        # Also ensure this user is in the AuthorizedUser list so they are fully valid
        authorized = AuthorizedUser.query.filter_by(email="admin@example.com").first()
        if not authorized:
            authorized = AuthorizedUser()
            authorized.email = "admin@example.com"
            authorized.role = "supervisor"
            db.session.add(authorized)
            db.session.commit()
    else:
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
    login_user(user)
    return redirect(url_for("home"))


# Decorators for route protection
def require_login(f):
    """Decorator to require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # Save the URL they were trying to access
            session["next_url"] = get_next_navigation_url(request)
            return redirect(url_for('google_auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def require_supervisor(f):
    """Decorator to require user to be logged in as supervisor"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            session["next_url"] = get_next_navigation_url(request)
            return redirect(url_for('google_auth.login'))
        
        if not current_user.is_supervisor:
            return render_template("403.html"), 403
        
        return f(*args, **kwargs)
    return decorated_function


def get_next_navigation_url(request):
    """Helper to determine the next URL to redirect to after login"""
    is_navigation_url = request.headers.get(
        'Sec-Fetch-Mode') == 'navigate' and request.headers.get(
            'Sec-Fetch-Dest') == 'document'
    if is_navigation_url:
        return request.url
    return request.referrer or request.url
