ALTER TABLE memories ADD COLUMN capture_method text NOT NULL DEFAULT 'browser'
    CHECK (capture_method IN ('browser', 'manual'));
ALTER TABLE memories ADD COLUMN source_author text;
ALTER TABLE memories ADD COLUMN source_image_uri text;
