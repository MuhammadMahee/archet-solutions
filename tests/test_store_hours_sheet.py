from contextlib import nullcontext
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from api import index, store_hours as sh, store_hours_sheet as sheet
from api.portal import PortalError
from test_portal import store, client, login, write
from test_store_hours import sample_rows


@pytest.mark.parametrize('value', [[], {'position':'fixed'},{'bold':1},{'color':'red'}, {'background':'url(x)'},
                                  {'align':'justify'},{'font_size':100},{'number_format':'formula'},{'wrap':'yes'}])
def test_invalid_formats(value):
    with pytest.raises(PortalError): sheet.validate_format(value)


def test_formats_and_archived_cells_validation():
    config={'columns':[{'id':'custom_1'},{'id':'custom_2','deleted':True}]}
    prior={'custom_cells':{'custom_2':'retained'},'cell_formats':{'custom_2':{'bold':True}}}
    cells,formats=sheet.validate_row_extras({'custom_cells':{'custom_1':'Note'},'cell_formats':{'employee':{'bold':True,'background':'#ffffff'}}},prior,config,{'employee'})
    assert cells=={'custom_1':'Note','custom_2':'retained'}
    assert formats['custom_2']=={'bold':True}
    for payload in [{'custom_cells':{'custom_2':'changed'}},{'custom_cells':{'unknown':'x'}},
                    {'custom_cells':{'custom_1':'x'*1001}},{'cell_formats':{'employee':[]}}]:
        with pytest.raises(PortalError): sheet.validate_row_extras(payload,prior,config,{'employee'})


def fake_settings(monkeypatch):
    config={'columns':[],'revision':0}
    class DB:
        def transaction(self): return nullcontext()
        def execute(self,sql,args=None):
            if sql.startswith('update public.store_hours_sheet_settings'):
                config['columns']=deepcopy(args[0].obj)
                config['revision']+=1
            return SimpleNamespace(fetchone=lambda:deepcopy(config))
    monkeypatch.setattr(sh,'connect',lambda:nullcontext(DB()))
    return config


def test_custom_columns_shared_revision_soft_delete_and_default_protection(monkeypatch):
    config=fake_settings(monkeypatch)
    created=sheet.change_column({'action':'add','name':'Notes','format':'text','revision':0},'user')
    column=created['columns'][0]['id']
    with pytest.raises(PortalError,match='Someone changed'):
        sheet.change_column({'action':'rename','id':column,'name':'Review','revision':0},'user')
    for field,_ in sh.COLUMNS:
        with pytest.raises(PortalError,match='Default columns') as exc:
            sheet.change_column({'action':'delete','id':field,'revision':1},'user')
        assert exc.value.status==403
    changed=sheet.change_column({'action':'rename','id':column,'name':'Amount','format':'currency','revision':1},'user')
    assert changed['columns'][0]['format']=='currency'
    deleted=sheet.change_column({'action':'delete','id':column,'revision':2},'user')
    assert deleted['columns'][0]['deleted'] and deleted['columns'][0]['name']=='Amount'
    assert config['revision']==3
    with pytest.raises(PortalError):
        sheet.change_column({'action':'add','name':'Employee','revision':3},'user')


def test_filters_and_numeric_sort_apply_to_all_rows():
    columns=[('employee','Employee'),('custom_1','Score')]
    rows=[{'employee':'Example','custom_1':str(n)} for n in range(120)]
    rows.append({'employee':'Other','custom_1':None})
    result=sheet.filter_rows(rows,columns,{'employee':{'contains':'EXAMPLE'}},{'key':'custom_1','direction':'desc'})
    assert len(result)==120 and result[0]['custom_1']=='119'
    selected=sheet.filter_rows(rows,columns,{'custom_1':{'values':['2','11']}},{})
    assert [r['custom_1'] for r in selected]==['2','11']
    assert sheet.filter_rows(rows,columns,{'custom_1':{'values':[]}},{})==[]
    for invalid in [[],{'unknown':{}},{'employee':{'values':[4]}},{'employee':{'contains':False}}]:
        with pytest.raises(PortalError): sheet.filter_rows(rows,columns,invalid,{})


def test_sheet_routes_authentication_and_same_origin(client,monkeypatch):
    assert client.get('/spreadsheet').status_code==200
    assert client.get('/api/internal/store-hours/sheet').status_code==401
    assert client.get('/api/internal/store-hours/sheet/export').status_code==401
    login(client,'Member')
    monkeypatch.setattr(sheet,'report',lambda:{'rows':[]})
    assert client.get('/api/internal/store-hours/sheet').status_code==200
    assert client.post('/api/internal/store-hours/sheet/columns',json={}).status_code==403
    monkeypatch.setattr(sheet,'change_column',lambda payload,user_id:{'revision':1,'columns':[]})
    assert write(client,'store-hours/sheet/columns',{}).json['revision']==1


def test_custom_cells_excel_values_and_formats_are_safe():
    rows=sample_rows()
    for row in rows: row.update(custom_1='=HYPERLINK("bad")',custom_2='12.50')
    rows[0]['cell_formats']={'custom_1':{'bold':True,'italic':True,'background':'#ffeeaa','color':'#123456','wrap':True,'align':'center'},'custom_2':{'number_format':'currency'}}
    result=sh.excel_report(dict(rows=rows,columns=sh.COLUMNS+[('custom_1','Notes'),('custom_2','Amount')],column_formats={},start='2026-10-20',end='2026-10-20',updated_at=None,coverage={'complete':0,'expected':1}))
    book=load_workbook(result)
    text=book.active['O3'];amount=book.active['P3']
    assert text.data_type=='s' and text.value.startswith('=HYPERLINK')
    assert text.font.bold and text.font.italic and text.alignment.wrap_text
    assert text.fill.fgColor.rgb=='00ffeeaa'
    assert amount.value==12.5 and amount.number_format=='$#,##0.00;[Red]-$#,##0.00'
    assert book.active.auto_filter.ref=='A2:P6'
