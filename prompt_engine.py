"""Contextual prompt engine — evaluates rules and surfaces action cards."""

from datetime import datetime, date, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, List

from app import db
from models import (
    ActiveClock, Client, TimeEntry, DailyLog, DailyLogPhoto,
    Notification, NotificationPreference, AppSetting,
)
from utils import haversine, PACIFIC_TZ

# ── Rule keys (priority order) ──────────────────────────────────────
RULE_GEO_CLOCK_IN = 'geo_clock_in'
RULE_LONG_CLOCK = 'long_clock'
RULE_NO_DAILY_LOG = 'no_daily_log'
RULE_GEO_LEFT_CLOCKED = 'geo_left_clocked'
RULE_UNATTACHED_PHOTOS = 'unattached_photos'

ALL_RULES = [
    RULE_GEO_CLOCK_IN,
    RULE_LONG_CLOCK,
    RULE_NO_DAILY_LOG,
    RULE_GEO_LEFT_CLOCKED,
    RULE_UNATTACHED_PHOTOS,
]

# Maps rule_key → NotificationPreference column name
_PREF_COLS = {
    RULE_GEO_CLOCK_IN: 'prompt_geo_clock_in',
    RULE_LONG_CLOCK: 'prompt_long_clock',
    RULE_NO_DAILY_LOG: 'prompt_no_daily_log',
    RULE_GEO_LEFT_CLOCKED: 'prompt_geo_left_clocked',
    RULE_UNATTACHED_PHOTOS: 'prompt_unattached_photos',
}

MAX_PROMPTS = 2
WEEKLY_DISMISS_CAP = 2
LONG_CLOCK_SECONDS = 36000  # 10 hours


@dataclass
class PromptContext:
    user_id: str
    now_utc: datetime
    today_pacific: date
    lat: Optional[float] = None
    lng: Optional[float] = None
    photos_taken_today: int = 0
    is_supervisor: bool = False


@dataclass
class PromptResult:
    rule_key: str
    title: str
    message: str
    action_url: str
    action_label: str
    icon: str  # 'clock', 'log', 'photo'

    def to_dict(self):
        return {
            'rule_key': self.rule_key,
            'title': self.title,
            'message': self.message,
            'action_url': self.action_url,
            'action_label': self.action_label,
            'icon': self.icon,
        }


def _get_or_create_prefs(user_id):
    prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.session.add(prefs)
        db.session.commit()
    return prefs


def _monday_of_week(d):
    return d - timedelta(days=d.weekday())


def evaluate_prompts(user_id, lat=None, lng=None, photos_taken_today=0,
                     is_supervisor=False):
    """Main entry point — returns list of prompt dicts (max 2)."""
    from models import PromptDismissal

    now_utc = datetime.now(timezone.utc)
    now_pacific = now_utc.astimezone(PACIFIC_TZ)
    today_pacific = now_pacific.date()

    prefs = _get_or_create_prefs(user_id)

    # Working-hours gate
    work_start = getattr(prefs, 'work_start_hour', 6) or 6
    work_end = getattr(prefs, 'work_end_hour', 19) or 19
    if now_pacific.hour < work_start or now_pacific.hour >= work_end:
        return []

    # Today's dismissals
    dismissed_today = set(
        r[0] for r in db.session.query(PromptDismissal.rule_key)
        .filter_by(user_id=user_id, dismissed_date=today_pacific).all()
    )

    # This week's dismissal counts
    monday = _monday_of_week(today_pacific)
    weekly_counts = dict(
        db.session.query(PromptDismissal.rule_key, db.func.count())
        .filter(
            PromptDismissal.user_id == user_id,
            PromptDismissal.dismissed_date >= monday,
        )
        .group_by(PromptDismissal.rule_key).all()
    )

    ctx = PromptContext(
        user_id=user_id,
        now_utc=now_utc,
        today_pacific=today_pacific,
        lat=lat,
        lng=lng,
        photos_taken_today=photos_taken_today,
        is_supervisor=is_supervisor,
    )

    evaluators = [
        (RULE_GEO_CLOCK_IN, _eval_geo_clock_in),
        (RULE_LONG_CLOCK, _eval_long_clock),
        (RULE_NO_DAILY_LOG, _eval_no_daily_log),
        (RULE_GEO_LEFT_CLOCKED, _eval_geo_left_clocked),
        (RULE_UNATTACHED_PHOTOS, _eval_unattached_photos),
    ]

    results = []
    for rule_key, evaluator in evaluators:
        if rule_key in dismissed_today:
            continue
        if weekly_counts.get(rule_key, 0) >= WEEKLY_DISMISS_CAP:
            continue
        pref_col = _PREF_COLS.get(rule_key)
        if pref_col and not getattr(prefs, pref_col, True):
            continue

        result = evaluator(ctx)
        if result:
            results.append(result)
            if len(results) >= MAX_PROMPTS:
                break

    return [r.to_dict() for r in results]


# ── Rule evaluators ──────────────────────────────────────────────────

def _eval_geo_clock_in(ctx):
    """Near a jobsite but not clocked in → suggest clock-in."""
    if ctx.lat is None or ctx.lng is None:
        return None

    active = ActiveClock.query.filter_by(user_id=ctx.user_id).first()
    if active:
        return None

    radius = float(AppSetting.get('clock_gps_radius_meters', '150'))

    if ctx.is_supervisor:
        clients = Client.query.filter(
            Client.status.in_(['Active', 'In Progress']),
            Client.jobsite_latitude.isnot(None),
            Client.jobsite_longitude.isnot(None),
        ).all()
    else:
        from auth_models import UserJobAssignment
        assigned_project_ids = [
            a.project_id for a in UserJobAssignment.query.filter_by(user_id=ctx.user_id).all()
        ]
        if assigned_project_ids:
            from models import Project
            assigned_client_ids = [
                p.client_id for p in Project.query.filter(
                    Project.id.in_(assigned_project_ids)
                ).all()
            ]
            clients = Client.query.filter(
                Client.id.in_(assigned_client_ids),
                Client.jobsite_latitude.isnot(None),
                Client.jobsite_longitude.isnot(None),
            ).all()
        else:
            clients = Client.query.filter(
                Client.status.in_(['Active', 'In Progress']),
                Client.jobsite_latitude.isnot(None),
                Client.jobsite_longitude.isnot(None),
            ).all()

    nearest = None
    nearest_dist = float('inf')
    for c in clients:
        dist = haversine(ctx.lat, ctx.lng, c.jobsite_latitude, c.jobsite_longitude)
        if dist <= radius and dist < nearest_dist:
            nearest = c
            nearest_dist = dist

    if nearest:
        return PromptResult(
            rule_key=RULE_GEO_CLOCK_IN,
            title=f"Clock in at {nearest.name}?",
            message=f"You're {int(nearest_dist)}m from the jobsite.",
            action_url='/clock',
            action_label='Clock In',
            icon='clock',
        )
    return None


def _eval_long_clock(ctx):
    """Clocked in for 10+ hours → nudge to check."""
    active = ActiveClock.query.filter_by(user_id=ctx.user_id).first()
    if not active:
        return None

    elapsed = (ctx.now_utc - active.start_time.replace(tzinfo=timezone.utc)).total_seconds()
    if elapsed < LONG_CLOCK_SECONDS:
        return None

    hours = round(elapsed / 3600, 1)
    return PromptResult(
        rule_key=RULE_LONG_CLOCK,
        title="Still on site?",
        message=f"You've been clocked in for {hours}h.",
        action_url='/clock',
        action_label='Review',
        icon='clock',
    )


def _eval_no_daily_log(ctx):
    """Worked today but no daily log → suggest filling one out."""
    active = ActiveClock.query.filter_by(user_id=ctx.user_id).first()
    if active:
        return None  # still working

    client_ids = [
        r[0] for r in db.session.query(TimeEntry.client_id).filter(
            TimeEntry.user_id == ctx.user_id,
            TimeEntry.date == ctx.today_pacific,
            TimeEntry.client_id.isnot(None),
        ).distinct().all()
    ]

    for cid in client_ids:
        existing = DailyLog.query.filter_by(
            client_id=cid,
            log_date=ctx.today_pacific,
            created_by_user_id=ctx.user_id,
        ).first()
        if not existing:
            client = Client.query.get(cid)
            name = client.name if client else 'the jobsite'
            return PromptResult(
                rule_key=RULE_NO_DAILY_LOG,
                title=f"Wrap up the day at {name}?",
                message="You worked here today but haven't filled out a daily log.",
                action_url=f'/daily-logs/field/{cid}',
                action_label='Log Now',
                icon='log',
            )
    return None


def _eval_geo_left_clocked(ctx):
    """Left the jobsite while still clocked in → suggest clock-out."""
    if ctx.lat is None or ctx.lng is None:
        return None

    active = ActiveClock.query.filter_by(user_id=ctx.user_id).first()
    if not active or not active.client_id:
        return None

    client = Client.query.get(active.client_id)
    if not client or not client.jobsite_latitude or not client.jobsite_longitude:
        return None

    radius = float(AppSetting.get('clock_gps_radius_meters', '150'))
    dist = haversine(ctx.lat, ctx.lng, client.jobsite_latitude, client.jobsite_longitude)

    if dist > radius:
        return PromptResult(
            rule_key=RULE_GEO_LEFT_CLOCKED,
            title="Done for the day?",
            message=f"You've left {client.name} but are still clocked in.",
            action_url='/clock',
            action_label='Clock Out',
            icon='clock',
        )
    return None


def _eval_unattached_photos(ctx):
    """Photos taken via camera but not attached to a daily log."""
    if ctx.photos_taken_today <= 0:
        return None

    from sqlalchemy import func as sqlfunc, cast, Date
    uploaded_count = db.session.query(sqlfunc.count(DailyLogPhoto.id)).filter(
        DailyLogPhoto.uploaded_by_user_id == ctx.user_id,
        sqlfunc.date(DailyLogPhoto.created_at) == ctx.today_pacific,
    ).scalar() or 0

    delta = ctx.photos_taken_today - uploaded_count
    if delta > 0:
        return PromptResult(
            rule_key=RULE_UNATTACHED_PHOTOS,
            title=f"Add {delta} photo{'s' if delta != 1 else ''} to today's log?",
            message="Photos taken on site haven't been attached to a daily log yet.",
            action_url='/daily-logs/field',
            action_label='Add Photos',
            icon='photo',
        )
    return None
