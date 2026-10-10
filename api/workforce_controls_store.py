"""Member-scoped chat organization and message actions."""
import json
import secrets
import time
from uuid import uuid4
from api import portal
from api.portal import PortalError

PREF_DEFAULTS = dict(archived=0, pinned=0, favorite=0, muted_until=0, read_seq=0, unread=0,
                     cleared_seq=0, theme='default', list_name='', member_tag='')
REACTIONS = ('👍', '❤️', '😂', '😮', '😢', '🙏', '✅', '🎉', '👀', '🔥')

def visible_sql(alias='m'):
    # Parameters: current epoch, current user, current user. Alias is code-owned.
    return f'''NOT EXISTS (SELECT 1 FROM message_details d WHERE d.message_seq={alias}.seq
        AND (d.deleted=1 OR (d.expires_at>0 AND d.expires_at<=?)))
        AND NOT EXISTS (SELECT 1 FROM message_flags f WHERE f.message_seq={alias}.seq AND f.user_id=? AND f.hidden=1)
        AND {alias}.seq>COALESCE((SELECT cleared_seq FROM chat_preferences p
            WHERE p.conversation_id={alias}.conversation_id AND p.user_id=?),0)'''

def visible_params(user):
    return (time.time(), user, user)

class ControlsStore:
    def direct_chat(self, user, person):
        from api.workforce_store import now
        pair=sorted([user['id'],person['id']]); key='direct:'+':'.join(pair)
        with self.connection(True) as conn:
            shared=conn.execute('SELECT 1 FROM members a JOIN members b ON a.conversation_id=b.conversation_id WHERE a.user_id=? AND b.user_id=? LIMIT 1',pair).fetchone()
            if not shared: raise PortalError('Private replies require a shared group.',403)
            old=conn.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            if old:
                members=sorted(r['user_id'] for r in conn.execute('SELECT user_id FROM members WHERE conversation_id=?',(old['value'],)))
                if members==pair: return old['value']
            chat=str(uuid4())
            conn.execute('INSERT INTO conversations VALUES(?,?,?,?)',(chat,(user['display_name']+' / '+person['display_name'])[:80],user['id'],now()))
            conn.executemany('INSERT INTO members VALUES(?,?)',[(chat,uid) for uid in pair])
            conn.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,chat))
            self.audit(conn,user['id'],'conversation.created',details={'conversation_id':chat})
            return chat

    @staticmethod
    def preferences(conn, chat, user):
        row=conn.execute('SELECT * FROM chat_preferences WHERE conversation_id=? AND user_id=?',(chat,user)).fetchone()
        return {**PREF_DEFAULTS, **(dict(row) if row else {})}

    @staticmethod
    def event(conn, chat, actor, event, details=None):
        from api.workforce_store import now
        conn.execute('INSERT INTO chat_events(conversation_id,actor_id,event,details,created_at) VALUES(?,?,?,?,?)',
                     (chat,actor,event,json.dumps(details or {}),now()))

    def manage(self, conn, chat, user):
        conversation=self.member(conn,chat,user['id'])
        if user['role']!='admin' and conversation['creator_id']!=user['id']:
            raise PortalError('Only the group creator or a group-member administrator can do this.',403)
        return conversation

    def message(self, conn, seq, user):
        row=conn.execute('SELECT m.* FROM messages m WHERE m.seq=? AND '+visible_sql(),(seq,*visible_params(user))).fetchone()
        if not row: raise PortalError('Message is unavailable.',404)
        self.member(conn,row['conversation_id'],user)
        return dict(row)

    def message_details(self, conn, seq, chat, reply=None, forwarded=False):
        profile=conn.execute('SELECT disappearing FROM chat_profiles WHERE conversation_id=?',(chat,)).fetchone()
        ttl=profile['disappearing'] if profile else 0
        conn.execute('INSERT INTO message_details(message_seq,reply_seq,forwarded,expires_at) VALUES(?,?,?,?)',
                     (seq,reply,int(forwarded),time.time()+ttl if ttl else 0))

    def chat_controls(self, chat, user):
        with self.connection() as conn:
            conversation=self.member(conn,chat,user['id'])
            row=conn.execute('SELECT * FROM chat_profiles WHERE conversation_id=?',(chat,)).fetchone()
            profile=dict(row) if row else dict(description='',avatar=None,disappearing=0)
            profile['original_creator']=profile.get('original_creator') or conversation['creator_id']
            profile['has_avatar']=bool(profile.pop('avatar',None))
            prefs=self.preferences(conn,chat,user['id'])
            tags=[dict(r) for r in conn.execute('SELECT user_id,member_tag,read_seq FROM chat_preferences WHERE conversation_id=?',(chat,))]
            revision=conn.execute('SELECT COALESCE(MAX(seq),0) AS revision FROM chat_events WHERE conversation_id=?',(chat,)).fetchone()['revision']
            expired=conn.execute('SELECT COUNT(*) AS n FROM message_details d JOIN messages m ON m.seq=d.message_seq WHERE m.conversation_id=? AND d.expires_at>0 AND d.expires_at<=?',(chat,time.time())).fetchone()['n']
            revision=str(revision)+':'+str(expired)
            return dict(profile=profile,preferences=prefs,member_preferences=tags,revision=revision,
                        can_manage=user['role']=='admin' or conversation['creator_id']==user['id'])

    def update_preferences(self, chat, user, values):
        allowed={'archived','pinned','favorite','unread','muted_until','theme','list_name','member_tag','read_seq'}
        if not values or set(values)-allowed: raise PortalError('Invalid chat setting.')
        for key,value in values.items():
            if key in ('archived','pinned','favorite','unread') and (type(value) not in (bool,int) or value not in (0,1)): raise PortalError('Invalid chat setting.')
            if key=='muted_until' and (type(value) not in (int,float) or not 0<=value<=time.time()+366*86400): raise PortalError('Choose a valid mute duration.')
            if key=='read_seq' and (type(value)!=int or value<0 or value>9223372036854775806): raise PortalError('Invalid read position.')
            if key=='theme' and value not in ('default','forest','midnight','plum'): raise PortalError('Choose a chat theme.')
            if key in ('list_name','member_tag') and (not isinstance(value,str) or len(value)>40): raise PortalError('Use up to 40 characters.')
        with self.connection(True) as conn:
            self.member(conn,chat,user['id'])
            conn.execute('INSERT INTO chat_preferences(conversation_id,user_id) VALUES(?,?) ON CONFLICT DO NOTHING',(chat,user['id']))
            if 'read_seq' in values:
                maximum=conn.execute('SELECT COALESCE(MAX(seq),0) AS seq FROM messages WHERE conversation_id=?',(chat,)).fetchone()['seq']
                values={**values,'read_seq':min(values['read_seq'],maximum)}
            for key,value in values.items():
                if key=='read_seq':
                    conn.execute('UPDATE chat_preferences SET read_seq=CASE WHEN read_seq>? THEN read_seq ELSE ? END WHERE conversation_id=? AND user_id=?',(value,value,chat,user['id']))
                else:
                    conn.execute('UPDATE chat_preferences SET '+key+'=? WHERE conversation_id=? AND user_id=?',(int(value) if isinstance(value,bool) else value,chat,user['id']))
            if set(values)-{'read_seq','unread'}: self.event(conn,chat,user['id'],'preferences.changed')

    def update_group(self, chat, user, payload):
        if set(payload)-{'title','description','avatar','disappearing'} or not payload: raise PortalError('Invalid group settings.')
        from api.workforce_images import upload_images
        title=portal.text_field(payload,'title',80) if 'title' in payload else None
        description=portal.text_field(payload,'description',1000,False) if 'description' in payload else None
        avatar=None
        if 'avatar' in payload and payload['avatar'] is not None:
            avatar=json.dumps(upload_images([payload['avatar']])[0])
        ttl=payload.get('disappearing')
        if ttl is not None and (type(ttl)!=int or ttl not in (0,86400,604800,7776000)): raise PortalError('Choose Off, 24 hours, 7 days or 90 days.')
        with self.connection(True) as conn:
            self.manage(conn,chat,user)
            conn.execute('INSERT INTO chat_profiles(conversation_id) VALUES(?) ON CONFLICT DO NOTHING',(chat,))
            if title is not None: conn.execute('UPDATE conversations SET title=? WHERE id=?',(title,chat))
            if description is not None: conn.execute('UPDATE chat_profiles SET description=? WHERE conversation_id=?',(description,chat))
            if 'avatar' in payload: conn.execute('UPDATE chat_profiles SET avatar=? WHERE conversation_id=?',(avatar,chat))
            if ttl is not None: conn.execute('UPDATE chat_profiles SET disappearing=? WHERE conversation_id=?',(ttl,chat))
            self.event(conn,chat,user['id'],'group.updated',{'fields':list(payload)})

    def change_member(self, chat, user, member_id, remove=False):
        available=portal.db('portal_users',id='eq.'+member_id,limit=1)
        if not remove and (not available or not available[0]['active'] or available[0].get('rest_mode')): raise PortalError('That employee is unavailable.')
        with self.connection(True) as conn:
            conversation=self.manage(conn,chat,user)
            if remove:
                if member_id==conversation['creator_id']: raise PortalError('The group creator must transfer ownership before leaving or being removed.')
                conn.execute('DELETE FROM members WHERE conversation_id=? AND user_id=?',(chat,member_id))
                conn.execute("UPDATE tasks SET status='cancelled',step='Member removed',lease_owner=NULL WHERE conversation_id=? AND creator_id=? AND status IN ('pending','running')",(chat,member_id))
            else:
                if conn.execute('SELECT COUNT(*) AS n FROM members WHERE conversation_id=?',(chat,)).fetchone()['n']>=21: raise PortalError('A group supports up to 21 people.')
                conn.execute('INSERT INTO members VALUES(?,?) ON CONFLICT DO NOTHING',(chat,member_id))
            self.event(conn,chat,user['id'],'member.removed' if remove else 'member.added',{'name':available[0]['display_name'] if available else 'Former member'})

    def group_action(self, chat, user, action, payload):
        with self.connection(True) as conn:
            conversation=self.member(conn,chat,user['id'])
            if action=='clear':
                maximum=conn.execute('SELECT COALESCE(MAX(seq),0) AS seq FROM messages WHERE conversation_id=?',(chat,)).fetchone()['seq']
                conn.execute('INSERT INTO chat_preferences(conversation_id,user_id,cleared_seq) VALUES(?,?,?) ON CONFLICT(conversation_id,user_id) DO UPDATE SET cleared_seq=excluded.cleared_seq',(chat,user['id'],maximum))
                conn.execute('UPDATE chat_preferences SET read_seq=?,unread=0 WHERE conversation_id=? AND user_id=?',(maximum,chat,user['id']))
            elif action=='exit':
                if conversation['creator_id']==user['id']:
                    conn.execute('INSERT INTO chat_profiles(conversation_id,original_creator) VALUES(?,?) ON CONFLICT DO NOTHING',(chat,user['id']))
                    conn.execute("UPDATE chat_profiles SET original_creator=? WHERE conversation_id=? AND original_creator=''",(user['id'],chat))
                    successor=conn.execute('SELECT user_id FROM members WHERE conversation_id=? AND user_id<>? ORDER BY user_id LIMIT 1',(chat,user['id'])).fetchone()
                    if successor: conn.execute('UPDATE conversations SET creator_id=? WHERE id=?',(successor['user_id'],chat))
                conn.execute('DELETE FROM members WHERE conversation_id=? AND user_id=?',(chat,user['id']))
                conn.execute("UPDATE tasks SET status='cancelled',step='Requester left group',lease_owner=NULL WHERE conversation_id=? AND creator_id=? AND status IN ('pending','running')",(chat,user['id']))
                conn.execute('DELETE FROM chat_invites WHERE conversation_id=?',(chat,))
            elif action=='invite':
                self.manage(conn,chat,user)
                token=secrets.token_urlsafe(32)
                conn.execute('DELETE FROM chat_invites WHERE conversation_id=?',(chat,))
                conn.execute('INSERT INTO chat_invites VALUES(?,?,?,?)',(portal.digest(token),chat,user['id'],time.time()+604800))
                self.event(conn,chat,user['id'],'invite.created')
                return {'token':token}
            elif action=='revoke-invite':
                self.manage(conn,chat,user)
                conn.execute('DELETE FROM chat_invites WHERE conversation_id=?',(chat,))
            else: raise PortalError('Unknown group action.',404)
            self.event(conn,chat,user['id'],'group.'+action)
            return {}

    def join_invite(self, token, user):
        if not isinstance(token,str) or len(token)>100: raise PortalError('Invalid invitation.')
        with self.connection(True) as conn:
            invite=conn.execute('SELECT * FROM chat_invites WHERE token_hash=? AND expires_at>?',(portal.digest(token),time.time())).fetchone()
            if not invite: raise PortalError('This invitation expired or was revoked.',404)
            chat=invite['conversation_id']
            if conn.execute('SELECT 1 FROM members WHERE conversation_id=? AND user_id=?',(chat,user['id'])).fetchone(): return chat
            if conn.execute('SELECT COUNT(*) AS n FROM members WHERE conversation_id=?',(chat,)).fetchone()['n']>=21: raise PortalError('This group is full.')
            conn.execute('INSERT INTO members VALUES(?,?) ON CONFLICT DO NOTHING',(chat,user['id']))
            self.event(conn,chat,user['id'],'member.joined',{'name':user['display_name']})
            return chat

    def message_action(self, seq, user, action, payload):
        from api.workforce_store import now
        with self.connection(True) as conn:
            message=self.message(conn,seq,user['id']); chat=message['conversation_id']
            if action in ('star','hide'):
                conn.execute('INSERT INTO message_flags(message_seq,user_id) VALUES(?,?) ON CONFLICT DO NOTHING',(seq,user['id']))
                field='starred' if action=='star' else 'hidden'
                conn.execute('UPDATE message_flags SET '+field+'=1-'+field+' WHERE message_seq=? AND user_id=?',(seq,user['id']))
            elif action=='react':
                emoji=payload.get('emoji')
                if emoji not in REACTIONS: raise PortalError('Choose a supported reaction.')
                old=conn.execute('SELECT emoji FROM message_reactions WHERE message_seq=? AND user_id=?',(seq,user['id'])).fetchone()
                conn.execute('DELETE FROM message_reactions WHERE message_seq=? AND user_id=?',(seq,user['id']))
                if not old or old['emoji']!=emoji: conn.execute('INSERT INTO message_reactions VALUES(?,?,?)',(seq,user['id'],emoji))
            elif action=='pin':
                self.manage(conn,chat,user)
                conn.execute('INSERT INTO message_details(message_seq) VALUES(?) ON CONFLICT DO NOTHING',(seq,))
                conn.execute('UPDATE message_details SET pinned=1-pinned WHERE message_seq=?',(seq,))
            elif action=='delete':
                if message['sender_id']!=user['id']: self.manage(conn,chat,user)
                conn.execute('INSERT INTO message_details(message_seq) VALUES(?) ON CONFLICT DO NOTHING',(seq,))
                conn.execute('UPDATE message_details SET deleted=1 WHERE message_seq=?',(seq,))
                conn.execute("UPDATE messages SET content='Message deleted' WHERE seq=?",(seq,))
                conn.execute('DELETE FROM message_images WHERE message_seq=?',(seq,))
                if message['task_id']:
                    conn.execute("UPDATE tasks SET result=NULL,status=CASE WHEN status IN ('pending','running') THEN 'cancelled' ELSE status END,lease_owner=NULL WHERE id=?",(message['task_id'],))
            else: raise PortalError('Unknown message action.',404)
            self.event(conn,chat,user['id'],'message.'+action)

    def report_chat(self, chat, user, reason, seq=None):
        from api.workforce_store import now
        with self.connection(True) as conn:
            self.member(conn,chat,user['id'])
            if seq and self.message(conn,seq,user['id'])['conversation_id']!=chat: raise PortalError('Message not found.',404)
            conn.execute('INSERT INTO chat_reports VALUES(?,?,?,?,?,?)',(str(uuid4()),chat,seq,user['id'],reason,now()))

    def forward(self, seq, target, user, request_id):
        from api.workforce_store import now
        with self.connection(True) as conn:
            message=self.message(conn,seq,user['id']); self.member(conn,target,user['id'])
            old=conn.execute('SELECT seq FROM messages WHERE conversation_id=? AND sender_id=? AND request_id=?',(target,user['id'],request_id)).fetchone()
            if old: return old['seq']
            # Explicit forwarding copies visible attachments into the destination's permissions.
            images=[dict(r) for r in conn.execute('SELECT * FROM message_images WHERE message_seq=?',(seq,))]
            report=conn.execute('SELECT result FROM tasks WHERE id=?',(message['task_id'],)).fetchone() if message['task_id'] else None
            new_seq=conn.execute('INSERT INTO messages(conversation_id,sender_id,sender_name,kind,content,created_at,request_id) VALUES(?,?,?,\'human\',?,?,?) RETURNING seq',
                (target,user['id'],user['display_name'],message['content'],now(),request_id)).fetchone()['seq']
            self.save_images(conn,new_seq,images); self.message_details(conn,new_seq,target,forwarded=True)
            if report and report['result']:
                task_id=str(uuid4())
                conn.execute("INSERT INTO tasks(id,conversation_id,message_seq,creator_id,session_version,model,status,step,created_at,completed_at,result) VALUES(?,?,?,?,?,?,'completed','Forwarded report',?,?,?)",
                    (task_id,target,new_seq,user['id'],user['session_version'],'forwarded',now(),now(),report['result']))
                conn.execute('UPDATE messages SET task_id=? WHERE seq=?',(task_id,new_seq))
            self.event(conn,target,user['id'],'message.forwarded')
            return new_seq
