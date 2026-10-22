"""Store opening/closing reviews and inclusive RT-POS time-punch imports."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, time as wall_time, timedelta
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
import re
import time
from urllib.parse import urlencode
from urllib.request import Request

from flask import g, jsonify, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import xlrd

from api.calling_tree import active_roster, clean
from api.portal import PortalError, body, require_user
from api.store_schedules import scheduled_hours
from api.sales import (SOURCES, COLORS, MAX_REPORT_BYTES, ReportError, connect,
                       open_source, read_source, source_error, today)

REPORT_URL = 'https://myrtpos.com/newbdi/TimePunches.fwx'
LOCK_ID = 731043260927
COLUMNS = [('date', 'Date'), ('market', 'Market'), ('store', 'Store'),
           ('employee', 'Employee'), ('store_status', 'Opening Status'),
           ('opening_time', 'Opening Time'), ('camera_in', 'Camera In View'),
           ('rt_clockin', 'RT Clockin'), ('opening_status', 'Opening Status'),
           ('closing_time', 'Closing Time'), ('camera_out', 'Camera Out View'),
           ('rt_clockout', 'RT Clockout'), ('closing_status', 'Closing Status'),
           ('chargeback', 'Late Opening Chargeback')]
TIME_FIELDS = ('opening_time', 'closing_time', 'camera_in', 'camera_out')


def parse_datetime(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    value = ' '.join(clean(value).split())
    if not value or value.replace('/', '').replace(':', '').strip() == '':
        return None
    for fmt in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
                '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ReportError('invalid_punch_date')


def read_report(data):
    """RT-POS currently emits CSV despite btnExcel; also accept legacy XLS."""
    if data.startswith((b'\xd0\xcf\x11\xe0', b'\x09\x00', b'\x09\x02', b'\x09\x04', b'\x09\x08')):
        try:
            book = xlrd.open_workbook(file_contents=data)
            sheet = book.sheet_by_index(0)
            rows = []
            for n in range(sheet.nrows):
                rows.append([xlrd.xldate_as_datetime(c.value, book.datemode)
                             if c.ctype == xlrd.XL_CELL_DATE else c.value for c in sheet.row(n)])
        except (xlrd.XLRDError, IndexError, ValueError):
            raise ReportError('invalid_xls') from None
    else:
        text = data.decode('utf-8-sig', errors='replace')
        if '<html' in text[:2000].lower() or '<!doctype' in text[:2000].lower():
            raise ReportError('invalid_report_or_expired_cookies')
        delimiter = '\t' if '\t' in text.partition('\n')[0] else ','
        try:
            rows = list(csv.reader(StringIO(text), delimiter=delimiter, strict=True))
        except csv.Error:
            raise ReportError('invalid_csv') from None
    if not rows:
        raise ReportError('missing_headers')
    headers = {clean(v).lower(): i for i, v in enumerate(rows[0])}
    required = {'marketid', 'custno', 'company', 'name', 'lastname', 'clockintime', 'clockouttime'}
    if required - headers.keys():
        raise ReportError('report_columns_changed')
    result = {}
    for values in rows[1:]:
        if not any(clean(v) for v in values):
            continue
        if len(values) < max(headers[k] for k in required) + 1:
            raise ReportError('invalid_report_row')
        cell = lambda key: values[headers[key]] if key in headers else ''
        clock_in = parse_datetime(cell('clockintime'))
        if clock_in is None:
            # A missing date cannot advance the import watermark or be assigned to a day.
            raise ReportError('missing_clockin_date')
        clock_out = parse_datetime(cell('clockouttime'))
        if clock_out and clock_out < clock_in:
            raise ReportError('invalid_clockout_date')
        sid, store = clean(cell('custno')).upper(), clean(cell('company')).upper()
        if not sid and not store:
            raise ReportError('missing_store_identity')
        employee = ' '.join(filter(None, (clean(cell('name')), clean(cell('lastname'))))) or '-'
        key = sha256(json.dumps([sid, store, clean(cell('username')), employee, clock_in.isoformat()]).encode()).hexdigest()
        record = dict(punch_key=key, report_date=clock_in.date(), store_id=sid,
                      store=store, market=clean(cell('marketid')).upper(), employee=employee,
                      clock_in=clock_in, clock_out=clock_out)
        # Exact duplicate shifts collapse; a completed duplicate wins over an open one.
        if key not in result or (clock_out or datetime.min) > (result[key]['clock_out'] or datetime.min):
            result[key] = record
    return list(result.values())


def fetch_report(opener, start, end, deadline=None):
    payload = urlencode({'frmMarketID': '', 'frmStateID': '', 'frmRegionID': '',
                         'frmStoreType': '', 'frmStore': '', 'frmStart': start.strftime('%m/%d/%Y'),
                         'frmEnd': end.strftime('%m/%d/%Y'), 'btnExcel': 'click'}).encode()
    raw = read_source(opener, Request(REPORT_URL, data=payload, headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Referer': REPORT_URL}),
        MAX_REPORT_BYTES + 1, deadline=deadline)
    if len(raw) > MAX_REPORT_BYTES:
        raise ReportError('report_too_large')
    rows = read_report(raw)
    # RT-POS includes older, still-open shifts even when frmStart is later.
    # Assign days by clockintime and exclude carryovers from this replacement window.
    return [r for r in rows if start <= r['report_date'] <= end]


def sync_start(last_punch, last_complete, current):
    # Inclusive by design: refresh the last extracted clockintime date, including late clock-outs.
    return min(last_punch or last_complete or current.replace(day=1), current)


def seed_imports(conn, current, continuation=False):
    if continuation:
        return
    with conn.transaction():
        for source in SOURCES:
            punch = conn.execute('select max(report_date) as day from public.store_time_punches where source_id=%s', (source,)).fetchone()['day']
            complete = conn.execute("select max(report_date) as day from public.store_hours_imports where source_id=%s and status='complete'", (source,)).fetchone()['day']
            start = sync_start(punch, complete, current)
            conn.execute('''insert into public.store_hours_imports(source_id,report_date)
                select %s,d::date from generate_series(%s::date,%s::date,'1 day') d
                on conflict(source_id,report_date) do update set status='pending',error_code=null''', (source, start, current))
        conn.execute("update public.store_hours_imports set status='pending',error_code=null where status='error'")


def save_punches(conn, source, start, end, rows):
    with conn.transaction():
        conn.execute('delete from public.store_time_punches where source_id=%s and report_date between %s and %s', (source, start, end))
        if rows:
            fields = ('report_date', 'punch_key', 'store_id', 'market', 'store', 'employee', 'clock_in', 'clock_out')
            with conn.cursor() as cur:
                cur.executemany(f'''insert into public.store_time_punches(source_id,{','.join(fields)})
                    values({','.join(['%s'] * 9)})''', [(source, *(r[k] for k in fields)) for r in rows])
        counts = Counter(r['report_date'] for r in rows)
        with conn.cursor() as cur:
            cur.executemany('''update public.store_hours_imports set status='complete',loaded_at=now(),
                row_count=%s,error_code=null where source_id=%s and report_date=%s''',
                [(counts[start + timedelta(days=n)], source, start + timedelta(days=n)) for n in range((end-start).days+1)])


def source_worker(source, cookies):
    with connect() as conn:
        job = conn.execute("select min(report_date) as day from public.store_hours_imports where source_id=%s and status='pending'", (source,)).fetchone()['day']
        if not job:
            return {'source': source, 'completed': 0}
        end = min(job + timedelta(days=6), today())
        try:
            deadline = time.monotonic() + 200
            opener = open_source(cookies, deadline=deadline, report_url=REPORT_URL)
            rows = fetch_report(opener, job, end, deadline)
            save_punches(conn, source, job, end, rows)
            return {'source': source, 'completed': (end-job).days+1, 'rows': len(rows)}
        except (ReportError, OSError) as exc:
            code = source_error(exc)
            conn.execute("""update public.store_hours_imports set status='error',error_code=%s
                where source_id=%s and report_date between %s and %s""", (code, source, job, end))
            return {'source': source, 'completed': 0, 'error': code}


def run_sync(continuation=False):
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
            seed_imports(conn, today(), continuation)
            with ThreadPoolExecutor(max_workers=6) as pool:
                workers = list(pool.map(lambda s: source_worker(s, cookies.get(s, {})), SOURCES))
            counts = conn.execute("""select count(*) filter(where status='pending') as pending,
                count(*) filter(where status='error') as failed from public.store_hours_imports""").fetchone()
            return dict(status='partial' if counts['pending'] or counts['failed'] else 'complete',
                        remaining=counts['pending'] + counts['failed'], workers=workers, **counts)
        finally:
            conn.execute('select pg_advisory_unlock(%s)', (LOCK_ID,))


def seconds(value):
    if not value:
        return None
    if isinstance(value, str):
        value = wall_time.fromisoformat(value)
    return value.hour * 3600 + value.minute * 60 + value.second


def evaluate(row):
    """Only camera evidence determines compliance; scheduled times are never guessed."""
    opening, closing, camera_in, camera_out = (seconds(row.get(k)) for k in TIME_FIELDS)
    result = {'store_status': 'Open' if camera_in is not None else 'Pending camera review',
              'opening_status': 'Pending camera review', 'closing_status': 'Pending camera review',
              'chargeback': None}
    if camera_in is not None:
        if opening is None:
            result['opening_status'] = 'Schedule required'
        else:
            delay = camera_in - opening
            result['opening_status'] = 'Late' if delay >= 60 else 'On Time'
            threshold = {'houston': 5, 'reno': 5, 'dallas': 10}.get(row['market'].strip().casefold())
            result['chargeback'] = -10 if row['dealer'] == 'Connect' and threshold and delay >= threshold * 60 else 0
    if camera_out is not None:
        if closing is None:
            result['closing_status'] = 'Schedule required'
        else:
            # Treat a close after midnight as the next day for an overnight schedule.
            if opening is not None and closing <= opening:
                closing += 86400
                if camera_out < opening:
                    camera_out += 86400
            result['closing_status'] = 'Early' if closing - camera_out >= 60 else 'On Time'
    return result


def iso_time(value):
    return value.isoformat() if value is not None else None


def build_rows(roster, punches, reviews, imports, start, end):
    by_id = defaultdict(list)
    by_name = defaultdict(list)
    name_counts = Counter((s['dealer'], s['store'].strip().upper()) for s in roster)
    for punch in punches:
        dealer = SOURCES[punch['source_id']]
        by_id[(dealer, punch['store_id'], punch['report_date'])].append(punch)
        by_name[(dealer, punch['store'].strip().upper(), punch['report_date'])].append(punch)
    saved = {(r['dealer'], r['store_id'], r['report_date']): r for r in reviews}
    loaded = {(r['source_id'], r['report_date']): r for r in imports}
    source_ids = {dealer: source for source, dealer in SOURCES.items()}
    rows = []
    for n in range((end-start).days+1):
        day = start + timedelta(days=n)
        for store in roster:
            dealer, sid = store['dealer'], store['store_id']
            records = by_id.get((dealer, sid, day), [])
            name = store['store'].strip().upper()
            if not records and name_counts[dealer, name] == 1:
                records = by_name.get((dealer, name, day), [])
            first = min(records, key=lambda r: r['clock_in']) if records else None
            outs = [r['clock_out'] for r in records if r['clock_out']]
            review = saved.get((dealer, sid, day), {})
            schedule = scheduled_hours(store, day)
            imported = loaded.get((source_ids[dealer], day), {})
            row = dict(date=day.isoformat(), dealer=dealer, market=store['market'], store=store['store'], store_id=sid,
                       employee=first['employee'] if first else '-',
                       rt_clockin=first['clock_in'].isoformat() if first else None,
                       rt_clockout=max(outs).isoformat() if outs else None,
                       revision=review.get('revision', 0), source_status=imported.get('status', 'not_synced'),
                       schedule_period=schedule['period'],
                       scheduled_opening_time=iso_time(schedule.get('opening_time')),
                       scheduled_closing_time=iso_time(schedule.get('closing_time')),
                       **{k: iso_time(review.get(k) if review.get(k) is not None else schedule.get(k)) for k in TIME_FIELDS})
            row.update(evaluate(row))
            rows.append(row)
    return rows


def report_range():
    try:
        start = date.fromisoformat(request.args.get('start') or today().isoformat())
        end = date.fromisoformat(request.args.get('end') or start.isoformat())
    except ValueError:
        raise PortalError('Choose valid report dates.') from None
    if start > end or end > today() or (end-start).days > 366:
        raise PortalError('Choose up to 367 days ending today or earlier.')
    return start, end


def report_data(start, end):
    with connect() as conn:
        roster = active_roster(conn)
        punches = conn.execute('select * from public.store_time_punches where report_date between %s and %s', (start, end)).fetchall()
        reviews = conn.execute('select * from public.store_hours_reviews where report_date between %s and %s', (start, end)).fetchall()
        imports = conn.execute('select * from public.store_hours_imports where report_date between %s and %s', (start, end)).fetchall()
        earliest = conn.execute('select min(report_date) as day from public.store_hours_imports').fetchone()['day']
    dealer, market, sid = (request.args.get(k, '') for k in ('dealer', 'market', 'store'))
    selected = [s for s in roster if not dealer or s['dealer'] == dealer]
    markets = sorted({s['market'] for s in selected})
    selected = [s for s in selected if not market or s['market'] == market]
    stores = [{'id': s['dealer'] + ':' + s['store_id'], 'name': s['store']} for s in selected]
    selected = [s for s in selected if not sid or s['dealer'] + ':' + s['store_id'] == sid]
    if len(selected) * ((end-start).days+1) > 20000:
        raise PortalError('Select a dealer, market, or shorter date range (up to 20,000 rows).')
    rows = build_rows(selected, punches, reviews, imports, start, end)
    relevant_sources = {s for s, d in SOURCES.items() if d in {r['dealer'] for r in selected}}
    relevant = [i for i in imports if i['source_id'] in relevant_sources]
    updated = max((i['loaded_at'] for i in relevant if i['loaded_at']), default=None)
    return dict(rows=rows, start=start.isoformat(), end=end.isoformat(), today=today().isoformat(),
                earliest=(earliest or today().replace(day=1)).isoformat(),
                dealers=list(COLORS), markets=markets, stores=stores,
                updated_at=updated.isoformat() if updated else None,
                coverage={'complete': sum(i['status'] == 'complete' for i in relevant),
                          'expected': len(relevant_sources) * ((end-start).days+1),
                          'errors': sorted({SOURCES[i['source_id']] for i in relevant if i['status'] == 'error'})})


def display_value(key, value):
    if key == 'chargeback':
        return 'Pending' if value is None else ('-$10' if value == -10 else '$0')
    if key in TIME_FIELDS or key in ('rt_clockin', 'rt_clockout'):
        if not value:
            return {'rt_clockin': 'No Clock In', 'rt_clockout': 'No Clock Out'}.get(key, '-')
        value = datetime.fromisoformat(value).time() if 'T' in value else wall_time.fromisoformat(value)
        return value.strftime('%I:%M:%S %p').lstrip('0')
    return value


def excel_report(data):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Store Opening Closing'
    sheet.append([f"STORE OPENING / CLOSING | {data['start']} to {data['end']}"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))
    sheet.append([heading for _, heading in COLUMNS])
    for row in data['rows']:
        sheet.append([row[key] if key == 'chargeback' and row[key] is not None else display_value(key, row[key]) for key, _ in COLUMNS])
        for col, (key, _) in enumerate(COLUMNS, 1):
            cell = sheet.cell(sheet.max_row, col)
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Imported names are never executable Excel formulas.
            if key == 'chargeback' and isinstance(cell.value, int):
                cell.number_format = '$0;[Red]-$0'
            if row[key] in ('Late', 'Early') or (key == 'chargeback' and row[key] == -10):
                cell.fill = PatternFill('solid', fgColor='FFC7CE')
            elif row[key] in ('Open', 'On Time'):
                cell.fill = PatternFill('solid', fgColor='C6EFCE')
            if key in ('rt_clockin', 'rt_clockout') and not row[key]:
                cell.font = Font(color='C00000')
    for row in sheet.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.fill = PatternFill('solid', fgColor='203C66')
            cell.font = Font(color='FFFFFF', bold=True)
            cell.alignment = Alignment(horizontal='center')
    widths = [14, 20, 34, 30, 27, 17, 18, 18, 27, 17, 18, 18, 27, 25]
    for n, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(n)].width = width
    sheet.freeze_panes = 'E3'
    sheet.auto_filter.ref = f'A2:N{sheet.max_row}'
    meta = book.create_sheet('Report details')
    for values in [('Source', REPORT_URL), ('From', data['start']), ('To', data['end']),
                   ('Latest sync', data['updated_at'] or 'Not synced'),
                   ('Source coverage', f"{data['coverage']['complete']}/{data['coverage']['expected']} account-days"),
                   ('Rules', 'Late: 1 minute after opening. Early: 1 minute before closing.'),
                   ('Connect chargebacks', 'Houston/Reno: 5 minutes; Dallas: 10 minutes. Charge: -$10.'),
                   ('Pending', 'Camera review and scheduled hours are required. RT punches do not determine compliance.'),
                   ('RT aggregation', 'Earliest clock-in and its employee; latest clock-out per store/day.'),
                   ('Schedules', 'OPENING TIMING FOR ALL DEALERS.xlsx: Monday-Friday, Saturday, Sunday; date-specific overrides take priority.'),
                   ('Schedule correction', 'Connect Monday-Saturday opening is 10:00 AM, confirmed by the user.'),
                   ('Times', 'Source and camera times are store-local wall times.')]:
        meta.append(values)
    meta.column_dimensions['A'].width = 26
    meta.column_dimensions['B'].width = 110
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return output


def save_review(payload, user_id):
    dealer, sid = payload.get('dealer'), payload.get('store_id')
    try:
        day = date.fromisoformat(payload.get('date', ''))
    except (ValueError, TypeError):
        raise PortalError('Choose a valid report date.') from None
    revision = payload.get('revision', 0)
    if day > today() or dealer not in SOURCES.values() or not isinstance(sid, str) or not sid or len(sid) > 100:
        raise PortalError('Choose a valid store and date.')
    if type(revision) is not int or revision < 0:
        raise PortalError('Reload this review before editing.')
    times = {}
    for key in TIME_FIELDS:
        value = payload.get(key)
        if value is None or value == '':
            times[key] = None
        elif isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}(:\d{2})?', value):
            try:
                times[key] = wall_time.fromisoformat(value)
            except ValueError:
                raise PortalError('Enter valid opening, closing, and camera times.') from None
        else:
            raise PortalError('Enter valid opening, closing, and camera times.')
    with connect() as conn:
        with conn.transaction():
            store = next((s for s in active_roster(conn) if s['dealer'] == dealer and s['store_id'] == sid), None)
            if store is None:
                raise PortalError('This store is no longer in the active Calling Tree.', 409)
            schedule = scheduled_hours(store, day)
            # Saving a camera observation must not freeze inherited workbook hours.
            # Only a time differing from the recurring schedule is a date-specific override.
            for key in ('opening_time', 'closing_time'):
                if times[key] == schedule.get(key):
                    times[key] = None
            result = conn.execute('''insert into public.store_hours_reviews
                (dealer,store_id,report_date,opening_time,closing_time,camera_in,camera_out,updated_by)
                select %s,%s,%s,%s,%s,%s,%s,%s where %s=0
                on conflict(dealer,store_id,report_date) do nothing returning revision''',
                (dealer, sid, day, *(times[k] for k in TIME_FIELDS), user_id, revision)).fetchone()
            if not result:
                result = conn.execute('''update public.store_hours_reviews set opening_time=%s,closing_time=%s,
                    camera_in=%s,camera_out=%s,updated_by=%s,updated_at=now(),revision=revision+1
                    where dealer=%s and store_id=%s and report_date=%s and revision=%s returning revision''',
                    (*(times[k] for k in TIME_FIELDS), user_id, dealer, sid, day, revision)).fetchone()
            if not result:
                raise PortalError('Someone updated this review. Reload the page before saving again.', 409)
    return result['revision']


def register_store_hours(app):
    @app.get('/api/internal/store-hours')
    @require_user()
    def get_report():
        return jsonify(report_data(*report_range()))

    @app.post('/api/internal/store-hours/refresh')
    @require_user(admin=True)
    def sync_report():
        return jsonify(run_sync(body().get('continue') is True))

    @app.post('/api/internal/store-hours/review')
    @require_user()
    def review_report():
        return jsonify(status='saved', revision=save_review(body(), g.portal_user['id']))

    @app.get('/api/internal/store-hours/export')
    @require_user()
    def export_report():
        data = report_data(*report_range())
        return send_file(excel_report(data), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=f"store-opening-closing-{data['start']}-{data['end']}.xlsx")
