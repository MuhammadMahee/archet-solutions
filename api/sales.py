"""Bounded, parallel RT-POS imports and authenticated sales reporting."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookiejar import Cookie, CookieJar
from io import BytesIO
import json
import os
import secrets
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from zoneinfo import ZoneInfo

from flask import jsonify, request, send_file
import psycopg
from psycopg.rows import dict_row
import xlrd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

try:
    from api.portal import require_user, PortalError
    from api.supabase_store import StoreError
except ModuleNotFoundError:
    from portal import require_user, PortalError
    from supabase_store import StoreError

REPORT_URL = 'https://myrtpos.com/newbdi/Store_Performance_lp.fwx'
CENTRAL = ZoneInfo('America/Chicago')
SOURCES = {'connect': 'Connect', 'california': 'California', 'srh': 'SRH',
           'arm1': 'ARM', 'arm2': 'ARM', 'arbf': 'ARBF'}
COLORS = {'Connect': '#176b56', 'California': '#a92d49', 'SRH': '#a06118',
          'ARM': '#365cad', 'ARBF': '#7646a5'}
METRICS = ('new_activation', 'upgrade', 'reactivation', 'bts', 'hsi',
           'accessory', 'total_boxes', 'qpay')
COLUMNS = [('dealer', 'Dealer'), ('market', 'Market'), ('store', 'Store'),
           ('new_activation', 'New activation'), ('upgrade', 'Upgrade'),
           ('reactivation', 'Reactivation'), ('bts', 'BTS'), ('hsi', 'HSI'),
           ('accessory', 'Accessory'), ('apo', 'APO'), ('total_boxes', 'Total boxes'),
           ('qpay', 'QPay'), ('qpay_conv', 'QPay conv')]
LOCK_ID = 731043260926
MAX_REPORT_BYTES = 20 * 1024 * 1024


class ReportError(Exception):
    """Only stable, non-secret error codes may leave the importer."""


def today():
    return datetime.now(CENTRAL).date()


def connect():
    url = os.getenv('SUPABASE_DB_URL', '')
    if not url:
        raise StoreError(code='not_configured')
    return psycopg.connect(url, autocommit=True, sslmode='require', connect_timeout=10,
                          row_factory=dict_row, options='-c statement_timeout=30000')


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != 'https' or target.hostname not in ('myrtpos.com', 'www.myrtpos.com'):
            raise ReportError('unexpected_redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_source(cookies):
    """Ignore shared FW_SessionID: RT-POS must issue a NEW session per account."""
    jar = CookieJar()
    for name in ('sec85952EAF_id', 'sec85952EAF_pd'):
        value = cookies.get(name)
        if not isinstance(value, str) or not value or any(c in value for c in '\r\n;'):
            raise ReportError('missing_cookies')
        jar.set_cookie(Cookie(0, name, value, None, False, 'myrtpos.com', False,
                              False, '/newbdi', True, True, None, True, None, None, {}, False))
    opener = build_opener(SameHostRedirect(), HTTPCookieProcessor(jar))
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (compatible; ArchetSales/1.0)')]
    with opener.open(REPORT_URL, timeout=35) as response:
        html = response.read(2 * 1024 * 1024).decode('utf-8', errors='replace')
    if 'frmStart' not in html or 'frmEnd' not in html:
        raise ReportError('cookies_expired')
    return opener


def fetch_report(opener, report_date):
    formatted = report_date.strftime('%m/%d/%Y')
    payload = urlencode({'frmMarketID': '', 'frmRegionID': '', 'frmStateID': '',
                         'frmStoreType': '', 'frmStore': '', 'frmStart': formatted,
                         'frmEnd': formatted, 'btnExcel': 'click'}).encode()
    req = Request(REPORT_URL, data=payload, headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Referer': REPORT_URL})
    with opener.open(req, timeout=35) as response:
        data = response.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ReportError('report_too_large')
    if not data.startswith(b'\xd0\xcf\x11\xe0'):
        raise ReportError('invalid_report_or_expired_cookies')
    return read_xls(data)


def number(value):
    try:
        result = Decimal(str(value or '0').strip().replace(',', '').replace('$', '').replace('%', ''))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise ReportError('invalid_numeric_data') from None


def read_xls(data):
    try:
        book = xlrd.open_workbook(file_contents=data)
        sheet = book.sheet_by_index(0)
    except (xlrd.XLRDError, IndexError):
        raise ReportError('invalid_xls') from None
    if not sheet.nrows:
        raise ReportError('missing_headers')
    headers = {str(v).strip().lower(): i for i, v in enumerate(sheet.row_values(0))}
    react = 'reactact' if 'reactact' in headers else 'react'
    needed = {'custno', 'marketid', 'company', 'newact', 'upgsor', 'totact',
              'totaccessory', 'totpaymentqty', 'iot', 'hint', react}
    if needed - headers.keys():
        raise ReportError('report_columns_changed')
    rows, seen = [], set()
    for idx in range(1, sheet.nrows):
        cell = lambda name: sheet.cell_value(idx, headers[name])
        store, sid = str(cell('company')).strip().upper(), str(cell('custno')).strip().upper()
        if not store or store == 'TOTAL':
            continue
        if not sid or sid in seen:
            raise ReportError('missing_or_duplicate_store_id')
        seen.add(sid)
        integer = lambda name: int(number(cell(name)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        rows.append({'store_id': sid, 'store': store,
                     'market': str(cell('marketid')).strip().upper() or 'UNASSIGNED',
                     'new_activation': integer('newact'), 'upgrade': integer('upgsor'),
                     'reactivation': integer(react), 'hsi': integer('hint'),
                     'bts': integer('iot') - integer('hint'),
                     'accessory': number(cell('totaccessory')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP),
                     'total_boxes': integer('totact'), 'qpay': integer('totpaymentqty')})
    # A valid header-only export means no source rows, not an authentication error.
    return rows


def seed_jobs(conn, current):
    """Resume month backfill and refresh today; close yesterday after midnight."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany('''insert into public.sales_imports(source_id, report_date)
                select %s, d::date from generate_series(%s::date,%s::date,'1 day') d
                on conflict do nothing''', [(s, current.replace(day=1), current) for s in SOURCES])
        conn.execute('''update public.sales_imports set status='pending', retry_at=now()
            where status='complete' and ((report_date=%s and loaded_at < now()-interval '18 minutes')
              or (report_date=%s and loaded_at < %s))''',
                     (current, current - timedelta(days=1), datetime.combine(current, datetime.min.time(), CENTRAL)))


def save_rows(conn, source, report_date, rows):
    """Replace explicit values, retaining omitted source rows with a stale timestamp."""
    with conn.transaction():
        fields = ('store_id', 'market', 'store', *METRICS)
        now = conn.execute('select now() as value').fetchone()['value']
        if rows:
            updates = ','.join(f'{key}=excluded.{key}' for key in fields if key != 'store_id')
            sql = f'''insert into public.sales_performance(source_id,report_date,{','.join(fields)},loaded_at)
                values ({','.join(['%s'] * (len(fields) + 3))})
                on conflict(source_id,report_date,store_id) do update set {updates},loaded_at=excluded.loaded_at'''
            with conn.cursor() as cur:
                cur.executemany(sql, [(source, report_date, *(r[k] for k in fields), now) for r in rows])
        retained = conn.execute('''select count(*) as n from public.sales_performance
            where source_id=%s and report_date=%s and loaded_at<%s''', (source, report_date, now)).fetchone()['n']
        conn.execute('''update public.sales_imports set status='complete', loaded_at=%s,
            attempted_at=%s,row_count=%s,retained_count=%s,error_code=null
            where source_id=%s and report_date=%s''', (now, now, len(rows), retained, source, report_date))


def mark_error(conn, source, report_date, code):
    conn.execute('''update public.sales_imports set status='error',attempted_at=now(),
        retry_at=now()+interval '20 minutes',error_code=%s where source_id=%s and report_date=%s''',
                 (code, source, report_date))


def source_worker(source, cookies, current):
    with connect() as conn:
        jobs = conn.execute('''select report_date from public.sales_imports
            where source_id=%s and report_date<=%s and status in ('pending','error') and retry_at<=now()
            order by (report_date=%s) desc,report_date limit 4''', (source, current, current)).fetchall()
        if not jobs:
            return {'source': source, 'completed': 0, 'failed': 0}
        try:
            opener = open_source(cookies)
        except Exception as exc:
            code = str(exc) if isinstance(exc, ReportError) else 'source_unavailable'
            for job in jobs:
                mark_error(conn, source, job['report_date'], code)
            return {'source': source, 'completed': 0, 'failed': len(jobs), 'error': code}
        completed, failed = 0, 0
        for job in jobs:
            try:
                rows = fetch_report(opener, job['report_date'])
                save_rows(conn, source, job['report_date'], rows)
                completed += 1
            except (ReportError, OSError, ValueError) as exc:
                code = str(exc) if isinstance(exc, ReportError) else 'source_unavailable'
                mark_error(conn, source, job['report_date'], code)
                failed += 1
        return {'source': source, 'completed': completed, 'failed': failed}


def run_batch():
    try:
        cookies = json.loads(os.getenv('RTPOS_COOKIES', '{}'))
        if not isinstance(cookies, dict):
            raise ValueError
    except ValueError:
        raise PortalError('RT-POS credentials need configuration.', 503) from None
    with connect() as conn:
        if not conn.execute('select pg_try_advisory_lock(%s) as locked', (LOCK_ID,)).fetchone()['locked']:
            return {'status': 'busy', 'remaining': 1, 'workers': []}
        try:
            current = today()
            seed_jobs(conn, current)
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [pool.submit(source_worker, s, cookies.get(s, {}), current) for s in SOURCES]
                results = [future.result() for future in futures]
            counts = conn.execute('''select count(*) filter(where status<>'complete') as remaining,
                count(*) filter(where status<>'complete' and retry_at<=now()) as due,
                count(*) filter(where status='error') as failed
                from public.sales_imports where report_date<=%s''', (current,)).fetchone()
            return {'status': 'partial' if counts['remaining'] else 'complete', **counts, 'workers': results}
        finally:
            conn.execute('select pg_advisory_unlock(%s)', (LOCK_ID,))


def ratios(row):
    row['apo'] = (Decimal(str(row['accessory'])) / row['total_boxes'] if row['total_boxes'] else Decimal(0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    row['qpay_conv'] = (Decimal(row['total_boxes']) / row['qpay'] * 100 if row['qpay'] else Decimal(0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return row


def aggregate(raw):
    """ARM overlap is one store/day; prefer arm1 consistently, never sum duplicate accounts."""
    daily = {}
    for row in sorted(raw, key=lambda r: (r['stale'], r['source_id'])):
        key = (SOURCES[row['source_id']], row['report_date'], row['store_id'])
        daily.setdefault(key, row)
    grouped = {}
    for (dealer, day, sid), r in sorted(daily.items(), key=lambda item: item[0][1]):
        key = dealer, sid
        if key not in grouped:
            grouped[key] = {'dealer': dealer, 'store_id': sid, 'market': r['market'], 'store': r['store'],
                            'stale': False, **{k: 0 for k in METRICS}}
        out = grouped[key]
        out.update(market=r['market'], store=r['store'])
        out['stale'] |= r['stale']
        for k in METRICS:
            out[k] += r[k]
    return sorted([ratios(r) for r in grouped.values()], key=lambda r: (r['dealer'], r['market'], r['store']))


def date_range():
    try:
        start = date.fromisoformat(request.args.get('start', today().isoformat()))
        end = date.fromisoformat(request.args.get('end', start.isoformat()))
    except ValueError:
        raise PortalError('Choose valid report dates.') from None
    if start > end or end > today() or (end - start).days > 92:
        raise PortalError('Choose a range of up to 93 days ending today or earlier.')
    return start, end


def report_data(start, end):
    with connect() as conn:
        raw = conn.execute('''select p.*, (p.loaded_at<i.loaded_at or i.status='error') as stale
            from public.sales_performance p join public.sales_imports i using(source_id,report_date)
            where p.report_date between %s and %s order by p.report_date,p.source_id,p.store_id''', (start, end)).fetchall()
        imports = conn.execute('''select source_id, report_date,status,loaded_at,row_count,retained_count,error_code
            from public.sales_imports where report_date between %s and %s
            order by source_id,report_date''', (start, end)).fetchall()
    rows = aggregate(raw)
    dealer = request.args.get('dealer', '')
    if dealer and dealer not in COLORS:
        raise PortalError('Unknown dealer.')
    relevant = [i for i in imports if not dealer or SOURCES[i['source_id']] == dealer]
    if dealer:
        rows = [r for r in rows if r['dealer'] == dealer]
    markets = sorted({r['market'] for r in rows})
    market, store_id = request.args.get('market', ''), request.args.get('store', '')
    if market:
        rows = [r for r in rows if r['market'] == market]
    stores = [{'id': r['dealer'] + ':' + r['store_id'], 'name': r['store']} for r in rows]
    if store_id:
        rows = [r for r in rows if r['dealer'] + ':' + r['store_id'] == store_id]
    total = ratios({k: sum(r[k] for r in rows) for k in METRICS})
    expected = sum(1 for s in SOURCES if not dealer or SOURCES[s] == dealer) * ((end - start).days + 1)
    complete = sum(i['status'] == 'complete' for i in relevant)
    times = [i['loaded_at'] for i in relevant if i['loaded_at']]
    return {'rows': rows, 'totals': total, 'markets': markets, 'stores': stores,
            'dealers': [{'name': d, 'color': c} for d, c in COLORS.items()],
            'start': start.isoformat(), 'end': end.isoformat(), 'today': today().isoformat(),
            'coverage': {'complete': complete, 'expected': expected,
                         'retained': sum(i['retained_count'] for i in relevant),
                         'errors': sorted({SOURCES[i['source_id']] for i in relevant if i['status'] == 'error'})},
            'updated_at': min(times).isoformat() if times else None}


def workbook_bytes(data):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Sales Update'
    sheet.append([label for _, label in COLUMNS])
    for row in [*data['rows'], {'dealer': 'TOTAL', **data['totals']}]:
        values = [row.get(key, '') for key, _ in COLUMNS]
        sheet.append(values)
        # Remote store names are untrusted strings; never create spreadsheet formulas.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
        for key, col in [('accessory', 9), ('apo', 10)]:
            sheet.cell(sheet.max_row, col).number_format = '$#,##0.00'
        sheet.cell(sheet.max_row, 13).number_format = '0.00"%"'
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='19352E')
    sheet.freeze_panes = 'D2'
    sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        sheet.column_dimensions[cells[0].column_letter].width = min(45, max(14, max(len(str(c.value or '')) for c in cells) + 2))
    meta = book.create_sheet('Report details')
    meta.append(['Start', data['start']]); meta.append(['End', data['end']])
    meta.append(['Completed source-days', data['coverage']['complete']])
    meta.append(['Expected source-days', data['coverage']['expected']])
    meta.append(['Retained source rows', data['coverage']['retained']])
    meta.append(['Oldest successful refresh', data['updated_at'] or 'Not available'])
    result = BytesIO(); book.save(result); result.seek(0)
    return result


def register_sales(app):
    @app.errorhandler(psycopg.Error)
    def sales_database_error(exc):
        app.logger.warning('Sales database unavailable (%s)', exc.sqlstate or 'connection_error')
        return jsonify(message='Sales data is temporarily unavailable. Please retry.'), 503

    @app.get('/api/internal/sales')
    @require_user()
    def sales_report():
        return jsonify(report_data(*date_range()))

    @app.get('/api/internal/sales/export')
    @require_user()
    def sales_export():
        start, end = date_range()
        return send_file(workbook_bytes(report_data(start, end)), as_attachment=True,
                         download_name=f'archet-sales-{start}-{end}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.post('/api/internal/sales/refresh')
    @require_user(admin=True)
    def sales_refresh():
        return jsonify(run_batch())

    @app.post('/api/jobs/sales')
    def scheduled_sales():
        secret = os.getenv('CRON_SECRET', '')
        if not secret or not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + secret):
            return jsonify(message='Unauthorized'), 401
        if os.getenv('VERCEL_ENV') and os.getenv('VERCEL_ENV') != 'production':
            return jsonify(message='Production only'), 403
        result = run_batch()
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response
