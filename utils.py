from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP
import pytz
from calendar import monthrange


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


def round_to_quarter_hour(hours):
    """Round hours to nearest 0.25 (15 minutes)."""
    if hours is None:
        return None
    decimal_hours = Decimal(str(hours))
    return (decimal_hours / Decimal('0.25')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('0.25')


def calculate_duration(start_time, end_time):
    """Calculate duration in hours between two datetime objects."""
    if start_time is None or end_time is None:
        return None
    delta = end_time - start_time
    hours = Decimal(str(delta.total_seconds() / 3600))
    return round_to_quarter_hour(hours)


def format_hours(hours):
    """Format hours for display (2 decimal places)."""
    if hours is None:
        return "0.00"
    return f"{float(hours):.2f}"


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


def get_pay_period_dates(reference_date=None):
    """
    Get current pay period start and end dates.
    Pay periods: 1st-14th (paid on 15th), 15th-last day (paid on 1st of next month)
    Returns: (period_start_date, period_end_date, pay_date)
    """
    if reference_date is None:
        reference_date = datetime.now(PACIFIC_TZ).date()
    
    if reference_date.day <= 14:
        period_start = date(reference_date.year, reference_date.month, 1)
        period_end = date(reference_date.year, reference_date.month, 14)
        pay_date = date(reference_date.year, reference_date.month, 15)
    else:
        period_start = date(reference_date.year, reference_date.month, 15)
        last_day = monthrange(reference_date.year, reference_date.month)[1]
        period_end = date(reference_date.year, reference_date.month, last_day)
        if reference_date.month == 12:
            pay_date = date(reference_date.year + 1, 1, 1)
        else:
            pay_date = date(reference_date.year, reference_date.month + 1, 1)
    
    return period_start, period_end, pay_date


def get_next_pay_period_dates(reference_date=None):
    """
    Get next pay period start and end dates.
    Returns: (period_start_date, period_end_date, pay_date)
    """
    if reference_date is None:
        reference_date = datetime.now(PACIFIC_TZ).date()
    
    current_start, current_end, current_pay_date = get_pay_period_dates(reference_date)
    next_period_start = current_end + timedelta(days=1)
    
    return get_pay_period_dates(next_period_start)


def get_previous_pay_period_dates(reference_date=None):
    """
    Get previous pay period start and end dates.
    Returns: (period_start_date, period_end_date, pay_date)
    """
    if reference_date is None:
        reference_date = datetime.now(PACIFIC_TZ).date()
    
    current_start, current_end, current_pay_date = get_pay_period_dates(reference_date)
    previous_period_end = current_start - timedelta(days=1)
    
    return get_pay_period_dates(previous_period_end)


def get_last_30_days_dates(reference_date=None):
    """
    Get dates for the last 30 days period.
    Returns: (period_start_date, period_end_date, display_label)
    """
    if reference_date is None:
        reference_date = datetime.now(PACIFIC_TZ).date()
    
    period_end = reference_date
    period_start = reference_date - timedelta(days=29)
    label = "Last 30 Days"
    
    return period_start, period_end, label


def get_month_to_date_dates(reference_date=None):
    """
    Get dates for month-to-date period.
    Returns: (period_start_date, period_end_date, display_label)
    """
    if reference_date is None:
        reference_date = datetime.now(PACIFIC_TZ).date()
    
    period_start = date(reference_date.year, reference_date.month, 1)
    period_end = reference_date
    label = "Month-to-Date"
    
    return period_start, period_end, label
