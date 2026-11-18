CREATE TABLE extension_pairings (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    code_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX extension_pairings_active ON extension_pairings (account_id, expires_at) WHERE used_at IS NULL;

CREATE TABLE extension_credentials (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);
CREATE INDEX extension_credentials_active ON extension_credentials (account_id) WHERE revoked_at IS NULL;

CREATE TABLE capture_requests (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    request_key text NOT NULL,
    request_hash text NOT NULL,
    memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, request_key)
);

CREATE TABLE projects (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, account_id)
);
CREATE UNIQUE INDEX projects_account_name ON projects (account_id, lower(name));

CREATE TABLE memory_projects (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    project_id uuid NOT NULL,
    PRIMARY KEY (memory_id, project_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, account_id) REFERENCES projects(id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_projects_owned ON memory_projects (account_id, project_id);

CREATE INDEX memories_capture_url ON memories (account_id, source_uri, captured_at DESC)
    WHERE kind = 'web_page';
