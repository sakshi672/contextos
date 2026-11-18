ALTER TABLE extension_credentials
    ADD COLUMN expires_at timestamptz NOT NULL DEFAULT (now() + interval '90 days');
