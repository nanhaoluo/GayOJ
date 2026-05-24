-- gayoj P3-04 code problem test-data object metadata.

BEGIN;

CREATE TABLE IF NOT EXISTS problem_test_data (
    problem_id TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,
    storage_backend TEXT NOT NULL DEFAULT 'local',
    bucket TEXT NOT NULL DEFAULT 'gayoj-testdata',
    object_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    archive_format TEXT NOT NULL DEFAULT 'zip' CHECK (archive_format = 'zip'),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0 CHECK (file_count >= 0),
    input_files INTEGER NOT NULL DEFAULT 0 CHECK (input_files >= 0),
    output_files INTEGER NOT NULL DEFAULT 0 CHECK (output_files >= 0),
    case_count INTEGER NOT NULL DEFAULT 0 CHECK (case_count >= 0),
    case_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_by TEXT REFERENCES users(id),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_problem_test_data_uploaded_at
ON problem_test_data (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_problem_test_data_sha256
ON problem_test_data (sha256);

INSERT INTO schema_migrations (version, name)
VALUES ('0009', 'problem_test_data')
ON CONFLICT (version) DO NOTHING;

COMMIT;

