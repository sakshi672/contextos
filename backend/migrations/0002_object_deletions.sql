-- Keep cleanup work after the owning memory and its assets are removed.
CREATE TABLE object_deletions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL,
    object_key text NOT NULL UNIQUE,
    attempt_count integer NOT NULL DEFAULT 0,
    next_retry_at timestamptz NOT NULL DEFAULT now(),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX object_deletions_due ON object_deletions (next_retry_at, created_at);
