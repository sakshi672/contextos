CREATE TABLE memory_relationships (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    from_memory_id uuid NOT NULL,
    to_memory_id uuid NOT NULL,
    relation_type text NOT NULL CHECK (relation_type IN ('related', 'supports', 'contradicts', 'inspired_by', 'references')),
    explanation text NOT NULL CHECK (char_length(explanation) BETWEEN 1 AND 2000),
    provenance text NOT NULL DEFAULT 'manual' CHECK (provenance = 'manual'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_memory_id <> to_memory_id),
    FOREIGN KEY (from_memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (to_memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_relationships_from ON memory_relationships (account_id, from_memory_id);
CREATE INDEX memory_relationships_to ON memory_relationships (account_id, to_memory_id);

CREATE TABLE memory_annotations (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    content_id uuid,
    location_kind text NOT NULL CHECK (location_kind IN ('note', 'content')),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    start_offset integer NOT NULL CHECK (start_offset >= 0),
    end_offset integer NOT NULL CHECK (end_offset > start_offset),
    quote text NOT NULL CHECK (char_length(quote) BETWEEN 1 AND 2000),
    page_number integer CHECK (page_number > 0),
    note text NOT NULL DEFAULT '' CHECK (char_length(note) <= 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((location_kind = 'note' AND content_id IS NULL AND page_number IS NULL) OR
           (location_kind = 'content' AND content_id IS NOT NULL)),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories (id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (content_id, memory_id, account_id)
        REFERENCES memory_contents (id, memory_id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_annotations_owned ON memory_annotations (account_id, memory_id, created_at);
