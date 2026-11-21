CREATE TABLE ai_artifact_sources (
    artifact_id uuid NOT NULL REFERENCES ai_artifacts(id) ON DELETE CASCADE,
    account_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    PRIMARY KEY (artifact_id, memory_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE
);
CREATE INDEX ai_artifact_sources_memory ON ai_artifact_sources(account_id, memory_id);

CREATE OR REPLACE FUNCTION invalidate_memory_ai() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; target_id uuid;
BEGIN
    owner_id := NEW.account_id;
    target_id := NEW.id;
    IF TG_TABLE_NAME = 'memory_contents' THEN target_id := NEW.memory_id; END IF;
    DELETE FROM ai_artifacts a USING ai_artifact_sources s
        WHERE a.id = s.artifact_id AND s.account_id = owner_id AND s.memory_id = target_id;
    DELETE FROM ai_suggestions WHERE account_id = owner_id
        AND (memory_id = target_id OR related_memory_id = target_id);
    DELETE FROM memory_embeddings WHERE account_id = owner_id AND memory_id = target_id;
    RETURN NEW;
END $$;
CREATE TRIGGER ai_memory_invalidate AFTER UPDATE OF title, user_note ON memories
    FOR EACH ROW WHEN (OLD.title IS DISTINCT FROM NEW.title OR OLD.user_note IS DISTINCT FROM NEW.user_note)
    EXECUTE FUNCTION invalidate_memory_ai();
CREATE TRIGGER ai_content_invalidate AFTER INSERT OR UPDATE OF is_active ON memory_contents
    FOR EACH ROW EXECUTE FUNCTION invalidate_memory_ai();

CREATE OR REPLACE FUNCTION delete_memory_ai_artifacts() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM ai_artifacts a USING ai_artifact_sources s
        WHERE a.id = s.artifact_id AND s.account_id = OLD.account_id AND s.memory_id = OLD.id;
    RETURN OLD;
END $$;
CREATE TRIGGER ai_memory_delete BEFORE DELETE ON memories
    FOR EACH ROW EXECUTE FUNCTION delete_memory_ai_artifacts();
