"""Authenticated routes for chat, group and message controls."""
import base64
import json
import time
from datetime import datetime, timezone
from flask import g, jsonify, request, Response
from api import portal
from api.portal import require_user, body, valid_id, text_field, PortalError
from api.workforce_controls_store import visible_sql, visible_params


def register_controls(app, get_store):
    @app.get('/api/internal/workforce/memory')
    @require_user()
    def memory_list():
        return jsonify(get_store().memory_list(g.portal_user))

    @app.post('/api/internal/workforce/memory')
    @require_user()
    def memory_add():
        portal.rate_limit('workforce-memory',g.portal_user['id'],60,60)
        return jsonify(id=get_store().save_memory(g.portal_user,body())),201

    @app.patch('/api/internal/workforce/memory/settings')
    @require_user()
    def memory_settings():
        get_store().memory_toggle(g.portal_user,body().get('enabled'))
        return jsonify(ok=True)

    @app.patch('/api/internal/workforce/memory/<mid>')
    @require_user()
    def memory_edit(mid):
        return jsonify(id=get_store().save_memory(g.portal_user,body(),valid_id(mid)))

    @app.delete('/api/internal/workforce/memory/<mid>')
    @require_user()
    def memory_forget(mid):
        get_store().forget_memory(g.portal_user,valid_id(mid))
        return jsonify(ok=True)

    @app.post('/api/internal/workforce/direct')
    @require_user()
    def direct():
        data=body(); uid=valid_id(text_field(data,'user_id',36)); store=get_store()
        users=portal.db('portal_users',id='eq.'+uid,limit=1)
        if uid==g.portal_user['id'] or not users or not users[0]['active'] or users[0].get('rest_mode'):
            raise PortalError('That employee is unavailable.')
        # Private replies require an existing shared group, not arbitrary user IDs.
        with store.connection() as conn:
            shared=conn.execute('SELECT 1 FROM members a JOIN members b ON a.conversation_id=b.conversation_id WHERE a.user_id=? AND b.user_id=? LIMIT 1',(g.portal_user['id'],uid)).fetchone()
            if not shared: raise PortalError('Private replies require a shared group.',403)
        portal.rate_limit('workforce-create',g.portal_user['id'],20,3600)
        return jsonify(id=store.direct_chat(g.portal_user,users[0]))

    @app.patch('/api/internal/workforce/conversations/<chat>/preferences')
    @require_user()
    def preferences(chat):
        get_store().update_preferences(valid_id(chat),g.portal_user,body())
        return jsonify(ok=True)

    @app.patch('/api/internal/workforce/conversations/<chat>/profile')
    @require_user()
    def profile(chat):
        get_store().update_group(valid_id(chat),g.portal_user,body())
        return jsonify(ok=True)

    @app.get('/api/internal/workforce/conversations/<chat>/avatar')
    @require_user()
    def avatar(chat):
        store=get_store()
        with store.connection() as conn:
            store.member(conn,valid_id(chat),g.portal_user['id'])
            row=conn.execute('SELECT avatar FROM chat_profiles WHERE conversation_id=?',(chat,)).fetchone()
            if not row or not row['avatar']: raise PortalError('No group photo.',404)
            image=json.loads(row['avatar'])
        return Response(base64.b64decode(image['data']),mimetype=image['mime'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/api/internal/workforce/conversations/<chat>/people')
    @require_user()
    def people(chat):
        store=get_store()
        with store.connection() as conn: store.manage(conn,valid_id(chat),g.portal_user)
        users=portal.db('portal_users',select='id,display_name,username,active,rest_mode',limit=500)
        return jsonify(people=[{k:u[k] for k in ('id','display_name','username')} for u in users if u['active'] and not u.get('rest_mode')])

    @app.post('/api/internal/workforce/conversations/<chat>/members')
    @require_user()
    def members(chat):
        data=body()
        if data.get('action') not in ('add','remove'): raise PortalError('Choose add or remove.')
        get_store().change_member(valid_id(chat),g.portal_user,valid_id(text_field(data,'user_id',36)),data['action']=='remove')
        return jsonify(ok=True)

    @app.post('/api/internal/workforce/conversations/<chat>/actions/<action>')
    @require_user()
    def action(chat,action):
        data=body(); store=get_store(); chat=valid_id(chat)
        portal.rate_limit('workforce-controls',g.portal_user['id'],120,60)
        if action=='report':
            store.report_chat(chat,g.portal_user,text_field(data,'reason',1000))
            return jsonify(ok=True)
        if action=='similar':
            with store.connection() as conn:
                store.manage(conn,chat,g.portal_user)
                members=[r['user_id'] for r in conn.execute('SELECT user_id FROM members WHERE conversation_id=?',(chat,))]
            title=text_field(data,'title',80)
            new=store.create_chat(title,g.portal_user['id'],members)
            with store.connection(True) as conn:
                for row in conn.execute('SELECT agent_id FROM conversation_agents WHERE conversation_id=?',(chat,)).fetchall():
                    conn.execute('INSERT INTO conversation_agents VALUES(?,?,?,?)',(new,row['agent_id'],g.portal_user['id'],datetime.now(timezone.utc).isoformat()))
            return jsonify(id=new)
        return jsonify(store.group_action(chat,g.portal_user,action,data))

    @app.post('/api/internal/workforce/invites/join')
    @require_user()
    def join():
        portal.rate_limit('workforce-join',g.portal_user['id'],20,3600)
        return jsonify(id=get_store().join_invite(text_field(body(),'token',100),g.portal_user))

    @app.get('/api/internal/workforce/conversations/<chat>/events')
    @require_user()
    def events(chat):
        store=get_store()
        with store.connection() as conn:
            store.member(conn,valid_id(chat),g.portal_user['id'])
            rows=[dict(r) for r in conn.execute("SELECT event,details,created_at FROM chat_events WHERE conversation_id=? AND (event LIKE 'member.%' OR event LIKE 'group.%') ORDER BY seq DESC LIMIT 200",(chat,))]
        return jsonify(events=rows)

    @app.get('/api/internal/workforce/conversations/<chat>/export')
    @require_user()
    def export(chat):
        store=get_store()
        with store.connection() as conn:
            conversation=store.member(conn,valid_id(chat),g.portal_user['id'])
            messages=[dict(r) for r in conn.execute('SELECT m.seq,m.sender_name,m.content,m.created_at FROM messages m WHERE m.conversation_id=? AND '+visible_sql()+' ORDER BY seq LIMIT 5001',(chat,*visible_params(g.portal_user['id'])))]
            if len(messages)>5000: raise PortalError('Export supports up to 5,000 visible messages. Narrow or clear your local history first.')
            for message in messages:
                message['images']=[{'name':r['name'],'path':'/api/internal/workforce/images/'+r['id']} for r in conn.execute('SELECT id,name FROM message_images WHERE message_seq=?',(message['seq'],))]
        return Response(json.dumps({'title':conversation['title'],'messages':messages},ensure_ascii=False,indent=2),mimetype='application/json',headers={'Content-Disposition':'attachment; filename="chat-export.json"'})

    @app.get('/api/internal/workforce/conversations/<chat>/library')
    @require_user()
    def library(chat):
        store=get_store(); kind=request.args.get('kind','media'); query=request.args.get('q','')[:100]
        if kind not in ('media','links','starred','pinned','search'): raise PortalError('Unknown message collection.')
        with store.connection() as conn:
            store.member(conn,valid_id(chat),g.portal_user['id'])
            extra={'media':"EXISTS (SELECT 1 FROM message_images i WHERE i.message_seq=m.seq) OR EXISTS (SELECT 1 FROM tasks t WHERE t.id=m.task_id AND t.result IS NOT NULL)",
                'links':"m.content LIKE '%https://%' OR m.content LIKE '%http://%'",'starred':"EXISTS (SELECT 1 FROM message_flags f WHERE f.message_seq=m.seq AND f.user_id=? AND f.starred=1)",
                'pinned':"EXISTS (SELECT 1 FROM message_details d WHERE d.message_seq=m.seq AND d.pinned=1)", 'search':"LOWER(m.content) LIKE ?"}[kind]
            params=[chat,*visible_params(g.portal_user['id'])]
            if kind=='starred': params.append(g.portal_user['id'])
            if kind=='search': params.append('%'+query.lower()+'%')
            rows=[dict(r) for r in conn.execute("SELECT m.*,EXISTS(SELECT 1 FROM tasks t WHERE t.id=m.task_id AND t.status='completed' AND t.result IS NOT NULL) AS report_ready FROM messages m WHERE m.conversation_id=? AND "+visible_sql()+' AND ('+extra+') ORDER BY seq DESC LIMIT 200',params)]
            images={}
            if rows:
                for image in conn.execute('SELECT i.id,i.name,i.message_seq FROM message_images i JOIN messages m ON m.seq=i.message_seq WHERE m.conversation_id=? AND m.seq>=? AND m.seq<=?',(chat,rows[-1]['seq'],rows[0]['seq'])):
                    images.setdefault(image['message_seq'],[]).append({'id':image['id'],'name':image['name']})
            for row in rows: row['images']=images.get(row['seq'],[])
        return jsonify(messages=rows)

    @app.get('/api/internal/workforce/messages/<int:seq>/info')
    @require_user()
    def message_info(seq):
        if not 0<seq<9223372036854775807: raise PortalError('Invalid message ID.')
        store=get_store()
        with store.connection() as conn:
            message=store.message(conn,seq,g.portal_user['id'])
            readers=[r['user_id'] for r in conn.execute('SELECT p.user_id FROM chat_preferences p JOIN members m ON m.conversation_id=p.conversation_id AND m.user_id=p.user_id WHERE p.conversation_id=? AND p.read_seq>=?',(message['conversation_id'],seq))]
        return jsonify(sent_at=message['created_at'],sender_name=message['sender_name'],read_by=readers)

    @app.post('/api/internal/workforce/messages/<int:seq>/<action>')
    @require_user()
    def message_action(seq,action):
        if not 0<seq<9223372036854775807: raise PortalError('Invalid message ID.')
        data=body();store=get_store()
        portal.rate_limit('workforce-message-actions',g.portal_user['id'],120,60)
        if action=='forward':
            return jsonify(seq=store.forward(seq,valid_id(text_field(data,'conversation_id',36)),g.portal_user,valid_id(text_field(data,'request_id',36))))
        if action=='report':
            with store.connection() as conn: message=store.message(conn,seq,g.portal_user['id'])
            store.report_chat(message['conversation_id'],g.portal_user,text_field(data,'reason',1000),seq)
        else: store.message_action(seq,g.portal_user,action,data)
        return jsonify(ok=True)

    @app.get('/api/internal/workforce/reports')
    @require_user(admin=True)
    def reports():
        with get_store().connection() as conn:
            rows=[dict(r) for r in conn.execute('SELECT id,conversation_id,message_seq,reason,created_at FROM chat_reports ORDER BY created_at DESC LIMIT 200')]
        return jsonify(reports=rows)
