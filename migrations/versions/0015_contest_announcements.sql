-- P6-10 contest announcements.

BEGIN;

CREATE TABLE IF NOT EXISTS contest_announcements (
    id TEXT PRIMARY KEY,
    contest_id TEXT NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_by_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contest_announcements_contest_created
ON contest_announcements (contest_id, created_at DESC);

INSERT INTO schema_migrations (version, name)
VALUES ('0015', 'contest_announcements')
ON CONFLICT (version) DO NOTHING;

COMMIT;
