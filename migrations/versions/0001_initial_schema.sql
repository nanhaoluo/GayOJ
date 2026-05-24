-- gayoj P1-02 initial PostgreSQL schema.
-- This file is safe to re-run against an empty or already initialized database.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'coach', 'judge', 'admin')),
    school TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    rating INTEGER NOT NULL DEFAULT 1500,
    solved INTEGER NOT NULL DEFAULT 0,
    disabled BOOLEAN NOT NULL DEFAULT false,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    problem_type TEXT NOT NULL CHECK (problem_type IN ('code', 'blank', 'single_choice', 'multiple_choice')),
    difficulty TEXT NOT NULL DEFAULT 'basic',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    statement TEXT NOT NULL,
    input_format TEXT NOT NULL DEFAULT '',
    output_format TEXT NOT NULL DEFAULT '',
    samples JSONB NOT NULL DEFAULT '[]'::jsonb,
    options JSONB NOT NULL DEFAULT '[]'::jsonb,
    blanks JSONB NOT NULL DEFAULT '[]'::jsonb,
    time_limit_ms INTEGER,
    memory_limit_mb INTEGER,
    author_id TEXT NOT NULL REFERENCES users(id),
    visible BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS problem_judge_config (
    problem_id TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    rule TEXT NOT NULL CHECK (rule IN ('ACM', 'OI', 'IOI', 'CF')),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    problem_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'running', 'ended')),
    visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_at > start_at)
);

CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    problem_id TEXT NOT NULL REFERENCES problems(id),
    problem_title TEXT NOT NULL,
    problem_type TEXT NOT NULL CHECK (problem_type IN ('code', 'blank', 'single_choice', 'multiple_choice')),
    contest_id TEXT REFERENCES contests(id),
    language TEXT,
    source_code TEXT,
    answers JSONB,
    status TEXT NOT NULL CHECK (
        status IN (
            'queued',
            'judging',
            'accepted',
            'wrong_answer',
            'compile_error',
            'runtime_error',
            'manual_override'
        )
    ),
    score INTEGER NOT NULL DEFAULT 0,
    max_score INTEGER NOT NULL DEFAULT 100,
    details JSONB NOT NULL DEFAULT '[]'::jsonb,
    message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    judged_at TIMESTAMPTZ,
    CHECK (score >= 0),
    CHECK (max_score >= 0),
    CHECK (score <= max_score)
);

CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY,
    contest_id TEXT NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    question TEXT NOT NULL,
    answer TEXT,
    public BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS judge_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('online', 'offline', 'draining')),
    languages JSONB NOT NULL DEFAULT '[]'::jsonb,
    queue_depth INTEGER NOT NULL DEFAULT 0,
    load DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (queue_depth >= 0),
    CHECK (load >= 0)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    actor_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS problem_sets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    set_type TEXT NOT NULL DEFAULT 'set' CHECK (set_type IN ('set', 'exam', 'assignment')),
    visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'private')),
    problem_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner_id TEXT NOT NULL REFERENCES users(id),
    duration_minutes INTEGER,
    due_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (duration_minutes IS NULL OR duration_minutes > 0)
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    invite_code TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id),
    member_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    problem_set_id TEXT NOT NULL REFERENCES problem_sets(id),
    team_id TEXT REFERENCES teams(id),
    due_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS discussions (
    id TEXT PRIMARY KEY,
    discussion_type TEXT NOT NULL DEFAULT 'general' CHECK (discussion_type IN ('general', 'problem', 'contest', 'solution')),
    target_id TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author_id TEXT NOT NULL REFERENCES users(id),
    author_name TEXT NOT NULL,
    pinned BOOLEAN NOT NULL DEFAULT false,
    likes INTEGER NOT NULL DEFAULT 0,
    replies JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (likes >= 0)
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    notification_type TEXT NOT NULL DEFAULT 'system' CHECK (notification_type IN ('judge', 'contest', 'reply', 'system', 'assignment')),
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_problems_type_visible ON problems (problem_type, visible);
CREATE INDEX IF NOT EXISTS idx_submissions_user_created ON submissions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_problem_created ON submissions (problem_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_status_created ON submissions (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_contests_status_time ON contests (status, start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read_created ON notifications (user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC);

INSERT INTO schema_migrations (version, name)
VALUES ('0001', 'initial_schema')
ON CONFLICT (version) DO NOTHING;

COMMIT;

