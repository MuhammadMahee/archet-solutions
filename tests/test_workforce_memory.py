"""Durable memory, consent controls and cross-conversation audience boundaries."""
import json
from uuid import uuid4
import pytest
from api import workforce_ai as ai
from api.workforce_store import Store
from test_portal import store, client, login, write
from test_workforce import local_workforce, queue, chat, send


def plan(notes=None, action='remember'):
    return dict(action=action,message='Proposed memory',start='',end='',dealer='',market='',agent_ids=[],url='',memories=notes or [])


def task_for(client,queue,cid,text):
    return queue.claim('memory-test',send(client,cid,content=text).json['task_id'])


def test_automatic_memory_survives_clear_exit_and_reopen(client,queue,store):
    login(client);cid=chat(client);text='I prefer concise updates with bullet points.'
    class Model:
        def local_model(self,*args):pass
        def chat(self,model,system,content,schema):
            assert 'persistent memory' in system
            return json.dumps(plan([dict(topic='Update style',evidence=text)]))
    task=task_for(client,queue,cid,text);ai.execute(queue,task,Model())
    assert queue.snapshot(cid,store.owner['id'])['tasks'][0]['status']=='completed'
    assert "I've saved 1 memory note" in queue.snapshot(cid,store.owner['id'])['messages'][-1]['content']
    queue.group_action(cid,store.owner,'clear',{})
    queue.group_action(cid,store.owner,'exit',{})
    reopened=Store(queue.path);new=chat(client);follow=task_for(client,reopened,new,'How do I like my updates?')
    context=ai.manager_context(reopened,follow,store.owner)
    assert context['memory']['notes'][0]['content']==text
    assert context['conversation']['recent_messages']==[]


def test_personal_audience_and_company_permissions(client,queue,store):
    login(client);cid=chat(client);task=task_for(client,queue,cid,'Our internal plan is the autumn launch.')
    assert queue.remember_request(task,store.owner,[dict(topic='Launch',evidence=task['content'])],0)==1
    shared=chat(client,[store.member['id']]);request=task_for(client,queue,shared,'What is the plan?')
    assert not queue.memory_context(request,store.owner)['notes']
    login(client,'OtherAdmin')
    assert client.get('/api/internal/workforce/memory').json['memories']==[]
    login(client,'Member')
    data=dict(topic='Company launch',content='The launch is in autumn.',scope='company')
    assert write(client,'workforce/memory',data).status_code==403
    login(client);result=write(client,'workforce/memory',data);assert result.status_code==201
    assert queue.memory_context(request,store.owner)['notes'][0]['scope']=='company'
    login(client,'Member')
    assert len(client.get('/api/internal/workforce/memory').json['memories'])==1
    assert write(client,'workforce/memory/'+result.json['id'],data,method='PATCH').status_code==403
    assert write(client,'workforce/memory/'+result.json['id'],{},method='DELETE').status_code==404


def test_exact_evidence_dedup_and_stale_request(client,queue,store):
    login(client);cid=chat(client);task=task_for(client,queue,cid,'My preferred market is Dallas.')
    assert queue.remember_request(task,store.owner,[dict(topic='Market',evidence='My preferred market is Reno.')],0)==0
    note=dict(topic='Market',evidence=task['content'])
    assert queue.remember_request(task,store.owner,[note],0)==1
    assert queue.remember_request(task,store.owner,[note],0)==0
    second=task_for(client,queue,cid,'My preferred market is Reno.')
    assert queue.remember_request(second,store.owner,[dict(topic='Market',evidence=second['content'])],0)==1
    assert queue.remember_request(task,store.owner,[note],0)==0
    memories=queue.memory_list(store.owner)['memories'];assert len(memories)==1
    assert memories[0]['content']=='My preferred market is Reno.'
    queue.forget_memory(store.owner,memories[0]['id'])
    assert queue.remember_request(second,store.owner,[dict(topic='Market',evidence=second['content'])],0)==0
    assert queue.memory_list(store.owner)['memories']==[]


def test_disabled_secrets_and_disappearing_messages(client,queue,store):
    login(client);cid=chat(client)
    for text in ['My API_KEY is not-a-real-key','My password is not-a-real-password','My SSN is 000-00-0000']:
        task=task_for(client,queue,cid,text)
        assert queue.remember_request(task,store.owner,[dict(topic='Bad note',evidence=text)],0)==0
    queue.memory_toggle(store.owner,False)
    task=task_for(client,queue,cid,'My preferred market is Dallas.')
    assert queue.remember_request(task,store.owner,[dict(topic='Market',evidence=task['content'])],1)==0
    queue.memory_toggle(store.owner,True)
    queue.update_group(cid,store.owner,{'disappearing':86400})
    task=task_for(client,queue,cid,'My preferred market is Dallas.')
    assert queue.remember_request(task,store.owner,[dict(topic='Market',evidence=task['content'])],2)==0
    assert not queue.memory_list(store.owner)['memories']


def test_memory_api_edit_forget_auth_and_context(client,queue,store):
    assert client.get('/api/internal/workforce/memory').status_code==401
    login(client)
    data=dict(topic='Update style',content='Use short updates.',scope='personal')
    assert client.post('/api/internal/workforce/memory',json=data).status_code==403
    mid=write(client,'workforce/memory',data).json['id']
    assert write(client,'workforce/memory/'+mid,{**data,'content':'Include dates.'},method='PATCH').status_code==200
    cid=chat(client);task=task_for(client,queue,cid,'What do you remember?')
    assert queue.memory_context(task,store.owner)['notes'][0]['content']=='Include dates.'
    login(client,'OtherAdmin')
    assert write(client,'workforce/memory/'+mid,data,method='PATCH').status_code==404
    login(client)
    assert write(client,'workforce/memory/'+mid,{},method='DELETE').status_code==200
    assert queue.memory_context(task,store.owner)['notes']==[]
    assert write(client,'workforce/memory/settings',{'enabled':'false'},method='PATCH').status_code==400
    assert write(client,'workforce/memory/settings',{'enabled':False},method='PATCH').status_code==200
    assert not client.get('/api/internal/workforce/memory').json['enabled']


@pytest.mark.parametrize('notes',[{},[{'topic':'x','evidence':'a'}],[{'topic':'x','evidence':'12345','extra':'x'}],[{'topic':4,'evidence':'12345'}]])
def test_invalid_model_memory_rejected(notes):
    value=plan();value['memories']=notes
    with pytest.raises(ai.AIError):ai.parse_plan(json.dumps(value))

@pytest.mark.parametrize('change',['forget','new_member'])
def test_pending_reply_rechecks_memory_and_audience(client,queue,store,change):
    login(client);cid=chat(client)
    mid=queue.save_memory(store.owner,dict(topic='Private context',content='The internal codename is River.',scope='personal'))
    task=task_for(client,queue,cid,'What is the codename?')
    class Model:
        def local_model(self,*args):pass
        def chat(self,model,system,content,schema):
            assert json.loads(content)['memory']['notes']
            if change=='forget':queue.forget_memory(store.owner,mid)
            else:
                with queue.connection(True) as conn:conn.execute('INSERT INTO members VALUES(?,?)',(cid,store.member['id']))
            return json.dumps(plan(action='reply'))
    ai.execute(queue,task,Model())
    state=queue.snapshot(cid,store.owner['id'])
    assert state['tasks'][0]['status']=='failed'
    assert 'Memory or group access changed' in state['tasks'][0]['error']
    assert len(state['messages'])==1
