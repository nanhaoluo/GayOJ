-- gayoj P2-01 runtime permission-code enforcement grants.

BEGIN;

INSERT INTO permissions (code, description, category)
VALUES
    ('problem_set:create', 'Create problem sets and exams', 'problem_set'),
    ('problem_set:edit:own', 'Edit owned problem sets and exams', 'problem_set'),
    ('problem_set:edit:all', 'Edit all problem sets and exams', 'problem_set'),
    ('submission:read:own', 'Read own submissions', 'submission'),
    ('submission:read:all', 'Read all submissions', 'submission'),
    ('clarification:create', 'Ask contest clarifications', 'contest'),
    ('clarification:read:all', 'Read all contest clarifications', 'contest'),
    ('assignment:manage', 'Create and manage assignments', 'team'),
    ('analytics:read', 'Read coach analytics', 'analytics'),
    ('discussion:write', 'Create discussion posts and replies', 'discussion'),
    ('notification:read', 'Read own notifications', 'notification'),
    ('judge:monitor', 'Read judge queue monitor', 'judge'),
    ('audit:read', 'Read audit logs', 'system'),
    ('rbac:read', 'Read RBAC permission matrix', 'system')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description,
    category = EXCLUDED.category;

INSERT INTO role_permissions (role_code, permission_code)
VALUES
    ('student', 'submission:read:own'),
    ('student', 'clarification:create'),
    ('student', 'discussion:write'),
    ('student', 'notification:read'),
    ('coach', 'submission:read:own'),
    ('coach', 'submission:read:all'),
    ('coach', 'clarification:create'),
    ('coach', 'problem_set:create'),
    ('coach', 'problem_set:edit:own'),
    ('coach', 'assignment:manage'),
    ('coach', 'analytics:read'),
    ('coach', 'discussion:write'),
    ('coach', 'notification:read'),
    ('judge', 'submission:read:own'),
    ('judge', 'submission:read:all'),
    ('judge', 'clarification:create'),
    ('judge', 'clarification:read:all'),
    ('judge', 'problem_set:create'),
    ('judge', 'problem_set:edit:own'),
    ('judge', 'discussion:write'),
    ('judge', 'notification:read'),
    ('judge', 'judge:monitor'),
    ('admin', 'problem_set:create'),
    ('admin', 'problem_set:edit:own'),
    ('admin', 'problem_set:edit:all'),
    ('admin', 'submission:read:own'),
    ('admin', 'submission:read:all'),
    ('admin', 'clarification:create'),
    ('admin', 'clarification:read:all'),
    ('admin', 'assignment:manage'),
    ('admin', 'analytics:read'),
    ('admin', 'discussion:write'),
    ('admin', 'notification:read'),
    ('admin', 'judge:monitor'),
    ('admin', 'audit:read'),
    ('admin', 'rbac:read')
ON CONFLICT (role_code, permission_code) DO NOTHING;

INSERT INTO schema_migrations (version, name)
VALUES ('0004', 'permission_code_enforcement')
ON CONFLICT (version) DO NOTHING;

COMMIT;

