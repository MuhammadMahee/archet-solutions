from uuid import uuid4
import pytest
from api import store_hours_sheet as sheet
from api.portal import PortalError
from test_portal import client, store, login, write


def payload():
    return dict(client_id=str(uuid4()),sequence=1,active=True,editing=True,
                selection=dict(dealer='Connect',store_id='1',source_date='2026-10-20',employee_key='person:jane',column='employee'))


@pytest.mark.parametrize('change',[
    {'client_id':'bad'}, {'client_id':5}, {'sequence':True}, {'sequence':-1}, {'sequence':2**54},
    {'active':1}, {'editing':'true'}, {'selection':[]}, {'selection':{'row':1}},
])
def test_invalid_presence(change):
    with pytest.raises(PortalError):sheet.presence_input({**payload(),**change})


@pytest.mark.parametrize('change',[
    {'column':'<script>'},{'source_date':'2026-02-31'},{'employee_key':'x'*501},
    {'store_id':''},{'dealer':4},{'draft_text':'private unfinished edit'},
])
def test_invalid_cell_metadata(change):
    data=payload();data['selection'].update(change)
    with pytest.raises(PortalError):sheet.presence_input(data)


def test_presence_only_tracks_identity_and_editing_flag():
    data=payload()
    assert sheet.presence_input(data)[3:]==(data['selection'],True)
    data['active']=False
    assert sheet.presence_input(data)[2:]==(False,None,False)
    data.update(active=True,selection=None)
    assert sheet.presence_input(data)[2:]==(True,None,False)


def test_presence_authentication_csrf_and_server_identity(client,store,monkeypatch):
    path='store-hours/sheet/presence'
    assert write(client,path,payload()).status_code==401
    login(client,'Member')
    assert client.post('/api/internal/'+path,json=payload()).status_code==403
    seen=[]
    def update(data,user,session):
        seen.append((user['id'],session))
        return []
    monkeypatch.setattr(sheet,'update_presence',update)
    monkeypatch.setattr(sheet,'live_revision',lambda:'12')
    result=write(client,path,{**payload(),'user_id':store.owner['id'],'name':'Spoofed'})
    assert result.json=={'peers':[],'revision':'12'}
    assert seen[0][0]==store.member['id'] and seen[0][1]
    assert result.headers['Cache-Control']=='no-store'
