"""Private monthly invoice ledger for the permanent Mahee account."""
import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import g, jsonify, request

try:
    from api.portal import PortalError, body, require_user, text_field, valid_id
    from api.supabase_store import StoreError, db
except ModuleNotFoundError:
    from portal import PortalError, body, require_user, text_field, valid_id
    from supabase_store import StoreError, db


def check_access():
    user = g.portal_user
    if not user.get('is_owner') or user.get('username', '').lower() != 'mahee':
        raise PortalError('Invoices are only available to Mahee.', 403)


def validate_month(month):
    if not isinstance(month, str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', month):
        raise PortalError('Choose a month between January 2000 and December 2099.')
    return month


def invoice_selector(key):
    # Older open tabs still address the original monthly invoice only.
    if re.fullmatch(r'\d{4}-\d{1,2}', key):
        return {'legacy_month': 'eq.' + validate_month(key)}
    return {'id': 'eq.' + valid_id(key)}


def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > 100:
        raise PortalError('An invoice can contain up to 100 markets.')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise PortalError('Invalid market entry.')
        cleaned = {key: text_field(row, key, size, required=key != 'remark')
                   for key, size in [('dealer', 100), ('market', 100), ('remark', 500)]}
        key = (cleaned['dealer'].casefold(), cleaned['market'].casefold())
        if key in seen:
            raise PortalError('Each dealer and market can appear only once per invoice.')
        seen.add(key)
        # Older saved invoices and clients represent one market amount.
        count = row.get('store_count', 1)
        if type(count) is not int or not 1 <= count <= 10000:
            raise PortalError('Store count must be a whole number from 1 to 10,000.')
        cleaned['store_count'] = count
        for field in ('amount_cents', 'advance_cents'):
            value = row.get(field)
            if type(value) is not int or not 0 <= value <= 99999999999:
                raise PortalError('Amounts must be nonnegative, with at most two decimal places and below 1 billion USD.')
            cleaned[field] = value
        if count * cleaned['amount_cents'] > 99999999999:
            raise PortalError('Store count times amount must be below 1 billion USD per market.')
        result.append(cleaned)
    return result


def invoice_view(record):
    rows = [{**row, 'store_count': row.get('store_count', 1),
             'subtotal_cents': row.get('store_count', 1) * row['amount_cents'],
             'balance_cents': row.get('store_count', 1) * row['amount_cents'] - row['advance_cents']}
            for row in record['rows']]
    totals = {'amount_cents': sum(row['subtotal_cents'] for row in rows),
              'advance_cents': sum(row['advance_cents'] for row in rows),
              'balance_cents': sum(row['balance_cents'] for row in rows)}
    year, month = map(int, record['month'].split('-'))
    return {**record, 'rows': rows, 'totals': totals, 'currency': 'USD',
            'balance_month': f'{year + (month == 12):04d}-{month % 12 + 1:02d}'}


def register_invoices(app):
    @app.get('/api/internal/invoices')
    @require_user()
    def list_invoices():
        check_access()
        query = text_field(request.args, 'q', 120, required=False)
        month = request.args.get('month', '')
        if month:
            validate_month(month)
        offset = request.args.get('offset', '0')
        if not re.fullmatch(r'\d{1,7}', offset):
            raise PortalError('Invalid invoice list offset.')
        records = db('rpc/list_saved_invoices', 'POST', {
            'p_query': query, 'p_month': month, 'p_offset': int(offset),
        })
        return jsonify(invoices=records[:20], has_more=len(records) > 20)

    @app.get('/api/internal/invoices/<key>')
    @require_user()
    def get_invoice(key):
        check_access()
        selector = invoice_selector(key)
        records = db('invoice_months', **selector, limit=1)
        if not records and 'id' in selector:
            raise PortalError('Saved invoice not found.', 404)
        record = records[0] if records else {'month': key, 'name': 'Invoice - ' + key,
                                            'rows': [], 'revision': None, 'updated_at': None}
        return jsonify(invoice=invoice_view(record))

    @app.put('/api/internal/invoices/<key>')
    @require_user()
    def save_invoice(key):
        check_access()
        selector = invoice_selector(key)
        payload = body()
        legacy = 'legacy_month' in selector
        month = validate_month(key if legacy else payload.get('month'))
        name = text_field(payload, 'name', 120) if not legacy or 'name' in payload else None
        rows = validate_rows(payload.get('rows'))
        revision = payload.get('revision')
        if revision is not None:
            if not isinstance(revision, str):
                raise PortalError('Invalid invoice revision.')
            revision = valid_id(revision)
        record = {'month': month, 'rows': rows, 'revision': str(uuid4()),
                  'updated_at': datetime.now(timezone.utc).isoformat()}
        if name is not None:
            record['name'] = name
        if legacy and revision is None:
            record.update(id=str(uuid4()), legacy_month=month, name=name or 'Invoice - ' + month)
        elif not legacy:
            record['id'] = selector['id'][3:]
        try:
            if revision is None:
                saved = db('invoice_months', 'POST', record)
            else:
                saved = db('invoice_months', 'PATCH', record, **selector, revision='eq.' + revision)
        except StoreError as exc:
            if exc.code != '23505':
                raise
            saved = []
        if not saved:
            raise PortalError('This invoice changed in another tab. Reload the saved invoice before editing again.', 409)
        return jsonify(invoice=invoice_view(saved[0]))
