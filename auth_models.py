"""Authorization models — Role, Permission, grants, assignments, and audit log.

Kept separate from models.py to avoid bloating that file.
"""

from datetime import datetime, timezone
from app import db
from sqlalchemy import Index, UniqueConstraint


def _utcnow():
    return datetime.now(timezone.utc)


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    is_system = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    role_permissions = db.relationship('RolePermission', backref='role', lazy='dynamic', cascade='all, delete-orphan')
    user_roles = db.relationship('UserRole', backref='role', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Role {self.name}>'


class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    codename = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Permission {self.codename}>'


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    scope = db.Column(db.String(20), nullable=False, default='ALL')

    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )


class UserRole(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=_utcnow)
    assigned_by = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
        Index('idx_userrole_user', 'user_id'),
    )


class UserPermissionGrant(db.Model):
    __tablename__ = 'user_permission_grants'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    scope = db.Column(db.String(20), nullable=False, default='ALL')

    __table_args__ = (
        UniqueConstraint('user_id', 'permission_id', name='uq_user_perm_grant'),
        Index('idx_upg_user', 'user_id'),
    )


class UserJobAssignment(db.Model):
    __tablename__ = 'user_job_assignments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=_utcnow)
    assigned_by = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', foreign_keys=[project_id], lazy='joined')

    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_user_job'),
        Index('idx_uja_user', 'user_id'),
        Index('idx_uja_project', 'project_id'),
    )


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=_utcnow, nullable=False)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.String(100), nullable=True)
    detail = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    success = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_timestamp', 'timestamp'),
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
    )

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type}:{self.entity_id}>'
