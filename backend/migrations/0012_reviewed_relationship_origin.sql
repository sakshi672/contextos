ALTER TABLE memory_relationships DROP CONSTRAINT memory_relationships_provenance_check;
ALTER TABLE memory_relationships ADD CONSTRAINT memory_relationships_provenance_check
    CHECK (provenance IN ('manual', 'reviewed_ai'));
