-- gayoj P4-04 compiler configuration table.

BEGIN;

CREATE TABLE IF NOT EXISTS compiler_configs (
    code TEXT PRIMARY KEY CHECK (code IN ('c', 'cpp', 'java', 'python')),
    display_name TEXT NOT NULL,
    version TEXT NOT NULL,
    source_extension TEXT NOT NULL,
    compile_command JSONB NOT NULL DEFAULT '[]'::jsonb,
    run_command JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO compiler_configs (
    code,
    display_name,
    version,
    source_extension,
    compile_command,
    run_command,
    enabled,
    sort_order
)
VALUES
    (
        'c',
        'C',
        'GCC 14.2 / C17',
        '.c',
        '["gcc","-std=c17","-O2","-Wall","-Wextra","-DONLINE_JUDGE","-static","-Wl,--no-relax","-Wl,--no-pie","-mcmodel=medium","-o","Main","Main.c"]'::jsonb,
        '["./Main"]'::jsonb,
        true,
        10
    ),
    (
        'cpp',
        'C++17',
        'GCC 14.2 / C++17',
        '.cpp',
        '["g++","-std=c++17","-O2","-Wall","-Wextra","-DONLINE_JUDGE","-static","-Wl,--no-relax","-Wl,--no-pie","-mcmodel=medium","-o","Main","Main.cpp"]'::jsonb,
        '["./Main"]'::jsonb,
        true,
        20
    ),
    (
        'java',
        'Java',
        'OpenJDK 21',
        '.java',
        '["javac","-J-Xms1024M","-J-Xmx1024M","-J-Xss64M","-encoding","UTF-8","Main.java"]'::jsonb,
        '["java","-Dfile.encoding=UTF-8","-XX:+UseSerialGC","-Xss64M","-cp",".","Main"]'::jsonb,
        true,
        30
    ),
    (
        'python',
        'Python',
        'Python 3.12',
        '.py',
        '["python3","-m","py_compile","Main.py"]'::jsonb,
        '["python3","Main.py"]'::jsonb,
        true,
        40
    )
ON CONFLICT (code) DO NOTHING;

INSERT INTO schema_migrations (version, name)
VALUES ('0011', 'compiler_configs')
ON CONFLICT (version) DO NOTHING;

COMMIT;

