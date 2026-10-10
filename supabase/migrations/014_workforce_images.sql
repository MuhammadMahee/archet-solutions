CREATE TABLE archet_workforce.message_images (
 id TEXT PRIMARY KEY, message_seq BIGINT NOT NULL REFERENCES archet_workforce.messages(seq),
 name TEXT NOT NULL, mime TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 size INTEGER NOT NULL, data TEXT NOT NULL, source TEXT NOT NULL, analysis TEXT NOT NULL DEFAULT '');
CREATE INDEX images_message ON archet_workforce.message_images(message_seq);
REVOKE ALL ON archet_workforce.message_images FROM PUBLIC, anon, authenticated, service_role;
