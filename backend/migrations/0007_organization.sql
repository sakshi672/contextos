CREATE TABLE collections (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, account_id)
);
CREATE UNIQUE INDEX collections_account_name ON collections (account_id, lower(name));

CREATE TABLE collection_memories (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    collection_id uuid NOT NULL,
    PRIMARY KEY (memory_id, collection_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (collection_id, account_id) REFERENCES collections(id, account_id) ON DELETE CASCADE
);
CREATE INDEX collection_memories_owned ON collection_memories (account_id, collection_id);

CREATE TABLE tags (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, account_id)
);
CREATE UNIQUE INDEX tags_account_name ON tags (account_id, lower(name));

CREATE TABLE memory_tags (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    PRIMARY KEY (memory_id, tag_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id, account_id) REFERENCES tags(id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_tags_owned ON memory_tags (account_id, tag_id);
