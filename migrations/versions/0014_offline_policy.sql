-- P5-07 objective offline policy controls.

BEGIN;

ALTER TABLE problems
ADD COLUMN IF NOT EXISTS offline_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE problems
ADD COLUMN IF NOT EXISTS offline_policy JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE problem_sets
ADD COLUMN IF NOT EXISTS offline_enabled BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE problem_sets
ADD COLUMN IF NOT EXISTS offline_policy JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_problems_offline_enabled
ON problems (offline_enabled, problem_type, visible);

CREATE INDEX IF NOT EXISTS idx_problem_sets_offline_enabled
ON problem_sets (offline_enabled, visibility);

INSERT INTO schema_migrations (version, name)
VALUES ('0014', 'offline_policy')
ON CONFLICT (version) DO NOTHING;

COMMIT;
