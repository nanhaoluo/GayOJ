-- gayoj P3-05 problem version history.

BEGIN;

CREATE TABLE IF NOT EXISTS problem_versions (
    id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    saved_by TEXT REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('update', 'delete', 'restore')),
    snapshot JSONB NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (problem_id, version)
);

CREATE INDEX IF NOT EXISTS idx_problem_versions_problem_version
ON problem_versions (problem_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_problem_versions_saved_at
ON problem_versions (saved_at DESC);

INSERT INTO schema_migrations (version, name)
VALUES ('0008', 'problem_versions')
ON CONFLICT (version) DO NOTHING;

COMMIT;

