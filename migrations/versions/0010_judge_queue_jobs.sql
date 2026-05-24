-- gayoj P4-01 judge queue abstraction.

BEGIN;

CREATE TABLE IF NOT EXISTS judge_queue_jobs (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL REFERENCES problems(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    contest_id TEXT REFERENCES contests(id),
    language TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    limits JSONB NOT NULL DEFAULT '{}'::jsonb,
    testdata_ref TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'leased', 'completed', 'failed')),
    backend TEXT NOT NULL DEFAULT 'json' CHECK (backend IN ('json', 'redis', 'kafka')),
    assigned_node_id TEXT REFERENCES judge_nodes(id) ON DELETE SET NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    leased_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS idx_judge_queue_jobs_status_priority
ON judge_queue_jobs (status, priority DESC, created_at);

CREATE INDEX IF NOT EXISTS idx_judge_queue_jobs_submission
ON judge_queue_jobs (submission_id);

CREATE INDEX IF NOT EXISTS idx_judge_queue_jobs_assigned_node
ON judge_queue_jobs (assigned_node_id, status);

INSERT INTO schema_migrations (version, name)
VALUES ('0010', 'judge_queue_jobs')
ON CONFLICT (version) DO NOTHING;

COMMIT;

