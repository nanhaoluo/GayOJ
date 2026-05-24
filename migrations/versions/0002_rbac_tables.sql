-- gayoj P1-03 RBAC tables and role-permission matrix.
-- This migration keeps the legacy users.role column for JSON compatibility.

BEGIN;

CREATE TABLE IF NOT EXISTS roles (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_system BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permissions (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_code TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_code TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    scope_type TEXT NOT NULL DEFAULT 'global',
    scope_id TEXT NOT NULL DEFAULT '*',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role_code, scope_type, scope_id)
);

INSERT INTO roles (code, name, description)
VALUES
    ('student', 'Student', 'Submit problems and join public training flows'),
    ('coach', 'Coach', 'Manage training content, teams, and assignments'),
    ('judge', 'Judge', 'Monitor contests and override judging outcomes'),
    ('admin', 'Admin', 'Operate the whole gayoj instance')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = now();

INSERT INTO permissions (code, description, category)
VALUES
    ('problem:read', 'Browse public problems', 'problem'),
    ('submission:create', 'Submit code or objective answers', 'submission'),
    ('training:offline', 'Download objective-only offline training packs', 'training'),
    ('contest:join', 'Join public contests', 'contest'),
    ('problem:create', 'Create problems', 'problem'),
    ('problem:edit:own', 'Edit own problems', 'problem'),
    ('problem:edit:all', 'Edit all problems', 'problem'),
    ('contest:manage', 'Create and manage contests', 'contest'),
    ('team:manage', 'Manage teams and assignments', 'team'),
    ('submission:override', 'Manually override submission results', 'submission'),
    ('clarification:reply', 'Reply to contest clarifications', 'contest'),
    ('judge_node:manage', 'Manage judge nodes', 'judge'),
    ('user:read', 'Read user administration lists', 'user'),
    ('user:ban', 'Ban or unban users', 'user'),
    ('user:role:update', 'Assign platform roles to users', 'user'),
    ('system:config', 'Read and update system configuration', 'system'),
    ('backup:manage', 'Run backup and restore operations', 'system')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description,
    category = EXCLUDED.category;

INSERT INTO role_permissions (role_code, permission_code)
VALUES
    ('student', 'problem:read'),
    ('student', 'submission:create'),
    ('student', 'training:offline'),
    ('student', 'contest:join'),
    ('coach', 'problem:read'),
    ('coach', 'submission:create'),
    ('coach', 'training:offline'),
    ('coach', 'contest:join'),
    ('coach', 'problem:create'),
    ('coach', 'problem:edit:own'),
    ('coach', 'contest:manage'),
    ('coach', 'team:manage'),
    ('judge', 'problem:read'),
    ('judge', 'submission:create'),
    ('judge', 'training:offline'),
    ('judge', 'contest:join'),
    ('judge', 'problem:create'),
    ('judge', 'problem:edit:own'),
    ('judge', 'problem:edit:all'),
    ('judge', 'contest:manage'),
    ('judge', 'submission:override'),
    ('judge', 'clarification:reply'),
    ('admin', 'problem:read'),
    ('admin', 'submission:create'),
    ('admin', 'training:offline'),
    ('admin', 'contest:join'),
    ('admin', 'problem:create'),
    ('admin', 'problem:edit:own'),
    ('admin', 'problem:edit:all'),
    ('admin', 'contest:manage'),
    ('admin', 'team:manage'),
    ('admin', 'submission:override'),
    ('admin', 'clarification:reply'),
    ('admin', 'judge_node:manage'),
    ('admin', 'user:read'),
    ('admin', 'user:ban'),
    ('admin', 'user:role:update'),
    ('admin', 'system:config'),
    ('admin', 'backup:manage')
ON CONFLICT (role_code, permission_code) DO NOTHING;

INSERT INTO user_roles (user_id, role_code, scope_type, scope_id)
SELECT id, role, 'global', '*'
FROM users
WHERE role IN ('student', 'coach', 'judge', 'admin')
ON CONFLICT (user_id, role_code, scope_type, scope_id) DO NOTHING;

CREATE OR REPLACE VIEW role_permission_matrix AS
SELECT
    r.code AS role_code,
    r.name AS role_name,
    p.code AS permission_code,
    p.category AS permission_category,
    (rp.role_code IS NOT NULL) AS allowed
FROM roles r
CROSS JOIN permissions p
LEFT JOIN role_permissions rp
    ON rp.role_code = r.code
   AND rp.permission_code = p.code;

CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions (permission_code);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles (role_code);

INSERT INTO schema_migrations (version, name)
VALUES ('0002', 'rbac_tables')
ON CONFLICT (version) DO NOTHING;

COMMIT;

