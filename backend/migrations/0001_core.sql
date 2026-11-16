-- First hosted schema. IDs are supplied by the application as UUIDs.
CREATE TABLE accounts (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    password_hash text NOT NULL,
    email_verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounts_email_normalized CHECK (email = lower(btrim(email)))
);
CREATE UNIQUE INDEX accounts_email_unique ON accounts (email);

CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    csrf_hash bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX sessions_account_active ON sessions (account_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE recovery_tokens (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE memories (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('note', 'link', 'web_page', 'pdf', 'document', 'image', 'snippet')),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 240),
    source_uri text,
    source_domain text,
    captured_at timestamptz NOT NULL,
    published_at timestamptz,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'partial', 'failed', 'deletion_pending')),
    user_note text NOT NULL DEFAULT '' CHECK (char_length(user_note) <= 20000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search_document tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, coalesce(user_note, '')), 'B')
    ) STORED,
    UNIQUE (id, account_id),
    CONSTRAINT memories_source_uri_length CHECK (source_uri IS NULL OR char_length(source_uri) <= 2048)
);
CREATE INDEX memories_account_captured ON memories (account_id, captured_at DESC, id);
CREATE INDEX memories_account_status ON memories (account_id, status);
CREATE INDEX memories_search_document ON memories USING gin (search_document);

CREATE TABLE memory_assets (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('original', 'screenshot')),
    object_key text NOT NULL UNIQUE,
    mime_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    source_filename text,
    storage_state text NOT NULL DEFAULT 'stored' CHECK (storage_state IN ('pending', 'stored', 'deletion_pending', 'deleted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_assets_owned ON memory_assets (account_id, memory_id);

CREATE TABLE memory_contents (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    provenance text NOT NULL CHECK (provenance IN ('source', 'user', 'extracted', 'generated')),
    body text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    processor_version text,
    status text NOT NULL CHECK (status IN ('pending', 'ready', 'partial', 'failed')),
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (memory_id, provenance, version),
    UNIQUE (id, memory_id, account_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX memory_contents_one_active ON memory_contents (memory_id, provenance) WHERE is_active;
CREATE INDEX memory_contents_owned ON memory_contents (account_id, memory_id);

CREATE TABLE content_passages (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    content_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    body text NOT NULL,
    page_number integer CHECK (page_number > 0),
    section_label text,
    start_offset integer CHECK (start_offset >= 0),
    end_offset integer CHECK (end_offset >= start_offset),
    UNIQUE (content_id, ordinal),
    FOREIGN KEY (content_id, memory_id, account_id)
        REFERENCES memory_contents (id, memory_id, account_id) ON DELETE CASCADE
);
CREATE INDEX content_passages_owned ON content_passages (account_id, memory_id);

CREATE TABLE extraction_jobs (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_until timestamptz,
    next_retry_at timestamptz NOT NULL DEFAULT now(),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE
);
CREATE INDEX extraction_jobs_claimable ON extraction_jobs (next_retry_at, created_at)
    WHERE status IN ('pending', 'processing');
