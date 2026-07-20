from datetime import datetime
import pytz


PACIFIC_TZ = pytz.timezone('America/Los_Angeles')


def utc_to_pacific(utc_dt):
    """Convert UTC datetime to Pacific timezone."""
    if utc_dt is None:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    return utc_dt.astimezone(PACIFIC_TZ)


def pacific_to_utc(pacific_dt):
    """Convert Pacific datetime to UTC."""
    if pacific_dt is None:
        return None
    if pacific_dt.tzinfo is None:
        pacific_dt = PACIFIC_TZ.localize(pacific_dt)
    return pacific_dt.astimezone(pytz.utc)


def format_date_for_display(date):
    """Format date as MM/DD/YYYY."""
    if date is None:
        return ""
    return date.strftime("%m/%d/%Y")


def format_datetime_for_display(dt):
    """Format datetime as MM/DD/YYYY HH:MM AM/PM in Pacific time."""
    if dt is None:
        return ""
    pacific_dt = utc_to_pacific(dt)
    return pacific_dt.strftime("%m/%d/%Y %I:%M %p")


def format_datetime_for_input(value):
    """Format datetime for datetime-local input field (YYYY-MM-DDTHH:MM)."""
    if value == 'now':
        pacific_now = datetime.now(PACIFIC_TZ)
        return pacific_now.strftime("%Y-%m-%dT%H:%M")
    if value is None:
        return ""
    pacific_dt = utc_to_pacific(value)
    return pacific_dt.strftime("%Y-%m-%dT%H:%M")
