"""Optional database checks. All schema and fixture writes are rolled back."""
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
import psycopg
from api import index, store_hours as sh, store_hours_sheet as sheet
from api.sheet_types import CHECK_FIELDS
from api.portal import PortalError


def main():
    load_dotenv(ROOT/'.env')
    with sh.connect() as conn:
        with conn.transaction():
            exists=conn.execute("select to_regclass('public.compliance_versions') as name").fetchone()['name']
            if not exists:
                conn.execute((ROOT/'supabase/migrations/028_compliance_spreadsheet.sql').read_text(encoding='utf-8'),prepare=False)
            user=conn.execute('select id,session_version from public.portal_users where active limit 1').fetchone()
            uid=str(user['id']);day=sh.today();name='TEST ROLLBACK '+uuid4().hex
            directory=sh.roster_with_schedules(conn);store=directory[0]
            identity=dict(dealer=store['dealer'],store_id=store['store_id'],date=day.isoformat(),employee=name)
            from urllib.parse import urlencode
            query=urlencode(dict(start=day.isoformat(),end=day.isoformat(),store=store['dealer']+':'+store['store_id']))
            with patch.object(sh,'connect',lambda:nullcontext(conn)):
                with index.app.test_request_context('/api/internal/compliance/sheet?'+query):
                    key=sh.add_manual_employee(identity,uid)
                    data=sheet.report();row=next(r for r in data['rows'] if r['employee_key']==key)
                    assert all(row[k] is None for k in CHECK_FIELDS)
                    old_revision=sheet.live_revision()
                    row['cell_overrides']={'shirt':'No','name_tag':'Yes','store_cleaning':'#N/A'}
                    saved=sh.save_review(row,uid,True)['row']
                    assert saved['shirt']=='No' and saved['revision']==1
                    assert sheet.live_revision()!=old_revision
                    assert sheet.report()['rows'][-1] is not None
                    with conn.transaction():
                        try:sh.save_review(row,uid,True)
                        except PortalError as error:assert error.status==409
                        else:raise AssertionError('Expected stale edit conflict')
                    col=sheet.change_column({'action':'add','name':'Audit notes','format':'text','revision':0},uid)['columns'][0]['id']
                    saved['custom_cells']={col:'Verified'}
                    saved=sh.save_review(saved,uid,True)['row']
                    assert saved['custom_cells'][col]=='Verified'
                    sh.set_rows_removed({'action':'remove','rows':[saved]},uid)
                    removed=next(r for r in sheet.report()['removed_rows'] if r['employee_key']==key)
                    sh.set_rows_removed({'action':'restore','rows':[removed]},uid)
                    assert next(r for r in sheet.report()['rows'] if r['employee_key']==key)['shirt']=='No'
                    assert any(v['after_data'] and v['after_data'].get('cell_overrides',{}).get('shirt')=='No' for v in sh.version_history(day,day)['versions'])
                    try:
                        with conn.transaction():conn.execute('delete from public.compliance_versions')
                    except psycopg.errors.InsufficientPrivilege:pass
                    else:raise AssertionError('History was deletable')
                    token=uuid4().hex
                    conn.execute("insert into public.portal_sessions(token_hash,user_id,session_version,expires_at) values(%s,%s,%s,now()+interval '1 hour')",(token,uid,user['session_version']))
                    selection={'dealer':store['dealer'],'store_id':store['store_id'],'source_date':day.isoformat(),'employee_key':key,'column':'shirt'}
                    peers=sheet.update_presence(dict(client_id=str(uuid4()),sequence=1,active=True,editing=True,selection=selection),{'id':uid},token)
                    assert any(p['selection']==selection for p in peers)
                with index.app.test_request_context('/api/internal/store-hours/sheet?'+query):
                    assert not any(r['employee_key']==key for r in sheet.report()['rows'])
                    key=sh.add_manual_employee(identity,uid)
                    row=next(r for r in sheet.report()['rows'] if r['employee_key']==key)
                    row['camera_in']=row['camera_out']='Camera Offline'
                    saved=sh.save_review(row,uid,True)['row']
                    assert saved['camera_in']==saved['camera_out']=='Camera Offline'
                    assert saved['chargeback'] is None
                    sh.set_rows_removed({'action':'remove','rows':[saved]},uid)
                    removed=next(r for r in sheet.report()['removed_rows'] if r['employee_key']==key)
                    sh.set_rows_removed({'action':'restore','rows':[removed]},uid)
                    row=next(r for r in sheet.report()['rows'] if r['employee_key']==key)
                    row['camera_in']='10:01:00';row['camera_out']=None
                    saved=sh.save_review(row,uid,True)['row']
                    assert saved['camera_in']=='10:01:00' and saved['camera_out'] is None
                    assert 'camera_in' not in saved['cell_overrides']
            print('Database integration passed: isolation, saves, conflicts, columns, restore, immutable history, presence, offline cameras. Rolling back.')
            raise psycopg.Rollback()


if __name__=='__main__':main()
