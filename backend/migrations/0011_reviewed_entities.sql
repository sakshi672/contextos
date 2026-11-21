ALTER TABLE ai_suggestions DROP CONSTRAINT ai_suggestions_kind_check;
ALTER TABLE ai_suggestions ADD CONSTRAINT ai_suggestions_kind_check
    CHECK (kind IN ('related', 'relationship', 'project', 'tag', 'collection', 'entity'));
ALTER TABLE ai_suggestions ADD COLUMN entity_type text
    CHECK (entity_type IN ('person', 'organization', 'place', 'product', 'concept'));
ALTER TABLE ai_suggestions ADD COLUMN source_refs jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE entities (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    entity_type text NOT NULL CHECK (entity_type IN ('person', 'organization', 'place', 'product', 'concept')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, account_id)
);
CREATE UNIQUE INDEX entities_account_name_type ON entities(account_id, lower(name), entity_type);

CREATE TABLE memory_entities (
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    memory_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    evidence text NOT NULL CHECK (char_length(evidence) BETWEEN 1 AND 1000),
    provenance text NOT NULL CHECK (provenance IN ('reviewed_ai')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (memory_id, entity_id),
    FOREIGN KEY (memory_id, account_id) REFERENCES memories(id, account_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id, account_id) REFERENCES entities(id, account_id) ON DELETE CASCADE
);
CREATE INDEX memory_entities_owned ON memory_entities(account_id, memory_id);

