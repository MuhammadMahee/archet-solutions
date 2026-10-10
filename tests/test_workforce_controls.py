"""Chat controls: user scope, authorization, content lifecycle and forwarding."""
import json
import time
from uuid import uuid4
import pytest
from api import workforce_ai as ai
from test_portal import store, client, login, write
from test_workforce import local_workforce, queue, chat, send, Model, report
from test_workforce_images import sample


def post(client,path,data=None):
    return write(client,'workforce/'+path,data or {})


def patch(client,path,data):
    return write(client,'workforce/'+path,data,method='PATCH')


def test_personal_preferences_clear_and_new_messages(client,queue,store):
    login(client);cid=chat(client,[store.member['id']])
    first=send(client,cid,content='Private history',invoke_agents=False).json
    assert patch(client,f'conversations/{cid}/preferences',dict(archived=True,pinned=True,favorite=True,theme='plum',list_name='Operations',muted_until=time.time()+3600)).status_code==200
    state=client.get('/api/internal/workforce/conversations/'+cid).json
    assert state['preferences']['archived']==1 and state['preferences']['theme']=='plum'
    assert post(client,f'conversations/{cid}/actions/clear').status_code==200
    assert queue.snapshot(cid,store.owner['id'])['messages']==[]
    assert len(queue.snapshot(cid,store.member['id'])['messages'])==1
    assert queue.chat_controls(cid,store.member)['preferences']['archived']==0
    send(client,cid,content='After clearing',invoke_agents=False)
    assert len(queue.snapshot(cid,store.owner['id'])['messages'])==1
    for invalid in ({'theme':'evil'},{'read_seq':'1'},{'archived':'true'},{'cleared_seq':999},{'list_name':'x'*41}):
        assert patch(client,f'conversations/{cid}/preferences',invalid).status_code==400


def test_reply_reactions_stars_and_membership(client,queue,store):
    login(client);cid=chat(client,[store.member['id']]);seq=send(client,cid,content='Question',invoke_agents=False).json['message_seq']
    assert send(client,cid,content='Reply',reply_seq=seq,invoke_agents=False).status_code==201
    reply=queue.snapshot(cid,store.owner['id'])['messages'][-1]
    assert reply['reply']['content']=='Question'
    assert post(client,f'messages/{seq}/react',{'emoji':'👍'}).status_code==200
    assert post(client,f'messages/{seq}/star').status_code==200
    assert post(client,f'messages/{seq}/pin').status_code==200
    assert queue.snapshot(cid,store.owner['id'])['messages'][0]['starred']
    assert not queue.snapshot(cid,store.member['id'])['messages'][0]['starred']
    assert post(client,f'messages/{seq}/react',{'emoji':'👍'}).status_code==200
    assert queue.snapshot(cid,store.owner['id'])['messages'][0]['reactions']==[]
    other=chat(client)
    assert send(client,other,content='Bad reply',reply_seq=seq).status_code==400
    login(client,'Member')
    assert post(client,f'messages/{seq}/delete').status_code==403
    assert post(client,f'messages/{seq}/pin').status_code==403
    assert patch(client,f'conversations/{cid}/profile',{'title':'Unauthorized'}).status_code==403
    assert post(client,f'messages/{seq}/hide').status_code==200
    assert len(queue.snapshot(cid,store.member['id'])['messages'])==1
    login(client,'OtherAdmin')
    assert post(client,f'messages/{seq}/star').status_code==404
    assert client.get('/api/internal/workforce/conversations/'+cid+'/library?kind=starred').status_code==404


def test_delete_and_disappearing_deny_old_media_and_ai_context(client,queue,store):
    login(client);cid=chat(client)
    sent=send(client,cid,content='Delete me',images=[{'data':sample()}],invoke_agents=False).json
    image=queue.snapshot(cid,store.owner['id'])['messages'][0]['images'][0]['id']
    assert post(client,f"messages/{sent['message_seq']}/delete").status_code==200
    assert client.get('/api/internal/workforce/images/'+image).status_code==404
    assert patch(client,f'conversations/{cid}/profile',{'disappearing':86400}).status_code==200
    expiring=send(client,cid,content='Expires',images=[{'data':sample()}],invoke_agents=False).json
    image=queue.snapshot(cid,store.owner['id'])['messages'][0]['images'][0]['id']
    revision=queue.chat_controls(cid,store.owner)['revision']
    with queue.connection(True) as conn: conn.execute('UPDATE message_details SET expires_at=1 WHERE message_seq=?',(expiring['message_seq'],))
    assert queue.chat_controls(cid,store.owner)['revision']!=revision
    assert client.get('/api/internal/workforce/images/'+image).status_code==404
    follow=send(client,cid,content='What is visible?').json
    task=queue.claim('worker',follow['task_id'])
    assert queue.assignment_context(task)['recent_messages']==[]
    assert queue.task_images(task)==[]


def test_group_invites_members_exit_and_private_reply(client,queue,store):
    login(client);cid=chat(client,[store.member['id']])
    assert patch(client,f'conversations/{cid}/profile',{'title':'Updated','description':'Daily coordination'}).status_code==200
    result=post(client,f'conversations/{cid}/actions/invite').json
    token=result['token']
    login(client,'OtherAdmin')
    assert post(client,'invites/join',{'token':token}).status_code==200
    assert client.get('/api/internal/workforce/conversations/'+cid).status_code==200
    login(client)
    assert post(client,f'conversations/{cid}/members',{'action':'remove','user_id':store.admin['id']}).status_code==200
    login(client,'OtherAdmin')
    assert client.get('/api/internal/workforce/conversations/'+cid).status_code==404
    login(client)
    assert post(client,f'conversations/{cid}/actions/revoke-invite').status_code==200
    login(client,'OtherAdmin')
    assert post(client,'invites/join',{'token':token}).status_code==404
    login(client,'Member')
    private=post(client,'direct',{'user_id':store.owner['id']})
    assert private.status_code==200
    assert post(client,'direct',{'user_id':store.admin['id']}).status_code==403
    login(client)
    assert post(client,f'conversations/{cid}/actions/exit').status_code==200
    assert client.get('/api/internal/workforce/conversations/'+cid).status_code==404
    assert queue.chat_controls(cid,store.member)['can_manage']


def test_forward_image_report_and_export_are_scoped(client,queue,store,monkeypatch):
    login(client);source=chat(client);target=chat(client,[store.member['id']])
    seq=send(client,source,content='Forward this',images=[{'data':sample()}],invoke_agents=False).json['message_seq']
    uid=str(uuid4())
    first=post(client,f'messages/{seq}/forward',{'conversation_id':target,'request_id':uid})
    second=post(client,f'messages/{seq}/forward',{'conversation_id':target,'request_id':uid})
    assert first.status_code==200 and first.json==second.json
    assert len(queue.snapshot(target,store.member['id'])['messages'])==1
    image=queue.snapshot(target,store.member['id'])['messages'][0]['images'][0]['id']
    with queue.connection(True) as conn: conn.execute("UPDATE message_images SET analysis='Synthetic image'")
    monkeypatch.setattr(ai.sales,'report_data',report)
    task=send(client,source).json['task_id'];ai.execute(queue,queue.claim('worker',task),Model())
    seq=queue.snapshot(source,store.owner['id'])['messages'][-1]['seq']
    assert post(client,f'messages/{seq}/forward',{'conversation_id':target,'request_id':str(uuid4())}).status_code==200
    forwarded=queue.snapshot(target,store.owner['id'])['messages'][-1]
    assert forwarded['report_ready'] and forwarded['details']['forwarded']
    login(client,'Member')
    assert client.get('/api/internal/workforce/images/'+image).status_code==200
    assert client.get('/api/internal/workforce/conversations/'+target+'/export').status_code==200
    assert client.get('/api/internal/workforce/conversations/'+source+'/export').status_code==404
    assert post(client,f'messages/{seq}/forward',{'conversation_id':target,'request_id':str(uuid4())}).status_code==404
    assert client.get('/api/internal/workforce/tasks/'+forwarded['task_id']+'/snapshot').status_code==200


def test_reports_and_read_receipts(client,queue,store):
    login(client);cid=chat(client,[store.member['id']]);seq=send(client,cid,content='A message',invoke_agents=False).json['message_seq']
    login(client,'Member')
    assert patch(client,f'conversations/{cid}/preferences',{'read_seq':seq}).status_code==200
    assert post(client,f'messages/{seq}/report',{'reason':'Please review this message'}).status_code==200
    assert client.get('/api/internal/workforce/reports').status_code==403
    login(client)
    assert store.member['id'] in client.get(f'/api/internal/workforce/messages/{seq}/info').json['read_by']
    assert client.get('/api/internal/workforce/reports').json['reports'][0]['reason']=='Please review this message'


def test_profile_library_similar_group_and_csrf(client,queue,store):
    login(client);cid=chat(client,[store.member['id']])
    assert client.patch(f'/api/internal/workforce/conversations/{cid}/profile',json={'title':'CSRF'}).status_code==403
    assert patch(client,f'conversations/{cid}/profile',{'avatar':{'data':sample()}}).status_code==200
    assert client.get(f'/api/internal/workforce/conversations/{cid}/avatar').mimetype=='image/png'
    people=client.get(f'/api/internal/workforce/conversations/{cid}/people').json['people']
    assert any(p['id']==store.admin['id'] for p in people)
    send(client,cid,content='Visible https://example.com',images=[{'data':sample()}],invoke_agents=False)
    for kind in ('media','links','search&q=visible'):
        result=client.get(f'/api/internal/workforce/conversations/{cid}/library?kind='+kind)
        assert result.status_code==200 and len(result.json['messages'])==1
    copied=post(client,f'conversations/{cid}/actions/similar',{'title':'Similar group'})
    assert copied.status_code==200 and queue.snapshot(copied.json['id'],store.member['id'])['messages']==[]
    first=post(client,'direct',{'user_id':store.member['id']}).json['id']
    assert post(client,'direct',{'user_id':store.member['id']}).json['id']==first
    login(client,'OtherAdmin')
    assert client.get(f'/api/internal/workforce/conversations/{cid}/avatar').status_code==404
    assert post(client,f'conversations/{cid}/actions/similar',{'title':'Denied'}).status_code==404
