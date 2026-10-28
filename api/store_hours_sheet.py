"""Shared spreadsheet columns, cell presentation, and filtered sheet exports."""
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from flask import g, jsonify, request, send_file
from psycopg.types.json import Jsonb

from api.portal import PortalError, body, require_user

NUMBER_FORMATS = {'auto','text','number','currency','percent','date','time'}
FONT_FAMILIES = {'Arial','Calibri','Aptos','Cambria','Times New Roman','Georgia','Verdana','Tahoma','Trebuchet MS','Segoe UI','Courier New','Consolas'}
BORDER_STYLES = {'none','thin','medium','thick','dashed','dotted','double'}
FORMAT_KEYS = {'bold','italic','underline','color','background','align','wrap','font_size','font_family','borders','number_format'}


def settings(conn, lock=False):
    row = conn.execute('select * from public.store_hours_sheet_settings where id=true' + (' for update' if lock else '')).fetchone()
    return dict(columns=row['columns'], revision=row['revision'])


def validate_format(value):
    if not isinstance(value,dict) or set(value)-FORMAT_KEYS:
        raise PortalError('Choose valid cell formatting.')
    for key,item in value.items():
        valid = False
        if key in ('bold','italic','underline','wrap'):
            valid = type(item) is bool
        elif key in ('color','background'):
            valid = isinstance(item,str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}',item))
        elif key=='align':
            valid = item in ('left','center','right')
        elif key=='font_size':
            valid = type(item) is int and 8 <= item <= 28
        elif key=='font_family':
            valid = isinstance(item,str) and item in FONT_FAMILIES
        elif key=='borders':
            valid = isinstance(item,dict) and not set(item)-{'top','bottom','left','right'}
            if valid:
                valid = all(isinstance(side,dict) and set(side)=={'style','color'}
                            and isinstance(side['style'],str) and side['style'] in BORDER_STYLES
                            and isinstance(side['color'],str) and re.fullmatch(r'#[0-9a-fA-F]{6}',side['color'])
                            for side in item.values())
        elif key=='number_format':
            valid = isinstance(item,str) and item in NUMBER_FORMATS
        if not valid:
            raise PortalError('Choose valid cell formatting.')
    return value


def validate_row_extras(payload, row, config, default_keys):
    custom = {c['id']:c for c in config['columns']}
    result = []
    for field in ('custom_cells','cell_formats'):
        prior = row.get(field) or {}
        values = payload.get(field,prior)
        if not isinstance(values,dict) or len(values)>len(custom)+len(default_keys):
            raise PortalError('Reload the spreadsheet before saving these cells.')
        allowed = set(custom) | (default_keys if field=='cell_formats' else set())
        if set(values)-allowed:
            raise PortalError('This column no longer exists. Reload the spreadsheet.',409)
        clean = {k:v for k,v in prior.items() if custom.get(k,{}).get('deleted')}
        for key,value in values.items():
            if custom.get(key,{}).get('deleted'):
                if prior.get(key)!=value:
                    raise PortalError('This column was removed. Reload the spreadsheet.',409)
                continue
            if field=='cell_formats':
                parsed=validate_format(value)
                if parsed:
                    clean[key]=parsed
            else:
                if value is not None and (not isinstance(value,str) or len(value)>1000 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',value)):
                    raise PortalError('Custom cells accept text up to 1,000 characters.')
                clean[key]=value
        result.append(clean)
    return result


def change_column(payload,user_id):
    from api import store_hours as sh
    if type(payload.get('revision')) is not int:
        raise PortalError('Reload the spreadsheet before changing columns.')
    action = payload.get('action')
    if action not in ('add','rename','delete','format'):
        raise PortalError('Choose a valid column action.')
    with sh.connect() as conn:
        with conn.transaction():
            config=settings(conn,True)
            if config['revision']!=payload['revision']:
                raise PortalError('Someone changed the columns. Reload before trying again.',409)
            columns=config['columns']
            if action=='add':
                if len([c for c in columns if not c.get('deleted')])>=40 or len(columns)>=200:
                    raise PortalError('This sheet supports 40 active custom columns and 200 archived definitions.')
                column={'id':'custom_'+uuid4().hex,'name':'','format':'text'}
                columns.append(column)
            else:
                column=next((c for c in columns if c['id']==payload.get('id') and not c.get('deleted')),None)
                if column is None:
                    raise PortalError('Default columns are protected. Only active custom columns can be changed.',403)
            if action in ('add','rename'):
                name=payload.get('name')
                if not isinstance(name,str) or not name.strip() or len(name)>60 or re.search(r'[\x00-\x1f]',name):
                    raise PortalError('Enter a column name of 1–60 characters.')
                name=name.strip()
                if name.casefold() in {label.casefold() for _,label in sh.COLUMNS} | {c['name'].casefold() for c in columns if c is not column and not c.get('deleted')}:
                    raise PortalError('Choose a unique column name.')
                column['name']=name
            if action in ('add','rename','format'):
                value=payload.get('format',column.get('format','text'))
                if not isinstance(value,str) or value not in NUMBER_FORMATS:
                    raise PortalError('Choose a valid column format.')
                column['format']=value
            if action=='delete':
                column['deleted']=True
            conn.execute('update public.store_hours_sheet_settings set columns=%s,revision=revision+1,updated_by=%s,updated_at=now() where id=true',
                         (Jsonb(columns),user_id))
            return dict(columns=columns,revision=config['revision']+1)


def filter_rows(rows, columns, filters, sort):
    keys={c[0] for c in columns}
    if not isinstance(filters,dict) or set(filters)-keys or len(filters)>54:
        raise PortalError('Choose valid column filters.')
    for key,rule in filters.items():
        if not isinstance(rule,dict) or set(rule)-{'contains','values'}:
            raise PortalError('Choose valid column filters.')
        needle=rule.get('contains','')
        values=rule.get('values')
        if not isinstance(needle,str) or len(needle)>1000 or (values is not None and (not isinstance(values,list) or len(values)>500 or any(not isinstance(v,str) or len(v)>1000 for v in values))):
            raise PortalError('Choose valid column filters.')
        rows=[r for r in rows if needle.casefold() in str(r.get(key) if r.get(key) is not None else '').casefold() and
              (values is None or str(r.get(key) if r.get(key) is not None else '') in values)]
    if sort:
        if not isinstance(sort,dict) or set(sort)-{'key','direction'} or sort.get('key') not in keys or sort.get('direction') not in ('asc','desc'):
            raise PortalError('Choose a valid column sort.')
        key=sort['key']
        def value(row):
            raw=row.get(key)
            try:
                num=Decimal(str(raw).replace('$','').replace(',',''))
                if num.is_finite():
                    return (0,num)
            except InvalidOperation:
                pass
            return (1,str(raw or '').casefold())
        filled=[r for r in rows if r.get(key) not in (None,'')]
        blank=[r for r in rows if r.get(key) in (None,'')]
        rows=sorted(filled,key=value,reverse=sort['direction']=='desc')+blank
    return rows


def report():
    from api import store_hours as sh
    data=sh.report_data(*sh.report_range())
    with sh.connect() as conn:
        config=settings(conn)
    custom=[c for c in config['columns'] if not c.get('deleted')]
    data['sheet']=config
    data['columns']=sh.COLUMNS+[(c['id'],c['name']) for c in custom]
    data['column_formats']={c['id']:c['format'] for c in custom}
    for row in data['rows']:
        for col in custom:
            row[col['id']]=(row.get('custom_cells') or {}).get(col['id'])
    try:
        filters=json.loads(request.args.get('filters','{}'))
        sort=json.loads(request.args.get('sort','{}'))
    except (ValueError,TypeError):
        raise PortalError('Choose valid spreadsheet filters.') from None
    data['rows']=filter_rows(data['rows'],data['columns'],filters,sort)
    search=request.args.get('search','').strip().casefold()
    if search:
        data['rows']=[r for r in data['rows'] if any(search in str(r.get(k) or '').casefold() for k,_ in data['columns'])]
    return data


def format_excel_cell(cell, value, fmt):
    from copy import copy
    from openpyxl.styles import PatternFill, Alignment, Side
    font=copy(cell.font)
    for key,attr in [('bold','bold'),('italic','italic'),('font_size','size'),('font_family','name')]:
        if key in fmt:
            setattr(font,attr,fmt[key])
    if 'underline' in fmt:
        font.underline='single' if fmt['underline'] else None
    if 'color' in fmt:
        font.color=fmt['color'][1:]
    cell.font=font
    if 'borders' in fmt:
        border=copy(cell.border)
        for side,value_style in fmt['borders'].items():
            setattr(border,side,Side(style=None if value_style['style']=='none' else value_style['style'],color=value_style['color'][1:]))
        cell.border=border
    if 'background' in fmt:
        cell.fill=PatternFill('solid',fgColor=fmt['background'][1:])
    cell.alignment=Alignment(horizontal=fmt.get('align'),wrap_text=fmt.get('wrap',False))
    kind=fmt.get('number_format','auto')
    if kind in ('number','currency','percent') and value not in (None,''):
        try:
            amount=Decimal(str(value).replace('$','').replace(',','').removesuffix('%'))
            if str(value).endswith('%'):
                amount/=100
            if amount.is_finite() and abs(amount)<10**15:
                cell.value=float(amount)
                cell.number_format={'number':'0.00','currency':'$#,##0.00;[Red]-$#,##0.00','percent':'0.00%'}[kind]
        except InvalidOperation:
            pass
    elif kind in ('date','time') and value:
        try:
            text=str(value)
            parsed=datetime.fromisoformat(text) if 'T' in text else datetime.strptime(text,'%Y-%m-%d' if kind=='date' else '%H:%M:%S')
            cell.value=parsed.date() if kind=='date' else parsed.time()
            cell.number_format='mmm d, yyyy' if kind=='date' else 'h:mm:ss AM/PM'
        except ValueError:
            pass
    elif kind=='text' and value is not None:
        cell.value=str(value)
        cell.data_type='s'
        cell.number_format='@'


def live_revision():
    from api import store_hours as sh
    with sh.connect() as conn:
        return str(conn.execute('select revision from public.store_hours_live_revision where id=true').fetchone()['revision'])


def presence_input(payload):
    try:
        client_id=str(UUID(payload.get('client_id','')))
    except (ValueError,TypeError,AttributeError):
        raise PortalError('Choose a valid spreadsheet session.') from None
    sequence=payload.get('sequence')
    if type(sequence) is not int or not 0 <= sequence <= 9007199254740991 or type(payload.get('active')) is not bool or type(payload.get('editing')) is not bool:
        raise PortalError('Invalid spreadsheet presence.')
    selection=payload.get('selection')
    if selection is not None:
        keys={'dealer','store_id','source_date','employee_key','column'}
        if not isinstance(selection,dict) or set(selection)!=keys or any(not isinstance(v,str) for v in selection.values()):
            raise PortalError('Choose a valid spreadsheet cell.')
        from api.store_hours import COLUMNS
        if any(not 0<len(selection[k])<=160 for k in ('dealer','store_id')) or len(selection['employee_key'])>500 or selection['column'] not in {k for k,_ in COLUMNS} and not re.fullmatch(r'custom_[a-zA-Z0-9_]{1,64}',selection['column']):
            raise PortalError('Choose a valid spreadsheet cell.')
        try:
            if date.fromisoformat(selection['source_date']).isoformat()!=selection['source_date']:
                raise ValueError
        except ValueError:
            raise PortalError('Choose a valid spreadsheet date.') from None
    active=payload['active']
    return client_id,sequence,active,selection if active else None,bool(active and selection and payload['editing'])


def update_presence(payload,user,session_hash):
    from api import store_hours as sh
    client_id,sequence,active,selection,editing=presence_input(payload)
    with sh.connect() as conn:
        with conn.transaction():
            conn.execute("delete from public.store_hours_presence where last_seen<now()-interval '1 day'")
            conn.execute('''insert into public.store_hours_presence(user_id,client_id,session_hash,sequence,active,selection,editing)
                values(%s,%s,%s,%s,%s,%s,%s)
                on conflict(user_id,client_id) do update set session_hash=excluded.session_hash,
                sequence=excluded.sequence,active=excluded.active,selection=excluded.selection,editing=excluded.editing,last_seen=clock_timestamp()
                where excluded.sequence>store_hours_presence.sequence''',
                (user['id'],client_id,session_hash,sequence,active,Jsonb(selection) if selection else None,editing))
            peers=conn.execute('''select p.user_id::text,p.client_id::text,u.display_name as name,p.selection,p.editing
                from public.store_hours_presence p join public.portal_users u on u.id=p.user_id
                join public.portal_sessions s on s.token_hash=p.session_hash and s.user_id=p.user_id
                where p.active and p.last_seen>clock_timestamp()-interval '15 seconds'
                and u.active and not u.rest_mode and s.expires_at>now() and s.session_version=u.session_version
                order by p.user_id,p.client_id''').fetchall()
    return peers


def register(app):
    @app.post('/api/internal/store-hours/sheet/presence')
    @require_user()
    def sheet_presence():
        peers=update_presence(body(),g.portal_user,g.session_hash)
        return jsonify(peers=peers,revision=live_revision())

    @app.get('/api/internal/store-hours/sheet/updates')
    @require_user()
    def sheet_updates():
        return jsonify(revision=live_revision())

    @app.get('/api/internal/store-hours/sheet')
    @require_user()
    def sheet_report():
        # Read the token first: a write during report loading is picked up next poll.
        revision = live_revision()
        result = report()
        result['live_revision'] = revision
        return jsonify(result)

    @app.post('/api/internal/store-hours/sheet/columns')
    @require_user()
    def sheet_columns():
        return jsonify(change_column(body(),g.portal_user['id']))

    @app.get('/api/internal/store-hours/sheet/export')
    @require_user()
    def sheet_export():
        from api.store_hours import excel_report
        data=report()
        return send_file(excel_report(data),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,download_name=f"opening-closing-sheet-{data['start']}-{data['end']}.xlsx")
