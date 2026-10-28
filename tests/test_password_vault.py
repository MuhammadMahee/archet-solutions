from uuid import uuid4
import pytest
from api import password_vault as vault
from test_portal import client,store,login,write


def test_authenticated_encryption_and_account_binding(monkeypatch):
    monkeypatch.setenv('PORTAL_PASSWORD_KEY','x'*48)
    uid=str(uuid4());token=vault.encrypt(uid,'SecretTest123')
    assert 'SecretTest123' not in token
    assert vault.decrypt(uid,token)=='SecretTest123'
    assert vault.decrypt(str(uuid4()),token) is None
    assert vault.decrypt(uid,token[:-4]+'AAAA') is None
    monkeypatch.setenv('PORTAL_PASSWORD_KEY','y'*48)
    assert vault.decrypt(uid,token) is None


@pytest.mark.parametrize('name',['Mahee','Mughees','Sharjeel'])
def test_only_named_viewers_receive_explicit_password_reveals(client,store,name):
    if name!='Mahee':store.add_user(name,'admin')
    login(client,name)
    assert client.get('/api/internal/users').json['can_view_passwords'] is True
    uid=store.member['id'];path='users/'+uid+'/password/reveal'
    assert write(client,path,{}).json=={'password':None,'available':False}
    assert write(client,'users/'+uid,{'password':'NewSecret123'},'PATCH').status_code==200
    result=write(client,path,{})
    assert result.json=={'password':'NewSecret123','available':True}
    assert result.headers['Cache-Control']=='no-store'
    assert 'NewSecret123' not in client.get('/api/internal/users').get_data(as_text=True)
    store.auth('admin/users/'+uid,'PUT',{'password':'ExternalReset123'})
    assert write(client,path,{}).json['available'] is False


def test_non_viewers_cannot_reveal_even_with_forged_identity(client,store):
    path='users/'+store.member['id']+'/password/reveal'
    assert write(client,path,{}).status_code==401
    login(client,'OtherAdmin')
    assert client.get('/api/internal/users').json['can_view_passwords'] is False
    assert write(client,path,{'username':'Mahee','role':'admin'}).status_code==403
    login(client,'Member')
    assert write(client,path,{}).status_code==403


def test_member_can_change_own_password_and_viewer_can_reveal_new_value(client,store):
    login(client,'Member')
    assert write(client,'password',{'current_password':'TestPass123','new_password':'ChangedMember123'}).status_code==200
    assert client.get('/api/internal/me').status_code==401
    login(client)
    assert write(client,'users/'+store.member['id']+'/password/reveal',{}).json['password']=='ChangedMember123'


def test_reveal_requires_origin_and_honors_revocation(client,store):
    login(client)
    path='users/'+store.member['id']+'/password/reveal'
    assert client.post('/api/internal/'+path,json={}).status_code==403
    store.db('portal_users','PATCH',{'session_version':str(uuid4())},id='eq.'+store.owner['id'])
    assert write(client,path,{}).status_code==401


def test_other_admin_cannot_take_over_password_viewer_account(client,store):
    viewer=store.add_user('Sharjeel','admin');login(client,'OtherAdmin')
    assert write(client,'users/'+viewer['id'],{'password':'Takeover123'},'PATCH').status_code==403
    assert write(client,'users/'+viewer['id'],{'role':'member'},'PATCH').status_code==403
