-- gayoj P2-02 role-management permission grant.

BEGIN;

INSERT INTO permissions (code, description, category)
VALUES
    ('user:role:update', 'Assign platform roles to users', 'user')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description,
    category = EXCLUDED.category;

INSERT INTO role_permissions (role_code, permission_code)
VALUES
    ('admin', 'user:role:update')
ON CONFLICT (role_code, permission_code) DO NOTHING;

INSERT INTO schema_migrations (version, name)
VALUES ('0006', 'role_management')
ON CONFLICT (version) DO NOTHING;

COMMIT;

