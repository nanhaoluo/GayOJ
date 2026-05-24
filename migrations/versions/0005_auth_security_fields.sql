-- gayoj P2-03 authentication security fields.
-- Adds account lockout state and default password policy settings.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_attempts >= 0);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_locked_until
    ON users (locked_until)
    WHERE locked_until IS NOT NULL;

INSERT INTO system_config (key, value)
VALUES
    ('password_min_length', '6'::jsonb),
    ('password_require_letter', 'true'::jsonb),
    ('password_require_digit', 'true'::jsonb),
    ('login_max_failed_attempts', '5'::jsonb),
    ('login_lockout_minutes', '15'::jsonb)
ON CONFLICT (key) DO NOTHING;

INSERT INTO schema_migrations (version, name)
VALUES ('0005', 'auth_security_fields')
ON CONFLICT (version) DO NOTHING;

COMMIT;

