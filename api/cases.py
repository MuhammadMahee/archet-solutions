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
from psycopg.types.json import Jsonb

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


def current_sender(row):
    return str(row.get('sender_id') or row['submitted_by'])


def can_edit(row):
    return g.portal_user['role']=='admin' or current_sender(row)==str(g.portal_user['id'])


def visible_case(conn, case_id, lock=False):
    uid = g.portal_user['id']
    row = conn.execute('''select c.* from public.violation_cases c where c.id=%s and c.deleted_at is null
        and (%s or coalesce(c.sender_id,c.submitted_by)=%s or exists(select 1 from public.case_recipients r
        where r.case_id=c.id and r.user_id=%s))''' + (' for update of c' if lock else ''),
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
                existing = conn.execute('select id,deleted_at from public.violation_cases where submitted_by=%s and request_id=%s',
                                        (uid, draft['request_id'])).fetchone()
                if existing['deleted_at'] is not None:
                    raise PortalError('This draft was already sent and deleted. Start a new case.',409)
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
        where, args = ['c.deleted_at is null'], [uid]
        if folder == 'inbox':
            where.append('r.user_id is not null')
        elif folder == 'sent':
            where.append('coalesce(c.sender_id,c.submitted_by)=%s'); args.append(uid)
        status = request.args.get('status', '')
        if status:
            if status not in ('pending', 'approved', 'not_approved'):
                raise PortalError('Invalid case status.')
            where.append('c.status=%s'); args.append(status)
        clause = ' and '.join(where) or 'true'
        with connect() as conn:
            rows = conn.execute(f'''select c.id,coalesce(c.sender_id,c.submitted_by) as sender_id,c.sender_name,c.subject,c.violation_date,c.employee_ntid,
                c.employee_name,c.case_type,c.status,c.submitted_at,c.revision,
                (r.user_id is not null and r.read_at is null) as unread,
                (select count(*) from public.case_attachments a where a.case_id=c.id) as attachment_count
                from public.violation_cases c left join public.case_recipients r on r.case_id=c.id and r.user_id=%s
                where {clause} order by c.submitted_at desc,c.id desc limit %s offset %s''',
                (*args, PAGE_SIZE+1, offset)).fetchall()
        return jsonify(cases=[{**serial(r),'can_edit':can_edit(r)} for r in rows[:PAGE_SIZE]], has_more=len(rows)>PAGE_SIZE)

    @app.get('/api/internal/cases/unread')
    @require_user()
    def unread_count():
        with connect() as conn:
            count = conn.execute('''select count(*) as count from public.case_recipients r
                join public.violation_cases c on c.id=r.case_id
                where r.user_id=%s and r.read_at is null and c.deleted_at is null''',
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
            ranking = conn.execute('''select coalesce(c.sender_id,c.submitted_by) as user_id,u.username,
                coalesce(nullif(u.display_name,''),u.username) as user_name,count(*) as submitted,
                count(*) filter(where c.status='approved') as approved,
                count(*) filter(where c.status='not_approved') as not_approved,
                count(*) filter(where c.status='pending') as pending
                from public.violation_cases c join public.portal_users u on u.id=coalesce(c.sender_id,c.submitted_by)
                where c.deleted_at is null and c.violation_date between %s and %s group by coalesce(c.sender_id,c.submitted_by),u.username,u.display_name
                order by submitted desc,user_name,user_id''', (start,end)).fetchall()
            rows = conn.execute('''select c.id,c.violation_date as date,c.sender_name as "user",
                c.employee_ntid,c.employee_name,c.case_type from public.violation_cases c
                where c.deleted_at is null and c.violation_date between %s and %s
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
            edits = conn.execute('''select e.edited_at,e.changed_fields,u.display_name as editor
                from public.case_edits e join public.portal_users u on u.id=e.edited_by
                where e.case_id=%s order by e.id''',(row['id'],)).fetchall()
        result = serial(row)
        result.pop('request_id', None)
        result.update(sender_id=current_sender(row),can_edit=can_edit(row))
        return jsonify(case=result, recipients=[serial(r) for r in recipients],
                       attachments=[serial(a) for a in attachments], reviews=[serial(r) for r in reviews],
                       edits=[serial(e) for e in edits])

    @app.patch('/api/internal/cases/<case_id>')
    @require_user()
    def edit_case(case_id):
        payload=body()
        admin=g.portal_user['role']=='admin'
        content_fields=('violation_date','employee_ntid','employee_name','case_type','subject','body')
        allowed={'revision','to','cc'}
        if admin:
            allowed.update((*content_fields,'custom_type','sender_id','attachments','remove_attachments'))
        if set(payload)-allowed:
            raise PortalError('Admins can edit case details. Senders may edit only To and CC.',403)
        revision=payload.get('revision')
        if type(revision) is not int or revision<1:
            raise PortalError('Refresh the case before editing.')
        with connect() as conn, conn.transaction():
            row=visible_case(conn,case_id,lock=True)
            if not can_edit(row):
                raise PortalError('Only admins and the current sender can edit this case.',403)
            if row['revision']!=revision:
                raise PortalError('This case was changed. Reopen Edit to load the latest version.',409)
            previous_recipients=conn.execute('select user_id,kind,recipient_name from public.case_recipients where case_id=%s',(row['id'],)).fetchall()
            old_pictures=conn.execute('select id,filename,octet_length(data) as size from public.case_attachments where case_id=%s order by id',(row['id'],)).fetchall()
            merged={k:row[k] for k in content_fields}
            merged['violation_date']=row['violation_date'].isoformat()
            if merged['case_type'] not in CASE_TYPES or merged['case_type']=='Custom':
                merged.update(case_type='Custom',custom_type=row['case_type'])
            merged.update({k:v for k,v in payload.items() if k in (*content_fields,'custom_type','attachments')})
            for kind in ('to','cc'):
                merged[kind]=payload.get(kind,[str(r['user_id']) for r in previous_recipients if r['kind']==kind])
            merged['request_id']=str(row['request_id'])
            draft=validate_draft(merged)
            recipient_ids=[uid for uid,kind in draft['recipients']]
            existing_ids={str(r['user_id']) for r in previous_recipients}
            recipient_users=conn.execute('''select id,display_name,username,active from public.portal_users
                where id=any(%s::uuid[]) for share''',(recipient_ids,)).fetchall()
            if len(recipient_users)!=len(recipient_ids) or any(not r['active'] and str(r['id']) not in existing_ids for r in recipient_users):
                raise PortalError('A selected recipient is unavailable. Refresh the recipient list.')
            names={str(r['id']):r['display_name'] or r['username'] for r in recipient_users}
            sender=current_sender(row)
            if 'sender_id' in payload:
                sender=valid_id(text_field(payload,'sender_id',36))
            sender_name=row['sender_name']
            if sender!=current_sender(row):
                account=conn.execute('select display_name,username from public.portal_users where id=%s and active=true for share',(sender,)).fetchone()
                if not account:
                    raise PortalError('Choose an active user as the sender.')
                sender_name=account['display_name'] or account['username']
            remove=payload.get('remove_attachments',[])
            if not isinstance(remove,list) or any(not isinstance(a,str) for a in remove):
                raise PortalError('Choose valid pictures to remove.')
            remove={valid_id(a) for a in remove}
            if not remove<={str(a['id']) for a in old_pictures}:
                raise PortalError('A selected picture does not belong to this case.')
            retained=[a for a in old_pictures if str(a['id']) not in remove]
            if len(retained)+len(draft['attachments'])>5 or sum(a['size'] for a in retained)+sum(len(a['data']) for a in draft['attachments'])>MAX_IMAGE_BYTES:
                raise PortalError('Attach up to 5 pictures, totaling 2 MB.')
            changes=[k for k in content_fields if draft[k]!=row[k]]
            if sender!=current_sender(row):changes.append('sender')
            if remove or draft['attachments']:changes.append('pictures')
            reset_review=bool(changes)
            for kind in ('to','cc'):
                old={str(r['user_id']) for r in previous_recipients if r['kind']==kind}
                new={uid for uid,k in draft['recipients'] if k==kind}
                if old!=new:changes.append(kind)
            if not changes:
                return jsonify(message='No changes to save.')
            before={**serial({k:row[k] for k in content_fields}),'sender_id':current_sender(row),
                    'sender_name':row['sender_name'],'status':row['status'],
                    'recipients':[serial(r) for r in previous_recipients],'pictures':[serial(a) for a in old_pictures]}
            conn.execute(f'''update public.violation_cases set {','.join(k+'=%s' for k in content_fields)},
                sender_id=%s,sender_name=%s,edited_by=%s,edited_at=now(),revision=revision+1,
                status=%s,reviewed_by=%s,reviewed_at=%s where id=%s''',
                (*(draft[k] for k in content_fields),sender,sender_name,g.portal_user['id'],
                 'pending' if reset_review else row['status'],None if reset_review else row['reviewed_by'],
                 None if reset_review else row['reviewed_at'],row['id']))
            conn.execute('delete from public.case_recipients where case_id=%s and not(user_id=any(%s::uuid[]))',(row['id'],recipient_ids))
            with conn.cursor() as cur:
                cur.executemany('''insert into public.case_recipients(case_id,user_id,kind,recipient_name)
                    values(%s,%s,%s,%s) on conflict(case_id,user_id) do update
                    set kind=excluded.kind,recipient_name=excluded.recipient_name,read_at=null''',
                    [(row['id'],uid,kind,names[uid]) for uid,kind in draft['recipients']])
                if remove:
                    conn.execute('delete from public.case_attachments where case_id=%s and id=any(%s::uuid[])',(row['id'],list(remove)))
                if draft['attachments']:
                    cur.executemany('insert into public.case_attachments(case_id,filename,content_type,data) values(%s,%s,%s,%s)',
                                    [(row['id'],a['filename'],a['content_type'],a['data']) for a in draft['attachments']])
            after={**serial({k:draft[k] for k in content_fields}),'sender_id':sender,'sender_name':sender_name,
                   'status':'pending' if reset_review else row['status'],
                   'recipients':[{'user_id':uid,'kind':kind,'recipient_name':names[uid]} for uid,kind in draft['recipients']],
                   'pictures':[serial(a) for a in conn.execute('select id,filename,octet_length(data) as size from public.case_attachments where case_id=%s order by id',(row['id'],)).fetchall()]}
            conn.execute('insert into public.case_edits(case_id,edited_by,changed_fields,before_state,after_state) values(%s,%s,%s,%s,%s)',
                         (row['id'],g.portal_user['id'],changes,Jsonb(before),Jsonb(after)))
        return jsonify(message='Case updated. Recipients have been notified in Inbox.'+
                       (' The case is pending review.' if reset_review else ''))

    @app.delete('/api/internal/cases/<case_id>')
    @require_user()
    def delete_case(case_id):
        revision=body().get('revision')
        if type(revision) is not int or revision<1:
            raise PortalError('Refresh the case before deleting.')
        with connect() as conn, conn.transaction():
            row=visible_case(conn,case_id,lock=True)
            if not can_edit(row):
                raise PortalError('Only admins and the current sender can delete this case.',403)
            if row['revision']!=revision:
                raise PortalError('This case was changed. Refresh before deleting it.',409)
            conn.execute('''update public.violation_cases set deleted_at=now(),deleted_by=%s,
                revision=revision+1 where id=%s''',(g.portal_user['id'],row['id']))
        return jsonify(message='Case deleted from history, Inbox, and reports.')

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
                reviewed_at=now(),revision=revision+1 where id=%s and revision=%s and deleted_at is null returning id''',
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
