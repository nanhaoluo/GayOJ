-- gayoj P5-05 offline result sync idempotency.

BEGIN;

ALTER TABLE submissions
ADD COLUMN IF NOT EXISTS offline_result_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_offline_result_key
ON submissions (user_id, offline_result_key)
WHERE offline_result_key IS NOT NULL;

INSERT INTO schema_migrations (version, name)
VALUES ('0013', 'offline_result_idempotency')
ON CONFLICT (version) DO NOTHING;

COMMIT;
