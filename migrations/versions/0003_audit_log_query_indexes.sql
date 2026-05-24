-- gayoj P1-06 audit log query indexes.
-- The audit_logs table already exists from the MVP schema; this migration
-- adds indexes used by the admin query API without changing stored rows.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created
    ON audit_logs (actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created
    ON audit_logs (action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_created
    ON audit_logs (resource, created_at DESC);

INSERT INTO schema_migrations (version, name)
VALUES ('0003', 'audit_log_query_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;

