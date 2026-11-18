ALTER TABLE memories ADD COLUMN search_metadata tsvector GENERATED ALWAYS AS (
    to_tsvector('english'::regconfig,
        coalesce(source_uri, '') || ' ' || replace(coalesce(source_domain, ''), '.', ' ') || ' ' ||
        coalesce(source_author, ''))
) STORED;
CREATE INDEX memories_search_metadata ON memories USING gin (search_metadata);

ALTER TABLE memory_contents ADD COLUMN search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('english'::regconfig, body)
) STORED;
CREATE INDEX memory_contents_search_active ON memory_contents USING gin (search_document)
    WHERE is_active AND provenance IN ('user', 'source', 'extracted');

ALTER TABLE content_passages ADD COLUMN search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('english'::regconfig, body)
) STORED;
CREATE INDEX content_passages_search_document ON content_passages USING gin (search_document);
