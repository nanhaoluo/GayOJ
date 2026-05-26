ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS participation_mode TEXT NOT NULL DEFAULT 'open'
        CHECK (participation_mode IN ('open', 'individual', 'team')),
    ADD COLUMN IF NOT EXISTS registered_user_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS registered_team_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS roster_locked BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS roster_locked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS roster_locked_by TEXT REFERENCES users(id);

CREATE INDEX IF NOT EXISTS idx_contests_participation_mode
    ON contests (participation_mode);

CREATE INDEX IF NOT EXISTS idx_contests_roster_locked
    ON contests (roster_locked);

INSERT INTO schema_migrations (version, name)
VALUES ('0017', 'contest_roster_fields')
ON CONFLICT (version) DO NOTHING;
