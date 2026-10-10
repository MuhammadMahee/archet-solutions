-- Memory deliberately has no chat foreign key: removing chat history does not erase notes.
SET LOCAL search_path TO archet_workforce, pg_catalog;
CREATE TABLE IF NOT EXISTS workforce_memories (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, scope TEXT NOT NULL,
 topic TEXT NOT NULL, content TEXT NOT NULL, audience TEXT NOT NULL,
 source_chat TEXT NOT NULL, source_seq BIGINT NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS workforce_memories_owner ON workforce_memories(owner_id,scope);
CREATE TABLE IF NOT EXISTS workforce_memory_settings (
 user_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0);
REVOKE ALL ON workforce_memories FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON workforce_memory_settings FROM PUBLIC, anon, authenticated, service_role;
