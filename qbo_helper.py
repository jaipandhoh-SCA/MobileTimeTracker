"""QuickBooks Online two-way sync helper.

OAuth 2.0 flow, token refresh, and API calls for Customers, Invoices,
Payments, and Accounts/Items.  Every sync is idempotent — entities carry
their QBO ID so retries never create duplicates.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import requests

log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

QBO_CLIENT_ID = os.environ.get('QBO_CLIENT_ID', '')
QBO_CLIENT_SECRET = os.environ.get('QBO_CLIENT_SECRET', '')
QBO_REDIRECT_URI = os.environ.get('QBO_REDIRECT_URI', '')
QBO_ENVIRONMENT = os.environ.get('QBO_ENVIRONMENT', 'sandbox')  # sandbox | production

_BASE = {
    'sandbox':    'https://sandbox-quickbooks.api.intuit.com',
    'production': 'https://quickbooks.api.intuit.com',
}
_AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
_TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'

SCOPES = 'com.intuit.quickbooks.accounting'


def is_configured():
    return bool(QBO_CLIENT_ID and QBO_CLIENT_SECRET and QBO_REDIRECT_URI)


def auth_url(state: str) -> str:
    """Build the OAuth 2.0 authorization URL."""
    from urllib.parse import urlencode
    params = {
        'client_id': QBO_CLIENT_ID,
        'scope': SCOPES,
        'redirect_uri': QBO_REDIRECT_URI,
        'response_type': 'code',
        'state': state,
    }
    return f'{_AUTH_URL}?{urlencode(params)}'


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    resp = requests.post(_TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': QBO_REDIRECT_URI,
    }, auth=(QBO_CLIENT_ID, QBO_CLIENT_SECRET), timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_token(refresh_tok: str) -> dict:
    """Refresh an expired access token.  Returns the new token payload."""
    resp = requests.post(_TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'refresh_token': refresh_tok,
    }, auth=(QBO_CLIENT_ID, QBO_CLIENT_SECRET), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── API helpers ─────────────────────────────────────────────────────────

class QBOClient:
    """Thin wrapper around the QBO REST API with automatic token refresh."""

    def __init__(self, realm_id: str, access_token: str, refresh_tok: str,
                 token_expires_at: float, on_token_refreshed=None):
        self.realm_id = realm_id
        self.access_token = access_token
        self.refresh_tok = refresh_tok
        self.token_expires_at = token_expires_at
        self._on_refreshed = on_token_refreshed  # callback(new_tokens_dict)

    @property
    def base_url(self):
        base = _BASE.get(QBO_ENVIRONMENT, _BASE['sandbox'])
        return f'{base}/v3/company/{self.realm_id}'

    def _ensure_fresh_token(self):
        if time.time() >= self.token_expires_at - 60:
            log.info('QBO access token expired — refreshing')
            data = refresh_token(self.refresh_tok)
            self.access_token = data['access_token']
            self.refresh_tok = data['refresh_token']
            self.token_expires_at = time.time() + data.get('expires_in', 3600)
            if self._on_refreshed:
                self._on_refreshed(data)

    def _headers(self):
        self._ensure_fresh_token()
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def _get(self, path, params=None):
        url = f'{self.base_url}{path}'
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path, data):
        url = f'{self.base_url}{path}'
        resp = requests.post(url, headers=self._headers(), json=data, timeout=30)
        if resp.status_code >= 400:
            log.error('QBO POST %s → %s: %s', path, resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()

    def query(self, q: str):
        """Run a QBO query (SQL-like).  Returns list of entities."""
        data = self._get('/query', params={'query': q})
        resp = data.get('QueryResponse', {})
        # Response key varies by entity type — grab the first list value
        for v in resp.values():
            if isinstance(v, list):
                return v
        return []

    # ── Company Info ────────────────────────────────────────────────

    def company_info(self):
        data = self._get('/companyinfo/' + self.realm_id)
        return data.get('CompanyInfo', {})

    # ── Chart of Accounts ───────────────────────────────────────────

    def get_accounts(self, account_type=None):
        q = "SELECT * FROM Account WHERE Active = true"
        if account_type:
            q += f" AND AccountType = '{account_type}'"
        q += " ORDERBY Name MAXRESULTS 1000"
        return self.query(q)

    def get_items(self):
        return self.query("SELECT * FROM Item WHERE Active = true MAXRESULTS 1000")

    # ── Customers ───────────────────────────────────────────────────

    def get_customer(self, qbo_id):
        data = self._get(f'/customer/{qbo_id}')
        return data.get('Customer')

    def find_customer_by_name(self, name):
        safe = name.replace("'", "\\'")
        results = self.query(f"SELECT * FROM Customer WHERE DisplayName = '{safe}'")
        return results[0] if results else None

    def create_customer(self, display_name, email=None, phone=None,
                        address_line=None, city=None, state=None, zip_code=None):
        body = {'DisplayName': display_name}
        if email:
            body['PrimaryEmailAddr'] = {'Address': email}
        if phone:
            body['PrimaryPhone'] = {'FreeFormNumber': phone}
        if address_line:
            body['BillAddr'] = {
                'Line1': address_line,
                'City': city or '',
                'CountrySubDivisionCode': state or '',
                'PostalCode': zip_code or '',
            }
        data = self._post('/customer', body)
        return data.get('Customer')

    def update_customer(self, qbo_id, sync_token, **fields):
        body = {'Id': str(qbo_id), 'SyncToken': str(sync_token), 'sparse': True}
        body.update(fields)
        data = self._post('/customer', body)
        return data.get('Customer')

    # ── Invoices ────────────────────────────────────────────────────

    def get_invoice(self, qbo_id):
        data = self._get(f'/invoice/{qbo_id}')
        return data.get('Invoice')

    def create_invoice(self, customer_id, line_items, doc_number=None,
                       due_date=None, txn_date=None, memo=None):
        """Create a QBO invoice.

        line_items: list of dicts with keys:
            description, amount, item_id (optional QBO Item ref)
        """
        lines = []
        for i, li in enumerate(line_items):
            line = {
                'Amount': float(li['amount']),
                'DetailType': 'SalesItemLineDetail',
                'Description': li.get('description', ''),
                'SalesItemLineDetail': {
                    'Qty': 1,
                    'UnitPrice': float(li['amount']),
                },
            }
            if li.get('item_id'):
                line['SalesItemLineDetail']['ItemRef'] = {'value': str(li['item_id'])}
            lines.append(line)

        body = {
            'CustomerRef': {'value': str(customer_id)},
            'Line': lines,
        }
        if doc_number:
            body['DocNumber'] = doc_number
        if due_date:
            body['DueDate'] = due_date
        if txn_date:
            body['TxnDate'] = txn_date
        if memo:
            body['PrivateNote'] = memo

        data = self._post('/invoice', body)
        return data.get('Invoice')

    def void_invoice(self, qbo_id, sync_token):
        body = {'Id': str(qbo_id), 'SyncToken': str(sync_token)}
        url = f'{self.base_url}/invoice/{qbo_id}?operation=void'
        resp = requests.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json().get('Invoice')

    # ── Payments ────────────────────────────────────────────────────

    def get_payment(self, qbo_id):
        data = self._get(f'/payment/{qbo_id}')
        return data.get('Payment')

    def create_payment(self, customer_id, amount, invoice_qbo_id=None,
                       txn_date=None, payment_method=None, memo=None):
        body = {
            'CustomerRef': {'value': str(customer_id)},
            'TotalAmt': float(amount),
        }
        if invoice_qbo_id:
            body['Line'] = [{
                'Amount': float(amount),
                'LinkedTxn': [{'TxnId': str(invoice_qbo_id), 'TxnType': 'Invoice'}],
            }]
        if txn_date:
            body['TxnDate'] = txn_date
        if payment_method:
            body['PaymentMethodRef'] = {'value': str(payment_method)}
        if memo:
            body['PrivateNote'] = memo

        data = self._post('/payment', body)
        return data.get('Payment')

    def get_payments_for_invoice(self, invoice_qbo_id):
        return self.query(
            f"SELECT * FROM Payment WHERE Line.LinkedTxn.TxnId = '{invoice_qbo_id}'"
        )

    # ── Query helpers ───────────────────────────────────────────────

    def get_invoices_since(self, since_date):
        return self.query(
            f"SELECT * FROM Invoice WHERE MetaData.LastUpdatedTime > '{since_date}' "
            "ORDERBY MetaData.LastUpdatedTime MAXRESULTS 500"
        )

    def get_payments_since(self, since_date):
        return self.query(
            f"SELECT * FROM Payment WHERE MetaData.LastUpdatedTime > '{since_date}' "
            "ORDERBY MetaData.LastUpdatedTime MAXRESULTS 500"
        )

    def get_customers_since(self, since_date):
        return self.query(
            f"SELECT * FROM Customer WHERE MetaData.LastUpdatedTime > '{since_date}' "
            "ORDERBY MetaData.LastUpdatedTime MAXRESULTS 500"
        )
