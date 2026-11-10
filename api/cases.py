"""Private case messages, recipient inboxes, and administrator reviews."""
import base64
import binascii
from datetime import date, datetime
from io import BytesIO
from pathlib import PureWindowsPath
import re
from uuid import UUID

from flask import g, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

from api.portal import PortalError, body, require_user, text_field, valid_id
from api.sales import connect, today

CASE_TYPES = ('Payment Fraud', 'Fraud Transaction (Non Up)', 'Rejections',
              'Suspicious Activity', 'Theft', 'Refund (All customer)',
              'Missed Opportunity', 'Over Accessory added in invoice', 'Custom')
MAX_IMAGE_BYTES = 2 * 1024 * 1024
PAGE_SIZE = 50


def serial(row):
    return {k: v.isoformat() if isinstance(v, (date, datetime)) else str(v) if isinstance(v, UUID) else v
            for k, v in row.items()}


def page_offset():
    try:
        value = int(request.args.get('offset', '0'))
    except ValueError:
        raise PortalError('Invalid page.') from None
    if value < 0 or value > 1000000:
        raise PortalError('Invalid page.')
    return value


def validate_images(items):
    if not isinstance(items, list) or len(items) > 5:
        raise PortalError('Attach up to 5 pictures, totaling 2 MB.')
    result, total = [], 0
    for item in items:
        if not isinstance(item, dict):
            raise PortalError('Invalid picture.')
        filename = text_field(item, 'filename', 180)
        encoded = item.get('content')
        if not isinstance(encoded, str) or len(encoded) > 2800000:
            raise PortalError('Pictures must total 2 MB or less.')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise PortalError('A picture upload is incomplete.') from None
        total += len(data)
        if not data or total > MAX_IMAGE_BYTES:
            raise PortalError('Pictures must total 2 MB or less.')
        try:
            with Image.open(BytesIO(data)) as check:
                fmt = check.format
                if fmt not in ('JPEG', 'PNG', 'WEBP') or check.width * check.height > 16000000:
                    raise PortalError('Use JPG, PNG, or WebP pictures up to 16 megapixels.')
                check.verify()
            # Re-encoding removes embedded metadata and non-image payloads.
            with Image.open(BytesIO(data)) as original:
                original.load()
                picture = ImageOps.exif_transpose(original).convert('RGB' if fmt == 'JPEG' else 'RGBA')
                picture.info.clear()
                output = BytesIO()
                picture.save(output, format=fmt)
                safe = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise PortalError('One attachment is not a valid picture.') from None
        extension = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[fmt]
        filename = (re.sub(r'[\x00-\x1f\x7f]', '', PureWindowsPath(filename).stem)[:160] or 'picture') + extension
        result.append({'filename': filename, 'content_type': 'image/' + ('jpeg' if fmt == 'JPEG' else fmt.lower()), 'data': safe})
    if sum(len(i['data']) for i in result) > MAX_IMAGE_BYTES:
        raise PortalError('Pictures must total 2 MB or less after processing.')
    return result


def validate_draft(payload):
    kind = text_field(payload, 'case_type', 150)
    if kind not in CASE_TYPES:
        raise PortalError('Choose a valid case type.')
    if kind == 'Custom':
        kind = text_field(payload, 'custom_type', 150)
    try:
        day = date.fromisoformat(text_field(payload, 'violation_date', 10))
    except ValueError:
        raise PortalError('Choose a valid violation date.') from None
    if day > today():
        raise PortalError('The violation date cannot be in the future.')
    recipients, seen = [], set()
    for category in ('to', 'cc'):
        values = payload.get(category, [])
        if not isinstance(values, list) or len(values) > 30 or (category == 'to' and not values):
            raise PortalError('Select at least one To recipient and up to 30 total recipients.')
        for value in values:
            if not isinstance(value, str):
                raise PortalError('Choose valid recipients.')
            uid = valid_id(value)
            if uid in seen:
                raise PortalError('Select each recipient only once across To and CC.')
            seen.add(uid)
            recipients.append((uid, category))
    if len(recipients) > 30:
        raise PortalError('Select up to 30 total recipients.')
    return {
        'request_id': valid_id(text_field(payload, 'request_id', 36)),
        'violation_date': day, 'case_type': kind,
        'employee_ntid': text_field(payload, 'employee_ntid', 80).upper(),
        'employee_name': text_field(payload, 'employee_name', 150),
        'subject': text_field(payload, 'subject', 200),
        'body': text_field(payload, 'body', 20000),
        'recipients': recipients, 'attachments': validate_images(payload.get('attachments', [])),
    }


def visible_case(conn, case_id):
    uid = g.portal_user['id']
    row = conn.execute('''select c.* from public.violation_cases c where c.id=%s
        and (%s or c.submitted_by=%s or exists(select 1 from public.case_recipients r
        where r.case_id=c.id and r.user_id=%s))''',
        (valid_id(case_id), g.portal_user['role'] == 'admin', uid, uid)).fetchone()
    if not row:
        raise PortalError('Case not found.', 404)
    return row


def register_cases(app):
    @app.get('/api/internal/cases/recipients')
    @require_user()
    def recipients():
        with connect() as conn:
            rows = conn.execute('''select id,username,display_name from public.portal_users
                where active=true order by display_name,username''').fetchall()
        return jsonify(users=[serial(r) for r in rows], case_types=CASE_TYPES)

    @app.post('/api/internal/cases')
    @require_user()
    def send_case():
        draft = validate_draft(body())
        uid = g.portal_user['id']
        with connect() as conn, conn.transaction():
            # One transaction delivers the case, pictures, and all To/CC notifications.
            recipient_users = conn.execute('''select id,display_name,username from public.portal_users
                where active=true and id=any(%s::uuid[]) for share''',
                ([r[0] for r in draft['recipients']],)).fetchall()
            names = {str(r['id']): r['display_name'] or r['username'] for r in recipient_users}
            if len(names) != len(draft['recipients']):
                raise PortalError('A selected recipient is unavailable. Refresh the recipient list.')
            fields = ('request_id', 'violation_date', 'employee_ntid', 'employee_name', 'case_type', 'subject', 'body')
            row = conn.execute(f'''insert into public.violation_cases(submitted_by,sender_name,{','.join(fields)})
                values({','.join(['%s'] * (len(fields)+2))}) on conflict(submitted_by,request_id) do nothing returning id''',
                (uid, g.portal_user['display_name'] or g.portal_user['username'], *(draft[k] for k in fields))).fetchone()
            if not row:
                existing = conn.execute('select id from public.violation_cases where submitted_by=%s and request_id=%s',
                                        (uid, draft['request_id'])).fetchone()
                return jsonify(id=str(existing['id']), message='Case already sent.'), 200
            cid = row['id']
            with conn.cursor() as cur:
                cur.executemany('''insert into public.case_recipients(case_id,user_id,kind,recipient_name)
                    values(%s,%s,%s,%s)''', [(cid, recipient, kind, names[recipient]) for recipient, kind in draft['recipients']])
                if draft['attachments']:
                    cur.executemany('''insert into public.case_attachments(case_id,filename,content_type,data)
                        values(%s,%s,%s,%s)''', [(cid, a['filename'], a['content_type'], a['data']) for a in draft['attachments']])
        return jsonify(id=str(cid), message='Case sent. To and CC recipients have been notified in Inbox.'), 201

    @app.get('/api/internal/cases')
    @require_user()
    def list_cases():
        folder = request.args.get('folder', 'sent')
        if folder not in ('sent', 'inbox', 'all'):
            raise PortalError('Invalid case folder.')
        if folder == 'all' and g.portal_user['role'] != 'admin':
            raise PortalError('Administrator access is required.', 403)
        uid, offset = g.portal_user['id'], page_offset()
        where, args = [], [uid]
        if folder == 'inbox':
            where.append('r.user_id is not null')
        elif folder == 'sent':
            where.append('c.submitted_by=%s'); args.append(uid)
        status = request.args.get('status', '')
        if status:
            if status not in ('pending', 'approved', 'not_approved'):
                raise PortalError('Invalid case status.')
            where.append('c.status=%s'); args.append(status)
        clause = ' and '.join(where) or 'true'
        with connect() as conn:
            rows = conn.execute(f'''select c.id,c.sender_name,c.subject,c.violation_date,c.employee_ntid,
                c.employee_name,c.case_type,c.status,c.submitted_at,c.revision,
                (r.user_id is not null and r.read_at is null) as unread,
                (select count(*) from public.case_attachments a where a.case_id=c.id) as attachment_count
                from public.violation_cases c left join public.case_recipients r on r.case_id=c.id and r.user_id=%s
                where {clause} order by c.submitted_at desc,c.id desc limit %s offset %s''',
                (*args, PAGE_SIZE+1, offset)).fetchall()
        return jsonify(cases=[serial(r) for r in rows[:PAGE_SIZE]], has_more=len(rows)>PAGE_SIZE)

    @app.get('/api/internal/cases/unread')
    @require_user()
    def unread_count():
        with connect() as conn:
            count = conn.execute('select count(*) as count from public.case_recipients where user_id=%s and read_at is null',
                                 (g.portal_user['id'],)).fetchone()['count']
        return jsonify(count=count)

    @app.get('/api/internal/cases/report')
    @require_user(admin=True)
    def case_report():
        try:
            start = date.fromisoformat(request.args.get('start', ''))
            end = date.fromisoformat(request.args.get('end', ''))
        except ValueError:
            raise PortalError('Select a start and end date.') from None
        if start > end:
            raise PortalError('The end date must be on or after the start date.')
        offset = page_offset()
        with connect() as conn, conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            ranking = conn.execute('''select c.submitted_by as user_id,u.username,
                coalesce(nullif(u.display_name,''),u.username) as user_name,count(*) as submitted,
                count(*) filter(where c.status='approved') as approved,
                count(*) filter(where c.status='not_approved') as not_approved,
                count(*) filter(where c.status='pending') as pending
                from public.violation_cases c join public.portal_users u on u.id=c.submitted_by
                where c.violation_date between %s and %s group by c.submitted_by,u.username,u.display_name
                order by submitted desc,user_name,user_id''', (start,end)).fetchall()
            rows = conn.execute('''select c.id,c.violation_date as date,c.sender_name as "user",
                c.employee_ntid,c.employee_name,c.case_type from public.violation_cases c
                where c.violation_date between %s and %s
                order by c.violation_date desc,c.submitted_at desc,c.id desc limit %s offset %s''',
                (start,end,PAGE_SIZE+1,offset)).fetchall()
        return jsonify(rows=[serial(r) for r in rows[:PAGE_SIZE]], ranking=[serial(r) for r in ranking],
                       total=sum(r['submitted'] for r in ranking), has_more=len(rows)>PAGE_SIZE,
                       start=start.isoformat(), end=end.isoformat())

    @app.get('/api/internal/cases/<case_id>')
    @require_user()
    def case_detail(case_id):
        with connect() as conn:
            row = visible_case(conn, case_id)
            recipients = conn.execute('''select user_id,kind,recipient_name,read_at from public.case_recipients
                where case_id=%s order by kind desc,recipient_name''', (row['id'],)).fetchall()
            attachments = conn.execute('''select id,filename,content_type,octet_length(data) as size
                from public.case_attachments where case_id=%s order by filename,id''', (row['id'],)).fetchall()
            reviews = conn.execute('''select r.status,r.reviewed_at,u.display_name as reviewer
                from public.case_reviews r join public.portal_users u on u.id=r.reviewed_by
                where r.case_id=%s order by r.reviewed_at,r.id''', (row['id'],)).fetchall()
        result = serial(row)
        result.pop('request_id', None)
        return jsonify(case=result, recipients=[serial(r) for r in recipients],
                       attachments=[serial(a) for a in attachments], reviews=[serial(r) for r in reviews])

    @app.post('/api/internal/cases/<case_id>/read')
    @require_user()
    def read_case(case_id):
        with connect() as conn:
            row = visible_case(conn, case_id)
            conn.execute('''update public.case_recipients set read_at=coalesce(read_at,now())
                where case_id=%s and user_id=%s''', (row['id'],g.portal_user['id']))
        return jsonify(message='Marked as read.')

    @app.patch('/api/internal/cases/<case_id>/review')
    @require_user(admin=True)
    def review_case(case_id):
        payload = body()
        status, revision = payload.get('status'), payload.get('revision')
        if status not in ('approved','not_approved') or type(revision) is not int or revision < 1:
            raise PortalError('Choose Approved or Not Approved.')
        with connect() as conn, conn.transaction():
            row = visible_case(conn, case_id)
            updated = conn.execute('''update public.violation_cases set status=%s,reviewed_by=%s,
                reviewed_at=now(),revision=revision+1 where id=%s and revision=%s returning id''',
                (status,g.portal_user['id'],row['id'],revision)).fetchone()
            if not updated:
                raise PortalError('Another administrator reviewed this case. Refresh before reviewing again.',409)
            conn.execute('insert into public.case_reviews(case_id,reviewed_by,status) values(%s,%s,%s)',
                         (row['id'],g.portal_user['id'],status))
            conn.execute('update public.case_recipients set read_at=null where case_id=%s',(row['id'],))
        return jsonify(message='Case '+('approved.' if status=='approved' else 'marked Not Approved.'))

    @app.get('/api/internal/cases/<case_id>/attachments/<attachment_id>')
    @require_user()
    def attachment(case_id, attachment_id):
        with connect() as conn:
            row = visible_case(conn, case_id)
            item = conn.execute('select filename,content_type,data from public.case_attachments where id=%s and case_id=%s',
                                (valid_id(attachment_id),row['id'])).fetchone()
        if not item:
            raise PortalError('Picture not found.',404)
        return send_file(BytesIO(bytes(item['data'])), mimetype=item['content_type'],
                         download_name=item['filename'], as_attachment=request.args.get('download')=='1', max_age=0)
