-- gayoj role boundary update: only student accounts can participate.

BEGIN;

UPDATE roles
SET
    name = CASE code
        WHEN 'student' THEN 'Student'
        WHEN 'coach' THEN 'Coach'
        WHEN 'judge' THEN 'Judge'
        WHEN 'admin' THEN 'Admin + Judge'
        ELSE name
    END,
    description = CASE code
        WHEN 'student' THEN 'Only participant role for contests, submissions, and training'
        WHEN 'coach' THEN 'Manage training content, teams, and assignments without participating'
        WHEN 'judge' THEN 'Monitor contests and override judging outcomes without participating'
        WHEN 'admin' THEN 'Operate the instance with merged judge authority'
        ELSE description
    END,
    updated_at = now()
WHERE code IN ('student', 'coach', 'judge', 'admin');

DELETE FROM role_permissions
WHERE permission_code IN (
    'submission:create',
    'training:offline',
    'contest:join',
    'clarification:create'
)
AND role_code IN ('coach', 'judge', 'admin');

INSERT INTO schema_migrations (version, name)
VALUES ('0012', 'participant_role_boundaries')
ON CONFLICT (version) DO NOTHING;

COMMIT;
