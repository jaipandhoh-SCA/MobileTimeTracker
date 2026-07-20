"""GoHighLevel API v2 helper — pull contacts into the CRM."""

import os
import logging
import requests

logger = logging.getLogger(__name__)

GHL_API_BASE = 'https://services.leadconnectorhq.com'


def _headers():
    token = os.environ.get('GHL_API_KEY', '')
    return {
        'Authorization': f'Bearer {token}',
        'Version': '2021-07-28',
        'Accept': 'application/json',
    }


def _location_id():
    return os.environ.get('GHL_LOCATION_ID', '')


def is_configured():
    return bool(os.environ.get('GHL_API_KEY')) and bool(os.environ.get('GHL_LOCATION_ID'))


def test_connection():
    """Verify credentials by fetching the location."""
    if not is_configured():
        return False, 'GHL_API_KEY and GHL_LOCATION_ID are required'
    try:
        r = requests.get(
            f'{GHL_API_BASE}/locations/{_location_id()}',
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json().get('location', {})
            return True, data.get('name', 'Connected')
        return False, f'HTTP {r.status_code}: {r.text[:200]}'
    except Exception as e:
        return False, str(e)


def fetch_contacts(limit=100, after=None, query=None):
    """Fetch contacts from GHL. Returns (contacts_list, next_cursor)."""
    params = {
        'locationId': _location_id(),
        'limit': min(limit, 100),
    }
    if after:
        params['startAfterId'] = after
    if query:
        params['query'] = query

    try:
        r = requests.get(
            f'{GHL_API_BASE}/contacts/',
            headers=_headers(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        contacts = data.get('contacts', [])
        meta = data.get('meta', {})
        next_cursor = meta.get('startAfterId') or meta.get('nextPageUrl')
        return contacts, next_cursor
    except Exception as e:
        logger.error(f'GHL fetch_contacts error: {e}')
        return [], None


def fetch_all_contacts(max_pages=20):
    """Paginate through all contacts. Returns full list."""
    all_contacts = []
    cursor = None
    for _ in range(max_pages):
        batch, cursor = fetch_contacts(limit=100, after=cursor)
        all_contacts.extend(batch)
        if not cursor or not batch:
            break
    return all_contacts


def map_contact_to_client_data(contact):
    """Map a GHL contact dict to fields compatible with Client model."""
    name_parts = []
    if contact.get('firstName'):
        name_parts.append(contact['firstName'])
    if contact.get('lastName'):
        name_parts.append(contact['lastName'])
    name = ' '.join(name_parts) or contact.get('email', 'Unknown')

    # GHL address fields
    addr_parts = []
    if contact.get('address1'):
        addr_parts.append(contact['address1'])
    if contact.get('city'):
        addr_parts.append(contact['city'])
    if contact.get('state'):
        addr_parts.append(contact['state'])
    if contact.get('postalCode'):
        addr_parts.append(contact['postalCode'])
    address = ', '.join(addr_parts) if addr_parts else 'Address pending'

    # Map GHL tags to status if possible
    tags = [t.lower() for t in (contact.get('tags') or [])]
    status = 'Lead'
    if 'active' in tags or 'customer' in tags:
        status = 'Active'
    elif 'prospect' in tags:
        status = 'Prospect'

    return {
        'ghl_contact_id': contact.get('id'),
        'name': name,
        'address': address,
        'contact_name': name,
        'phone': contact.get('phone'),
        'email': contact.get('email'),
        'status': status,
        'notes': contact.get('source') or None,
        'source_detail': f"GHL: {contact.get('source', '')}" if contact.get('source') else 'GoHighLevel',
    }


def fetch_opportunities(pipeline_id=None, limit=100):
    """Fetch opportunities from GHL (optional: filter by pipeline)."""
    params = {
        'location_id': _location_id(),
        'limit': min(limit, 100),
    }
    if pipeline_id:
        params['pipeline_id'] = pipeline_id

    try:
        r = requests.get(
            f'{GHL_API_BASE}/opportunities/search',
            headers=_headers(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get('opportunities', [])
    except Exception as e:
        logger.error(f'GHL fetch_opportunities error: {e}')
        return []


def fetch_pipelines():
    """Fetch available pipelines for the location."""
    try:
        r = requests.get(
            f'{GHL_API_BASE}/opportunities/pipelines',
            headers=_headers(),
            params={'locationId': _location_id()},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get('pipelines', [])
    except Exception as e:
        logger.error(f'GHL fetch_pipelines error: {e}')
        return []
