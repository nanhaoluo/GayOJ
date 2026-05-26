-- P6-10 contest access control.

BEGIN;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS access_mode TEXT NOT NULL DEFAULT 'open'
        CHECK (access_mode IN ('open', 'password', 'invite', 'team', 'manual'));

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS access_code_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS team_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS participant_user_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS access_unlocked_user_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE contests
SET access_mode = CASE WHEN visibility = 'public' THEN 'open' ELSE 'manual' END
WHERE access_mode IS NULL
   OR access_mode NOT IN ('open', 'password', 'invite', 'team', 'manual');

CREATE INDEX IF NOT EXISTS idx_contests_access_mode
ON contests (visibility, access_mode, start_at, end_at);

INSERT INTO schema_migrations (version, name)
VALUES ('0017', 'contest_access_control')
ON CONFLICT (version) DO NOTHING;

COMMIT;
