CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE ai_preferences (
    account_id uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    enabled boolean NOT NULL DEFAULT false,
    provider text NOT NULL DEFAULT 'openai' CHECK (provider IN ('openai')),
    monthly_token_limit integer NOT NULL DEFAULT 0 CHECK (monthly_token_limit BETWEEN 0 AND 10000000),
    consented_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT enabled OR (consented_at IS NOT NULL AND monthly_token_limit > 0))
);

CREATE TABLE ai_usage (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    month date NOT NULL,
    reserved_tokens integer NOT NULL DEFAULT 0 CHECK (reserved_tokens >= 0),
    used_tokens integer NOT NULL DEFAULT 0 CHECK (used_tokens >= 0),
    PRIMARY KEY (account_id, month)
);

CREATE TABLE memory_embeddings (
    account_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    model text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    embedding public.vector NOT NULL,
    input_tokens integer NOT NULL CHECK (input_tokens >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, memory_id, model),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_embeddings_account ON memory_embeddings(account_id, model);

CREATE TABLE ai_embedding_jobs (
    account_id uuid NOT NULL,
    memory_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_until timestamptz,
    next_retry_at timestamptz NOT NULL DEFAULT now(),
    error_code text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, memory_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE
);
CREATE INDEX ai_embedding_jobs_due ON ai_embedding_jobs(next_retry_at, updated_at) WHERE status IN ('pending', 'processing');

CREATE OR REPLACE FUNCTION queue_memory_embedding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id uuid; target_id uuid;
BEGIN
    owner_id := NEW.account_id;
    target_id := NEW.id;
    IF TG_TABLE_NAME = 'memory_contents' THEN target_id := NEW.memory_id; END IF;
    IF EXISTS (SELECT 1 FROM ai_preferences WHERE account_id = owner_id AND enabled) THEN
        INSERT INTO ai_embedding_jobs(account_id, memory_id, status, next_retry_at, updated_at)
        VALUES (owner_id, target_id, 'pending', now(), now())
        ON CONFLICT (account_id, memory_id) DO UPDATE SET status = 'pending',
            next_retry_at = now(), updated_at = now(), error_code = NULL;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ai_memory_changed AFTER INSERT OR UPDATE OF title, user_note ON memories
    FOR EACH ROW EXECUTE FUNCTION queue_memory_embedding();
CREATE TRIGGER ai_content_changed AFTER INSERT OR UPDATE OF is_active ON memory_contents
    FOR EACH ROW EXECUTE FUNCTION queue_memory_embedding();

CREATE TABLE ai_artifacts (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    project_id uuid,
    memory_id uuid,
    task text NOT NULL CHECK (task IN ('question', 'summary', 'comparison', 'ideas')),
    cache_key text NOT NULL CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    model text NOT NULL,
    result jsonb NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, cache_key),
    FOREIGN KEY (project_id, account_id) REFERENCES projects(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE
);

CREATE TABLE ai_suggestions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('related', 'relationship', 'project', 'tag', 'collection')),
    memory_id uuid NOT NULL,
    related_memory_id uuid,
    project_id uuid,
    label text,
    evidence text NOT NULL CHECK (char_length(evidence) BETWEEN 1 AND 1000),
    model text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'dismissed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (related_memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, account_id) REFERENCES projects(id, account_id) ON DELETE CASCADE,
    UNIQUE (account_id, kind, memory_id, related_memory_id, project_id, label)
);
