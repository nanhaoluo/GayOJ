-- P8-02 solution categories, likes, and bookmarks.

BEGIN;

ALTER TABLE discussions
    ADD COLUMN IF NOT EXISTS solution_category TEXT
        CHECK (solution_category IN ('general', 'tutorial', 'analysis', 'official', 'trick'));

ALTER TABLE discussions
    ADD COLUMN IF NOT EXISTS liked_by JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE discussions
    ADD COLUMN IF NOT EXISTS bookmarked_by JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE discussions
SET solution_category = 'general'
WHERE discussion_type = 'solution'
  AND solution_category IS NULL;

CREATE INDEX IF NOT EXISTS idx_discussions_solution_category
ON discussions (discussion_type, solution_category, updated_at DESC);

INSERT INTO schema_migrations (version, name)
VALUES ('0016', 'solution_reactions')
ON CONFLICT (version) DO NOTHING;

COMMIT;
