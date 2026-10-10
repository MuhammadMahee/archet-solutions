"""Additive schema shared by local chat controls."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_profiles (
 conversation_id TEXT PRIMARY KEY REFERENCES conversations(id), description TEXT NOT NULL DEFAULT '',
 avatar TEXT, original_creator TEXT NOT NULL DEFAULT '', disappearing INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chat_preferences (
 conversation_id TEXT NOT NULL REFERENCES conversations(id), user_id TEXT NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
 muted_until REAL NOT NULL DEFAULT 0, read_seq BIGINT NOT NULL DEFAULT 0, unread INTEGER NOT NULL DEFAULT 0,
 cleared_seq BIGINT NOT NULL DEFAULT 0, theme TEXT NOT NULL DEFAULT 'default', list_name TEXT NOT NULL DEFAULT '',
 member_tag TEXT NOT NULL DEFAULT '', PRIMARY KEY(conversation_id,user_id));
CREATE TABLE IF NOT EXISTS message_details (
 message_seq BIGINT PRIMARY KEY REFERENCES messages(seq), reply_seq BIGINT, forwarded INTEGER NOT NULL DEFAULT 0,
 deleted INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0, expires_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS message_flags (
 message_seq BIGINT NOT NULL REFERENCES messages(seq), user_id TEXT NOT NULL,
 starred INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(message_seq,user_id));
CREATE TABLE IF NOT EXISTS message_reactions (
 message_seq BIGINT NOT NULL REFERENCES messages(seq), user_id TEXT NOT NULL, emoji TEXT NOT NULL,
 PRIMARY KEY(message_seq,user_id));
CREATE TABLE IF NOT EXISTS chat_events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 actor_id TEXT NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_invites (
 token_hash TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
 created_by TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS chat_reports (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id), message_seq BIGINT,
 reporter_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chat_events_chat ON chat_events(conversation_id,seq);
"""
