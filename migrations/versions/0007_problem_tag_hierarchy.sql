-- gayoj P3-03 problem tag hierarchy and tag-management permission.

BEGIN;

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    parent_id TEXT REFERENCES tags(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS problem_tags (
    problem_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (problem_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_tags_parent_sort ON tags (parent_id, sort_order, name);
CREATE INDEX IF NOT EXISTS idx_problem_tags_tag_problem ON problem_tags (tag_id, problem_id);

INSERT INTO tags (id, name, slug, parent_id, sort_order)
SELECT
    'legacy-' || md5(tag_name.value),
    tag_name.value,
    lower(regexp_replace(tag_name.value, '\s+', '-', 'g')),
    NULL,
    row_number() OVER (ORDER BY tag_name.value)
FROM (
    SELECT DISTINCT tag_value.value
    FROM problems,
         jsonb_array_elements_text(problems.tags) AS tag_value(value)
) AS tag_name
WHERE tag_name.value <> ''
ON CONFLICT (name) DO NOTHING;

INSERT INTO problem_tags (problem_id, tag_id)
SELECT problems.id, tags.id
FROM problems,
     jsonb_array_elements_text(problems.tags) AS tag_name(value)
JOIN tags ON tags.name = tag_name.value
ON CONFLICT (problem_id, tag_id) DO NOTHING;

INSERT INTO permissions (code, description, category)
VALUES
    ('tag:manage', 'Manage problem tags and knowledge hierarchy', 'problem')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description,
    category = EXCLUDED.category;

INSERT INTO role_permissions (role_code, permission_code)
VALUES
    ('coach', 'tag:manage'),
    ('judge', 'tag:manage'),
    ('admin', 'tag:manage')
ON CONFLICT (role_code, permission_code) DO NOTHING;

INSERT INTO schema_migrations (version, name)
VALUES ('0007', 'problem_tag_hierarchy')
ON CONFLICT (version) DO NOTHING;

COMMIT;

