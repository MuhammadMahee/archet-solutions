CREATE TABLE archet_workforce.conversation_agents (
 conversation_id TEXT NOT NULL REFERENCES archet_workforce.conversations(id),
 agent_id TEXT NOT NULL, added_by TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(conversation_id,agent_id));
CREATE TABLE archet_workforce.message_mentions (
 message_seq BIGINT NOT NULL REFERENCES archet_workforce.messages(seq),
 recipient_id TEXT NOT NULL, PRIMARY KEY(message_seq,recipient_id));
CREATE INDEX mentions_recipient ON archet_workforce.message_mentions(recipient_id,message_seq);
REVOKE ALL ON archet_workforce.conversation_agents, archet_workforce.message_mentions
 FROM PUBLIC, anon, authenticated, service_role;
