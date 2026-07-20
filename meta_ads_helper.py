"""Meta Marketing API helper — pull ad spend and lead counts."""

import os
import logging
from datetime import date, timedelta
from decimal import Decimal
import requests

logger = logging.getLogger(__name__)

META_GRAPH_BASE = 'https://graph.facebook.com/v21.0'


def _access_token():
    return os.environ.get('META_ADS_ACCESS_TOKEN', '')


def _account_id():
    """Return account ID with 'act_' prefix."""
    raw = os.environ.get('META_ADS_ACCOUNT_ID', '')
    if raw and not raw.startswith('act_'):
        return f'act_{raw}'
    return raw


def is_configured():
    return bool(os.environ.get('META_ADS_ACCESS_TOKEN')) and bool(os.environ.get('META_ADS_ACCOUNT_ID'))


def test_connection():
    """Verify credentials by fetching account info."""
    if not is_configured():
        return False, 'META_ADS_ACCESS_TOKEN and META_ADS_ACCOUNT_ID are required'
    try:
        r = requests.get(
            f'{META_GRAPH_BASE}/{_account_id()}',
            params={
                'access_token': _access_token(),
                'fields': 'name,account_status,currency',
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return True, data.get('name', 'Connected')
        err = r.json().get('error', {}).get('message', r.text[:200])
        return False, f'HTTP {r.status_code}: {err}'
    except Exception as e:
        return False, str(e)


def fetch_account_insights(since, until, level='account'):
    """
    Fetch spend and action metrics for a date range.

    Args:
        since: date object (inclusive)
        until: date object (inclusive)
        level: 'account', 'campaign', or 'adset'

    Returns list of insight rows with spend, impressions, clicks, actions.
    """
    params = {
        'access_token': _access_token(),
        'fields': 'campaign_name,campaign_id,spend,impressions,clicks,actions,cost_per_action_type',
        'time_range': f'{{"since":"{since.isoformat()}","until":"{until.isoformat()}"}}',
        'level': level,
        'limit': 500,
    }

    all_rows = []
    url = f'{META_GRAPH_BASE}/{_account_id()}/insights'

    try:
        while url:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            all_rows.extend(data.get('data', []))
            # Pagination
            url = data.get('paging', {}).get('next')
            params = {}  # next URL has params baked in
    except Exception as e:
        logger.error(f'Meta Ads fetch_account_insights error: {e}')

    return all_rows


def fetch_monthly_spend(year, month):
    """
    Get total spend for a given month.
    Returns (spend_decimal, lead_count, impressions, clicks).
    """
    since = date(year, month, 1)
    if month == 12:
        until = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        until = date(year, month + 1, 1) - timedelta(days=1)

    rows = fetch_account_insights(since, until, level='account')
    total_spend = Decimal(0)
    total_impressions = 0
    total_clicks = 0
    total_leads = 0

    for row in rows:
        total_spend += Decimal(row.get('spend', '0'))
        total_impressions += int(row.get('impressions', 0))
        total_clicks += int(row.get('clicks', 0))
        # Extract lead actions
        for action in (row.get('actions') or []):
            if action.get('action_type') in ('lead', 'onsite_conversion.lead_grouped', 'offsite_conversion.fb_pixel_lead'):
                total_leads += int(action.get('value', 0))

    return total_spend, total_leads, total_impressions, total_clicks


def fetch_campaign_breakdown(year, month):
    """
    Get per-campaign spend breakdown for a month.
    Returns list of dicts with campaign_name, campaign_id, spend, leads, impressions, clicks.
    """
    since = date(year, month, 1)
    if month == 12:
        until = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        until = date(year, month + 1, 1) - timedelta(days=1)

    rows = fetch_account_insights(since, until, level='campaign')
    campaigns = []

    for row in rows:
        leads = 0
        for action in (row.get('actions') or []):
            if action.get('action_type') in ('lead', 'onsite_conversion.lead_grouped', 'offsite_conversion.fb_pixel_lead'):
                leads += int(action.get('value', 0))

        campaigns.append({
            'campaign_name': row.get('campaign_name', 'Unknown'),
            'campaign_id': row.get('campaign_id'),
            'spend': Decimal(row.get('spend', '0')),
            'leads': leads,
            'impressions': int(row.get('impressions', 0)),
            'clicks': int(row.get('clicks', 0)),
        })

    campaigns.sort(key=lambda x: -x['spend'])
    return campaigns
