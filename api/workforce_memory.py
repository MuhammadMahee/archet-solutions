"""Durable, user-owned notes and explicitly shared company knowledge."""
from datetime import datetime, timezone
import json
import re
from uuid import uuid4
from api.portal import PortalError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS workforce_memories (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL,
 topic TEXT NOT NULL, content TEXT NOT NULL, audience TEXT NOT NULL,
 source_chat TEXT NOT NULL, source_seq BIGINT NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS workforce_memories_owner ON workforce_memories(owner_id,scope);
CREATE TABLE IF NOT EXISTS workforce_memory_settings (
 user_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0);
'''


def stamp():
    return datetime.now(timezone.utc).isoformat()


def clean(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PortalError('Use a short title and a note up to 600 characters.')
    return value.strip()


def sensitive(text):
    return bool(re.search(r'(?i)(password|api[_ -]?key|secret|bearer |private key|access[_ -]?token|session[_ -]?cookie|social security|bank account|routing number|credit card|\bssn\b)',text))


class MemoryStore:
    @staticmethod
    def memory_settings(conn, uid):
        row=conn.execute('SELECT enabled,revision FROM workforce_memory_settings WHERE user_id=?',(uid,)).fetchone()
        return dict(row) if row else {'enabled':1,'revision':0}

    @staticmethod
    def bump_memory(conn, uid, enabled=None):
        conn.execute('INSERT INTO workforce_memory_settings(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING',(uid,))
        conn.execute('UPDATE workforce_memory_settings SET revision=revision+1 WHERE user_id=?',(uid,))
        if enabled is not None:
            conn.execute('UPDATE workforce_memory_settings SET enabled=? WHERE user_id=?',(int(enabled),uid))

    def memory_list(self, user):
        with self.connection() as conn:
            rows=[dict(r) for r in conn.execute("SELECT * FROM workforce_memories WHERE owner_id=? OR scope='company' ORDER BY updated_at DESC LIMIT 600",(user['id'],))]
            settings=self.memory_settings(conn,user['id'])
        for row in rows:
            row['can_edit']=row['scope']=='personal' and row['owner_id']==user['id'] or row['scope']=='company' and user['role']=='admin'
            row['audience_count']=len(json.loads(row.pop('audience')))
            row.pop('source_chat');row.pop('source_seq')
        return {'memories':rows,'enabled':bool(settings['enabled']),'can_share':user['role']=='admin'}

    def memory_context(self, task, user):
        with self.connection() as conn:
            self.member(conn,task['conversation_id'],user['id'])
            audience={r['user_id'] for r in conn.execute('SELECT user_id FROM members WHERE conversation_id=?',(task['conversation_id'],))}
            rows=[dict(r) for r in conn.execute("SELECT * FROM workforce_memories WHERE owner_id=? OR scope='company' ORDER BY updated_at DESC LIMIT 600",(user['id'],))]
            settings=self.memory_settings(conn,user['id'])
        # Personal notes never follow their author into a group with new recipients.
        rows=[r for r in rows if r['scope']=='company' or audience.issubset(set(json.loads(r['audience'])))]
        words=set(re.findall(r'\w{3,}',task['content'].lower()))
        rows.sort(key=lambda r:len(words & set(re.findall(r'\w{3,}',(r['topic']+' '+r['content']).lower()))),reverse=True)
        notes=[];size=0
        for r in rows[:30]:
            size+=len(r['content'])+len(r['topic'])
            if size>6000:break
            notes.append({k:r[k] for k in ('id','scope','topic','content','updated_at')})
        return {'notes':notes,'automatic':bool(settings['enabled']),'revision':settings['revision']}

    def remember_request(self, task, user, candidates, revision):
        """Only verbatim evidence from this request, never assistant guesses/history."""
        if not candidates:return 0
        with self.connection(True) as conn:
            settings=self.memory_settings(conn,user['id'])
            if not settings['enabled'] or settings['revision']!=revision:return 0
            self.member(conn,task['conversation_id'],user['id'])
            self.message(conn,task['message_seq'],user['id'])
            detail=conn.execute('SELECT expires_at FROM message_details WHERE message_seq=?',(task['message_seq'],)).fetchone()
            if detail and detail['expires_at']:return 0  # Disappearing messages never become durable notes.
            audience=json.dumps(sorted(r['user_id'] for r in conn.execute('SELECT user_id FROM members WHERE conversation_id=?',(task['conversation_id'],))))
            count=conn.execute("SELECT COUNT(*) AS n FROM workforce_memories WHERE owner_id=? AND scope='personal'",(user['id'],)).fetchone()['n']
            saved=0
            for candidate in candidates[:3]:
                topic=candidate['topic'].strip();content=candidate['evidence'].strip()
                if len(content)<5 or content not in task['content'] or sensitive(content):continue
                old=conn.execute("SELECT id,source_seq FROM workforce_memories WHERE owner_id=? AND scope='personal' AND topic=? AND audience=?",(user['id'],topic,audience)).fetchone()
                if old:
                    if old['source_seq']>=task['message_seq']:continue
                    conn.execute('UPDATE workforce_memories SET content=?,source_chat=?,source_seq=?,updated_at=? WHERE id=?',(content,task['conversation_id'],task['message_seq'],stamp(),old['id']))
                else:
                    if count>=200:continue
                    conn.execute('INSERT INTO workforce_memories VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uuid4()),user['id'],'personal',topic,content,audience,task['conversation_id'],task['message_seq'],stamp(),stamp()))
                    count+=1
                saved+=1
            return saved

    def save_memory(self, user, data, memory_id=None):
        topic=clean(data.get('topic'),80);content=clean(data.get('content'),600)
        scope=data.get('scope','personal')
        if scope not in ('personal','company'):raise PortalError('Choose personal or company memory.')
        if scope=='company' and user['role']!='admin':raise PortalError('Only administrators can share company memory.',403)
        if sensitive(content):raise PortalError('Do not store passwords, keys or financial identifiers in memory.')
        with self.connection(True) as conn:
            old=None
            if memory_id:
                old=self.editable_memory(conn,memory_id,user)
            count=conn.execute('SELECT COUNT(*) AS n FROM workforce_memories WHERE scope=?'+(' AND owner_id=?' if scope=='personal' else ''),(scope,user['id']) if scope=='personal' else (scope,)).fetchone()['n']
            if count>=200 and not old:raise PortalError('Memory is full. Remove an old note first.')
            mid=memory_id or str(uuid4())
            audience=old['audience'] if old and old['scope']=='personal' and scope=='personal' else json.dumps([user['id']])
            if old:
                conn.execute('UPDATE workforce_memories SET owner_id=?,scope=?,topic=?,content=?,audience=?,source_seq=0,updated_at=? WHERE id=?',(user['id'],scope,topic,content,audience,stamp(),mid))
            else:
                conn.execute('INSERT INTO workforce_memories VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,user['id'],scope,topic,content,audience,'',0,stamp(),stamp()))
            self.bump_memory(conn,user['id'])
            self.audit(conn,user['id'],'memory.saved',details={'id':mid,'scope':scope})
        return mid

    @staticmethod
    def editable_memory(conn, mid, user):
        row=conn.execute('SELECT * FROM workforce_memories WHERE id=?',(mid,)).fetchone()
        if not row or not (row['scope']=='personal' and row['owner_id']==user['id'] or row['scope']=='company' and user['role']=='admin'):
            raise PortalError('Memory not found or not editable.',404)
        return dict(row)

    def forget_memory(self, user, mid):
        with self.connection(True) as conn:
            self.editable_memory(conn,mid,user)
            conn.execute('DELETE FROM workforce_memories WHERE id=?',(mid,))
            self.bump_memory(conn,user['id'])
            self.audit(conn,user['id'],'memory.forgotten',details={'id':mid})

    def memory_toggle(self, user, enabled):
        if not isinstance(enabled,bool):raise PortalError('Choose whether automatic memory is enabled.')
        with self.connection(True) as conn:self.bump_memory(conn,user['id'],enabled)
