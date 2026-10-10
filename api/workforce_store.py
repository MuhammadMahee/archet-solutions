"""Durable local chat and job queue. SQL parameters never come from model SQL."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from api.portal import PortalError
from api.workforce_agents import AGENTS, DEFAULT_IDS


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, creator_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members (
 conversation_id TEXT NOT NULL REFERENCES conversations(id), user_id TEXT NOT NULL,
 PRIMARY KEY(conversation_id,user_id));
CREATE TABLE IF NOT EXISTS messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 sender_id TEXT NOT NULL, sender_name TEXT NOT NULL, kind TEXT NOT NULL,
 content TEXT NOT NULL, created_at TEXT NOT NULL, task_id TEXT, request_id TEXT,
 UNIQUE(conversation_id,sender_id,request_id));
CREATE INDEX IF NOT EXISTS messages_chat ON messages(conversation_id,seq);
CREATE INDEX IF NOT EXISTS messages_task ON messages(task_id,seq);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 message_seq INTEGER NOT NULL REFERENCES messages(seq), creator_id TEXT NOT NULL,
 session_version TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
 step TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
 error TEXT, result TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 lease_owner TEXT, lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS tasks_queue ON tasks(status,created_at);
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor_id TEXT NOT NULL,
 event TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, heartbeat REAL NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_agents (
 conversation_id TEXT NOT NULL REFERENCES conversations(id), agent_id TEXT NOT NULL,
 added_by TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(conversation_id,agent_id));
CREATE TABLE IF NOT EXISTS message_mentions (
 message_seq INTEGER NOT NULL REFERENCES messages(seq), recipient_id TEXT NOT NULL,
 PRIMARY KEY(message_seq,recipient_id));
CREATE INDEX IF NOT EXISTS mentions_recipient ON message_mentions(recipient_id,message_seq);
CREATE TABLE IF NOT EXISTS message_images (
 id TEXT PRIMARY KEY, message_seq INTEGER NOT NULL REFERENCES messages(seq),
 name TEXT NOT NULL, mime TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 size INTEGER NOT NULL, data TEXT NOT NULL, source TEXT NOT NULL, analysis TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS images_message ON message_images(message_seq);
PRAGMA user_version=1;
"""


class Store:
    lease_seconds = 45
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self, write=False):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def audit(conn, actor, event, task=None, details=None):
        conn.execute('INSERT INTO audit(task_id,actor_id,event,details,created_at) VALUES(?,?,?,?,?)',
                     (task, actor, event, json.dumps(details or {}), now()))

    @staticmethod
    def member(conn, chat, user):
        row = conn.execute('SELECT c.* FROM conversations c JOIN members m ON m.conversation_id=c.id '
                           'WHERE c.id=? AND m.user_id=?', (chat, user)).fetchone()
        if not row:
            raise PortalError('Conversation not found.', 404)
        return dict(row)

    def create_chat(self, title, creator, members):
        chat = str(uuid4())
        with self.connection(True) as conn:
            conn.execute('INSERT INTO conversations VALUES(?,?,?,?)', (chat, title, creator, now()))
            conn.executemany('INSERT INTO members VALUES(?,?)', [(chat, uid) for uid in set([creator, *members])])
            self.audit(conn, creator, 'conversation.created', details={'conversation_id': chat})
        return chat

    def list_chats(self, user):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute('''SELECT c.*,
                (SELECT content FROM messages WHERE conversation_id=c.id ORDER BY seq DESC LIMIT 1) AS preview,
                (SELECT MAX(seq) FROM messages WHERE conversation_id=c.id) AS last_seq,
                (SELECT MAX(mm.message_seq) FROM message_mentions mm JOIN messages msg ON msg.seq=mm.message_seq
                    WHERE msg.conversation_id=c.id AND mm.recipient_id=?) AS mention_seq,
                (SELECT COUNT(*) FROM tasks WHERE conversation_id=c.id AND status IN ('pending','running')) AS working
                FROM conversations c JOIN members m ON m.conversation_id=c.id WHERE m.user_id=?
                ORDER BY last_seq DESC NULLS LAST,c.created_at DESC LIMIT 200''', (user, user))]

    def snapshot(self, chat, user, after=0, before=0):
        with self.connection() as conn:
            conversation = self.member(conn, chat, user)
            select = '''SELECT m.*, CASE WHEN t.status='completed' AND t.result IS NOT NULL AND
                m.seq=(SELECT MAX(seq) FROM messages WHERE task_id=t.id) THEN 1 ELSE 0 END AS report_ready
                FROM messages m LEFT JOIN tasks t ON t.id=m.task_id WHERE m.conversation_id=? '''
            if after:
                rows = conn.execute(select + 'AND m.seq>? ORDER BY m.seq LIMIT 100', (chat, after)).fetchall()
            else:
                rows = conn.execute(select + 'AND m.seq<? ORDER BY m.seq DESC LIMIT 100',
                                    (chat, before or 9223372036854775807)).fetchall()[::-1]
            messages = [dict(row) for row in rows]
            mentions = {}
            images = {}
            if messages:
                for item in conn.execute('''SELECT i.id,i.message_seq,i.name,i.mime,i.width,i.height,i.source FROM message_images i
                    JOIN messages m ON m.seq=i.message_seq WHERE m.conversation_id=? AND m.seq>=? AND m.seq<=?''',
                    (chat, messages[0]['seq'], messages[-1]['seq'])):
                    images.setdefault(item['message_seq'], []).append(dict(item))
                for item in conn.execute('''SELECT mm.message_seq,mm.recipient_id FROM message_mentions mm
                    JOIN messages m ON m.seq=mm.message_seq WHERE m.conversation_id=? AND m.seq>=? AND m.seq<=?''',
                    (chat, messages[0]['seq'], messages[-1]['seq'])):
                    mentions.setdefault(item['message_seq'], []).append(item['recipient_id'])
            for message in messages:
                message['mention_ids'] = mentions.get(message['seq'], [])
                message['images'] = images.get(message['seq'], [])
                if message['report_ready']:
                    result = json.loads(conn.execute('SELECT result FROM tasks WHERE id=?', (message['task_id'],)).fetchone()['result'])
                    message['report_summary'] = {'store_count': len(result['rows']), 'total_boxes': result['totals'].get('total_boxes'),
                                                 'accessory_usd': result['totals'].get('accessory'), 'coverage': result['coverage'],
                                                 'start': result['start'], 'end': result['end']}
            oldest = messages[0]['seq'] if messages else 0
            has_older = bool(oldest and conn.execute('SELECT 1 FROM messages WHERE conversation_id=? AND seq<? LIMIT 1', (chat, oldest)).fetchone())
            tasks = [self.public_task(row) for row in conn.execute('''SELECT t.* FROM tasks t WHERE conversation_id=?
                AND NOT (t.status IN ('failed','cancelled') AND EXISTS (
                    SELECT 1 FROM settings s WHERE s.key=? || t.id AND s.value=CAST(t.attempts AS TEXT)))
                ORDER BY created_at DESC LIMIT 30''', (chat, 'dismissed:' + user + ':'))]
            members = [row['user_id'] for row in conn.execute('SELECT user_id FROM members WHERE conversation_id=?', (chat,))]
            agents = self.agent_ids(conn, chat)
        return dict(conversation=conversation, messages=messages, tasks=tasks, member_ids=members, agent_ids=agents, has_older=has_older)

    @staticmethod
    def agent_ids(conn, chat):
        return DEFAULT_IDS + [row['agent_id'] for row in conn.execute(
            'SELECT agent_id FROM conversation_agents WHERE conversation_id=? ORDER BY created_at,agent_id', (chat,))
            if row['agent_id'] in AGENTS and row['agent_id'] not in DEFAULT_IDS]

    def roster(self, chat, user):
        with self.connection() as conn:
            conversation = self.member(conn, chat, user)
            people = [r['user_id'] for r in conn.execute('SELECT user_id FROM members WHERE conversation_id=?', (chat,))]
            return conversation, people, self.agent_ids(conn, chat)

    def assignment_context(self, task):
        """Read only this member's conversation, stopping before the assignment."""
        with self.connection() as conn:
            conversation = self.member(conn, task['conversation_id'], task['creator_id'])
            members = [row['user_id'] for row in conn.execute(
                'SELECT user_id FROM members WHERE conversation_id=?', (task['conversation_id'],))]
            rows = conn.execute('''SELECT seq,sender_name,kind,content,created_at FROM messages
                WHERE conversation_id=? AND seq<? ORDER BY seq DESC LIMIT 25''',
                (task['conversation_id'], task['message_seq'])).fetchall()
            agents = self.agent_ids(conn, task['conversation_id'])
            mentions = [r['recipient_id'] for r in conn.execute(
                'SELECT recipient_id FROM message_mentions WHERE message_seq=?', (task['message_seq'],))]
            image_notes = [dict(r) for r in conn.execute('''SELECT i.analysis,i.name FROM message_images i
                JOIN messages m ON m.seq=i.message_seq WHERE m.conversation_id=? AND m.seq<? AND i.analysis<>''
                ORDER BY m.seq DESC LIMIT 2''', (task['conversation_id'], task['message_seq']))]
        history, remaining = [], 9000
        limited = len(rows) > 24
        for row in rows[:24]:
            content = row['content'][:min(2500, remaining)]
            if not content:
                limited = True
                break
            truncated = len(content) < len(row['content'])
            limited = limited or truncated
            history.append({'name': row['sender_name'][:100], 'kind': row['kind'],
                            'content': content, 'truncated': truncated, 'sent_at': row['created_at']})
            remaining -= len(content)
        return {'title': conversation['title'], 'creator_id': conversation['creator_id'], 'member_ids': members,
                'agent_ids': agents, 'mention_ids': mentions,
                'earlier_image_notes': image_notes,
                'recent_messages': history[::-1], 'history_limited': limited}

    @staticmethod
    def public_task(row):
        return {**{k: row[k] for k in ('id', 'creator_id', 'status', 'step', 'created_at', 'started_at', 'completed_at', 'error', 'attempts')},
                'has_report': row['status'] == 'completed' and bool(row['result'])}

    def enqueue(self, chat, user, content, request_id, model, invoke=True, mention_ids=None, images=None):
        with self.connection(True) as conn:
            self.member(conn, chat, user['id'])
            mentions = list(dict.fromkeys(mention_ids or []))
            allowed = set(self.agent_ids(conn, chat)) | {r['user_id'] for r in conn.execute(
                'SELECT user_id FROM members WHERE conversation_id=?', (chat,))}
            if len(mentions) > 10 or any(uid not in allowed for uid in mentions):
                raise PortalError('Mention up to 10 members of this group.')
            if len([uid for uid in mentions if uid in AGENTS and uid != 'ai-manager']) > 2:
                raise PortalError('Mention up to two specialist bots per message.')
            old = conn.execute('SELECT seq,task_id,content FROM messages WHERE conversation_id=? AND sender_id=? AND request_id=?',
                               (chat, user['id'], request_id)).fetchone()
            if old:
                old_images = sorted(r['data'] for r in conn.execute('SELECT data FROM message_images WHERE message_seq=?', (old['seq'],)))
                old_mentions = {r['recipient_id'] for r in conn.execute('SELECT recipient_id FROM message_mentions WHERE message_seq=?', (old['seq'],))}
                if old['content'] != content or bool(old['task_id']) != invoke or old_mentions != set(mentions) or old_images != sorted(i['data'] for i in (images or [])):
                    raise PortalError('This message ID was already used for another message.', 409)
                return dict(message_seq=old['seq'], task_id=old['task_id'])
            if invoke and conn.execute("SELECT COUNT(*) AS count FROM tasks WHERE creator_id=? AND status IN ('pending','running')", (user['id'],)).fetchone()['count'] >= 5:
                raise PortalError('You already have five active assignments. Wait or cancel one first.', 429)
            task = str(uuid4()) if invoke else None
            stamp = now()
            seq = conn.execute('''INSERT INTO messages(conversation_id,sender_id,sender_name,kind,content,created_at,task_id,request_id)
                VALUES(?,?,?,?,?,?,?,?) RETURNING seq''', (chat, user['id'], user['display_name'], 'human', content, stamp, task, request_id)).fetchone()['seq']
            conn.executemany('INSERT INTO message_mentions VALUES(?,?)', [(seq, uid) for uid in mentions])
            self.save_images(conn, seq, images or [])
            if invoke:
                conn.execute('''INSERT INTO tasks(id,conversation_id,message_seq,creator_id,session_version,model,status,step,created_at)
                    VALUES(?,?,?,?,?,?,'pending','Waiting to start',?)''',
                    (task, chat, seq, user['id'], user['session_version'], model, stamp))
            self.audit(conn, user['id'], 'message.sent', task, {'conversation_id': chat, 'invoke_agents': invoke})
        return dict(message_seq=seq, task_id=task)

    def control(self, task_id, user, action):
        with self.connection(True) as conn:
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise PortalError('Task not found.', 404)
            self.member(conn, row['conversation_id'], user['id'])
            if row['creator_id'] != user['id']:
                raise PortalError('Only the requesting employee can change this assignment.', 403)
            if action == 'cancel':
                if row['status'] not in ('pending', 'running'):
                    raise PortalError('This assignment has already ended.', 409)
                conn.execute("UPDATE tasks SET status='cancelled',step='Cancelled by requester',cancel_requested=1,completed_at=?,lease_owner=NULL WHERE id=?", (now(), task_id))
            else:
                if row['status'] not in ('failed', 'cancelled') or row['attempts'] >= 3:
                    raise PortalError('This assignment cannot be retried. Send a new message.', 409)
                if conn.execute("SELECT COUNT(*) AS count FROM tasks WHERE creator_id=? AND status IN ('pending','running')", (user['id'],)).fetchone()['count'] >= 5:
                    raise PortalError('You already have five active assignments.', 429)
                conn.execute("UPDATE tasks SET status='pending',step='Waiting to start',error=NULL,result=NULL,cancel_requested=0,lease_owner=NULL,lease_until=NULL,started_at=NULL,completed_at=NULL,session_version=? WHERE id=?",
                             (user['session_version'], task_id))
            self.audit(conn, user['id'], 'task.' + action, task_id)

    def dismiss(self, task_id, user):
        """Hide this ended attempt for this member; keep chat and audit history."""
        with self.connection(True) as conn:
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise PortalError('Assignment not found.', 404)
            self.member(conn, row['conversation_id'], user)
            if row['status'] not in ('failed', 'cancelled'):
                raise PortalError('Only failed or cancelled assignments can be dismissed.', 409)
            key = 'dismissed:' + user + ':' + task_id
            conn.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (key, str(row['attempts'])))
            self.audit(conn, user, 'task.dismissed', task_id)

    def heartbeat(self, worker):
        with self.connection(True) as conn:
            conn.execute('INSERT INTO workers VALUES(?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat', (worker, time.time()))
            conn.execute('DELETE FROM workers WHERE heartbeat<?', (time.time() - 86400,))
            conn.execute("UPDATE tasks SET lease_until=? WHERE lease_owner=? AND status='running'", (time.time() + 45, worker))

    def worker_online(self):
        with self.connection() as conn:
            return bool(conn.execute('SELECT 1 FROM workers WHERE heartbeat>? LIMIT 1', (time.time() - 30,)).fetchone())

    def expire(self):
        with self.connection(True) as conn:
            self._expire(conn)

    def _expire(self, conn):
        expired = conn.execute("SELECT id,creator_id FROM tasks WHERE status='running' AND lease_until<?", (time.time(),)).fetchall()
        for row in expired:
            conn.execute("UPDATE tasks SET status='failed',error='Processing stopped. Retry the assignment.',step='Assignment interrupted',completed_at=?,lease_owner=NULL WHERE id=?", (now(), row['id']))
            self.audit(conn, row['creator_id'], 'task.interrupted', row['id'])

    def claim(self, worker, task_id=None):
        with self.connection(True) as conn:
            # A crashed assignment is visible and manually retryable, never silently executed twice.
            self._expire(conn)
            query = "SELECT t.*,m.content FROM tasks t JOIN messages m ON m.seq=t.message_seq WHERE t.status='pending'"
            row = conn.execute(query + (' AND t.id=?' if task_id else '') + ' ORDER BY t.created_at LIMIT 1',
                               (task_id,) if task_id else ()).fetchone()
            if not row:
                return None
            conn.execute("UPDATE tasks SET status='running',step='AI Manager is reviewing the request',started_at=?,attempts=attempts+1,lease_owner=?,lease_until=? WHERE id=?",
                         (now(), worker, time.time() + self.lease_seconds, row['id']))
            self.audit(conn, row['creator_id'], 'task.started', row['id'])
            return {**dict(row), 'lease_owner': worker}

    def active(self, task):
        with self.connection() as conn:
            row = conn.execute('SELECT status,lease_owner FROM tasks WHERE id=?', (task['id'],)).fetchone()
            return bool(row and row['status'] == 'running' and row['lease_owner'] == task['lease_owner'])

    def progress(self, task, step, sender=None, content=None, event=None, details=None, complete=False, result=None, agents=None, user=None, images=None):
        with self.connection(True) as conn:
            row = conn.execute('SELECT status,lease_owner FROM tasks WHERE id=?', (task['id'],)).fetchone()
            if not row or row['status'] != 'running' or row['lease_owner'] != task['lease_owner']:
                return False
            if agents is not None:
                chat = self.member(conn, task['conversation_id'], task['creator_id'])
                if not user or user['id'] != task['creator_id'] or (user['role'] != 'admin' and chat['creator_id'] != user['id']):
                    raise PortalError('Only the group creator or an administrator can add AI teammates.', 403)
                if not agents or len(agents) > 6 or any(a not in AGENTS or a in DEFAULT_IDS for a in agents):
                    raise PortalError('Choose available specialist bots.')
                for agent in dict.fromkeys(agents):
                    conn.execute('INSERT INTO conversation_agents VALUES(?,?,?,?) ON CONFLICT(conversation_id,agent_id) DO NOTHING',
                                 (task['conversation_id'], agent, user['id'], now()))
                self.audit(conn, user['id'], 'agents.added', task['id'], {'agent_ids': agents})
                content = 'Ready in this group: ' + ', '.join(AGENTS[a]['name'] + ' (@' + AGENTS[a]['handle'] + ')' for a in dict.fromkeys(agents)) + '. Mention a bot to ask for help. These bots can advise and draft; adding them does not connect private business records.'
            if sender and content:
                seq = conn.execute('''INSERT INTO messages(conversation_id,sender_id,sender_name,kind,content,created_at,task_id)
                    VALUES(?,?,?,'ai',?,?,?) RETURNING seq''', (task['conversation_id'], sender[0], sender[1], content, now(), task['id'])).fetchone()['seq']
                self.save_images(conn, seq, images or [])
            conn.execute('UPDATE tasks SET step=? WHERE id=?', (step, task['id']))
            if event:
                self.audit(conn, task['creator_id'], event, task['id'], details)
            if complete:
                conn.execute("UPDATE tasks SET status='completed',completed_at=?,result=?,lease_owner=NULL WHERE id=?", (now(), json.dumps(result) if result else None, task['id']))
                self.audit(conn, task['creator_id'], 'task.completed', task['id'])
        return True

    @staticmethod
    def save_images(conn, seq, images):
        if not images:
            return
        used = conn.execute('SELECT COALESCE(SUM(size),0) AS used FROM message_images').fetchone()['used']
        if used + sum(i['size'] for i in images) > 100 * 1024 * 1024:
            raise PortalError('Chat image storage is full (100 MB). Contact your administrator before adding more images.', 413)
        for image in images:
            conn.execute('INSERT INTO message_images(id,message_seq,name,mime,width,height,size,data,source) VALUES(?,?,?,?,?,?,?,?,?)',
                         (str(uuid4()), seq, *[image[k] for k in ('name', 'mime', 'width', 'height', 'size', 'data', 'source')]))

    def image(self, image_id, user):
        with self.connection() as conn:
            row = conn.execute('''SELECT i.*,m.conversation_id FROM message_images i
                JOIN messages m ON m.seq=i.message_seq WHERE i.id=?''', (image_id,)).fetchone()
            if not row:
                raise PortalError('Image not found.', 404)
            self.member(conn, row['conversation_id'], user)
            return dict(row)

    def task_images(self, task):
        with self.connection() as conn:
            self.member(conn, task['conversation_id'], task['creator_id'])
            current = [dict(r) for r in conn.execute('SELECT * FROM message_images WHERE message_seq=?', (task['message_seq'],))]
            if current:
                return current
            previous = conn.execute('''SELECT m.seq FROM messages m JOIN message_images i ON i.message_seq=m.seq
                WHERE m.conversation_id=? AND m.seq<? AND m.kind='human' AND i.analysis=''
                AND m.seq IN (SELECT seq FROM messages WHERE conversation_id=? AND seq<? ORDER BY seq DESC LIMIT 24)
                ORDER BY m.seq DESC LIMIT 1''', (task['conversation_id'], task['message_seq'], task['conversation_id'], task['message_seq'])).fetchone()
            return [dict(r) for r in conn.execute('SELECT * FROM message_images WHERE message_seq=?', (previous['seq'],))] if previous else []

    def remember_images(self, task, analysis, images):
        with self.connection(True) as conn:
            self.member(conn, task['conversation_id'], task['creator_id'])
            for image in images:
                conn.execute('''UPDATE message_images SET analysis=? WHERE id=? AND message_seq IN
                    (SELECT seq FROM messages WHERE conversation_id=?)''', (analysis[:3500], image['id'], task['conversation_id']))

    def fail(self, task, message):
        with self.connection(True) as conn:
            changed = conn.execute("UPDATE tasks SET status='failed',step='Assignment failed',error=?,completed_at=?,lease_owner=NULL WHERE id=? AND status='running' AND lease_owner=?",
                                   (message, now(), task['id'], task['lease_owner'])).rowcount
            if changed:
                self.audit(conn, task['creator_id'], 'task.failed', task['id'], {'reason': message})

    def model(self, default, setting='model'):
        with self.connection() as conn:
            row = conn.execute('SELECT value FROM settings WHERE key=?', (setting,)).fetchone()
            return row['value'] if row else default

    def set_model(self, model, actor, setting='model'):
        with self.connection(True) as conn:
            conn.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (setting, model))
            self.audit(conn, actor, 'model.changed', details={'model': model})

    def result(self, task_id, user):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise PortalError('Report not found.', 404)
            self.member(conn, row['conversation_id'], user)
            if row['status'] != 'completed' or not row['result']:
                raise PortalError('No completed sales report is available.', 404)
            return json.loads(row['result'])

    def latest_report(self, task):
        with self.connection() as conn:
            self.member(conn, task['conversation_id'], task['creator_id'])
            row = conn.execute('''SELECT result FROM tasks WHERE conversation_id=?
                AND message_seq<? AND status='completed' AND result IS NOT NULL
                ORDER BY message_seq DESC LIMIT 1''', (task['conversation_id'], task['message_seq'])).fetchone()
            return json.loads(row['result']) if row else None
