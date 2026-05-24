from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "versions"
RUNNER = ROOT / "scripts" / "db-migrate.ps1"
IMPORT_SCRIPT = ROOT / "scripts" / "export-dev-db-sql.py"
STORE = ROOT / "apps" / "api" / "app" / "store.py"

EXPECTED_TABLES = [
    "schema_migrations",
    "users",
    "problems",
    "problem_judge_config",
    "problem_test_data",
    "problem_versions",
    "contests",
    "submissions",
    "judge_queue_jobs",
    "clarifications",
    "judge_nodes",
    "compiler_configs",
    "audit_logs",
    "problem_sets",
    "teams",
    "assignments",
    "discussions",
    "notifications",
    "system_config",
    "tags",
    "problem_tags",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
]

EXPECTED_VIEWS = [
    "role_permission_matrix",
]

EXPECTED_PERMISSIONS = [
    "problem:create",
    "problem:edit:own",
    "problem:edit:all",
    "tag:manage",
    "problem_set:create",
    "submission:read:own",
    "submission:read:all",
    "contest:manage",
    "analytics:read",
    "submission:override",
    "judge:monitor",
    "user:ban",
    "user:role:update",
    "audit:read",
    "rbac:read",
    "system:config",
]

EXPECTED_INDEXES = [
    "idx_audit_logs_created",
    "idx_audit_logs_actor_created",
    "idx_audit_logs_action_created",
    "idx_audit_logs_resource_created",
    "idx_problem_versions_problem_version",
    "idx_problem_versions_saved_at",
    "idx_problem_test_data_uploaded_at",
    "idx_problem_test_data_sha256",
    "idx_tags_parent_sort",
    "idx_problem_tags_tag_problem",
    "idx_judge_queue_jobs_status_priority",
    "idx_judge_queue_jobs_submission",
]

DANGEROUS_PATTERNS = [
    r"\bdrop\s+database\b",
    r"\bdrop\s+schema\b",
    r"\btruncate\b",
    r"\bcopy\b.+\bprogram\b",
    r"\\!",
]

DANGEROUS_IMPORT_PATTERNS = [
    r"\bsubprocess\b",
    r"\bos\.system\b",
    r"\bpopen\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
]


def fail(message: str) -> None:
    print(f"migration check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_sql_files() -> list[Path]:
    if not MIGRATIONS.exists():
        fail("migrations/versions is missing")
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        fail("no SQL migration files found")
    for file in files:
        if not re.fullmatch(r"\d{4}_[a-z0-9_]+\.sql", file.name):
            fail(f"migration file name must be versioned: {file.name}")
    return files


def table_block(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"create\s+table\s+if\s+not\s+exists\s+{re.escape(table)}\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    return match.group(1) if match else ""


def main() -> int:
    files = read_sql_files()
    versions = [file.name.split("_", 1)[0] for file in files]
    duplicate_versions = sorted({version for version in versions if versions.count(version) > 1})
    if duplicate_versions:
        fail(f"duplicate migration version(s): {', '.join(duplicate_versions)}")
    combined = "\n".join(file.read_text(encoding="utf-8") for file in files)
    normalized = combined.lower()

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE | re.DOTALL):
            fail(f"dangerous SQL pattern is not allowed: {pattern}")

    for table in EXPECTED_TABLES:
        if not re.search(rf"create\s+table\s+if\s+not\s+exists\s+{table}\b", normalized):
            fail(f"expected table is missing: {table}")

    for view in EXPECTED_VIEWS:
        if not re.search(rf"create\s+or\s+replace\s+view\s+{view}\b", normalized):
            fail(f"expected view is missing: {view}")

    problems_block = table_block(combined, "problems").lower()
    if not problems_block:
        fail("problems table block could not be parsed")
    if "judge_config" in problems_block:
        fail("judge_config must not be stored on the public problems table")

    judge_config_block = table_block(combined, "problem_judge_config").lower()
    if "config jsonb" not in judge_config_block:
        fail("problem_judge_config must store config as JSONB")

    tags_block = table_block(combined, "tags").lower()
    problem_tags_block = table_block(combined, "problem_tags").lower()
    if "parent_id text references tags(id)" not in tags_block:
        fail("tags must support parent_id hierarchy")
    if "problem_id text not null references problems(id)" not in problem_tags_block:
        fail("problem_tags must link problems to tags")

    problem_versions_block = table_block(combined, "problem_versions").lower()
    if "snapshot jsonb" not in problem_versions_block:
        fail("problem_versions must store snapshots as JSONB")
    if "unique (problem_id, version)" not in problem_versions_block:
        fail("problem_versions must keep per-problem version numbers unique")
    problem_test_data_block = table_block(combined, "problem_test_data").lower()
    if "object_key text not null" not in problem_test_data_block:
        fail("problem_test_data must keep an object storage key")
    if "case_names jsonb" not in problem_test_data_block:
        fail("problem_test_data must store case names as JSONB")

    compiler_config_block = table_block(combined, "compiler_configs").lower()
    for token in ["code text primary key", "version text not null", "compile_command jsonb", "run_command jsonb"]:
        if token not in compiler_config_block:
            fail(f"compiler_configs table must include {token}")
    for language in ["'c'", "'cpp'", "'java'", "'python'"]:
        if language not in normalized:
            fail(f"P4-04 compiler config migration must seed language {language}")

    if "insert into schema_migrations" not in normalized:
        fail("migrations must record their version in schema_migrations")
    if "::jsonb" not in normalized:
        fail("schema must use JSONB for typed flexible fields")
    if "source_code text" not in normalized:
        fail("submissions table must preserve submitted code as data")
    judge_queue_block = table_block(combined, "judge_queue_jobs").lower()
    if not judge_queue_block:
        fail("judge_queue_jobs table block could not be parsed")
    if "source_code" in judge_queue_block:
        fail("judge_queue_jobs must store source_ref instead of copied source_code")
    for token in ["submission_id", "source_ref", "source_sha256", "limits jsonb", "testdata_ref", "backend"]:
        if token not in judge_queue_block:
            fail(f"judge_queue_jobs table must include {token}")

    for permission in EXPECTED_PERMISSIONS:
        if f"'{permission}'" not in normalized:
            fail(f"expected RBAC permission is missing: {permission}")
    for index in EXPECTED_INDEXES:
        if not re.search(rf"create\s+index\s+if\s+not\s+exists\s+{index}\b", normalized):
            fail(f"expected audit log index is missing: {index}")
    for table in ["roles", "permissions", "role_permissions", "user_roles"]:
        block = table_block(combined, table).lower()
        if not block:
            fail(f"{table} table block could not be parsed")
    if "insert into user_roles" not in normalized or "select id, role" not in normalized:
        fail("RBAC migration must backfill user_roles from existing users.role")

    runner = RUNNER.read_text(encoding="utf-8")
    if "GAYOJ_DATABASE_URL" not in runner or "psql" not in runner:
        fail("db-migrate.ps1 must use GAYOJ_DATABASE_URL and psql")

    if not IMPORT_SCRIPT.exists():
        fail("P1-04 JSON import/export script is missing")
    import_source = IMPORT_SCRIPT.read_text(encoding="utf-8")
    import_normalized = import_source.lower()
    for token in [
        "dev-db.json",
        "problem_judge_config",
        "problem_test_data",
        "tags",
        "problem_versions",
        "judge_queue_jobs",
        "submissions",
        "source_code",
        "user_roles",
        "problem_tags",
        "compiler_configs",
    ]:
        if token not in import_normalized:
            fail(f"P1-04 import script must mention {token}")
    for pattern in DANGEROUS_IMPORT_PATTERNS:
        if re.search(pattern, import_source, re.IGNORECASE):
            fail(f"P1-04 import script must not execute submission code: {pattern}")

    store_source = STORE.read_text(encoding="utf-8")
    for token in ["problem_judge_config", "get_problem_judge_config", "set_problem_judge_config"]:
        if token not in store_source:
            fail(f"P1-05 JSON store must isolate objective judge config via {token}")
    for token in ["problem_test_data", "get_problem_test_data", "set_problem_test_data"]:
        if token not in store_source:
            fail(f"P3-04 JSON store must preserve test-data metadata via {token}")
    for token in ["list_tags", "add_tag", "update_tag", "delete_tag"]:
        if token not in store_source:
            fail(f"P3-03 JSON store must support tag hierarchy via {token}")
    for token in ["judge_queue_jobs", "list_judge_queue_jobs", "add_judge_queue_job", "source_ref"]:
        if token not in store_source:
            fail(f"P4-01 JSON store must support judge queue jobs via {token}")
    for token in ["compiler_configs", "list_compiler_configs", "update_compiler_config"]:
        if token not in store_source:
            fail(f"P4-04 JSON store must manage compiler configs via {token}")
    if "pop(\"judge_config\"" not in store_source and "pop('judge_config'" not in store_source:
        fail("P1-05 JSON store must migrate embedded judge_config out of public problem rows")
    for token in ["actor_id", "created_from", "created_to", "limit", "offset"]:
        if token not in store_source:
            fail(f"P1-06 audit log store query must support {token}")

    print(f"migration check passed: {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
