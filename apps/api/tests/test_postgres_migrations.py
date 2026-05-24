from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "migrations" / "versions" / "0001_initial_schema.sql"
RBAC_MIGRATION = ROOT / "migrations" / "versions" / "0002_rbac_tables.sql"
AUDIT_MIGRATION = ROOT / "migrations" / "versions" / "0003_audit_log_query_indexes.sql"
PERMISSION_MIGRATION = ROOT / "migrations" / "versions" / "0004_permission_code_enforcement.sql"
AUTH_SECURITY_MIGRATION = ROOT / "migrations" / "versions" / "0005_auth_security_fields.sql"
TAG_MIGRATION = ROOT / "migrations" / "versions" / "0007_problem_tag_hierarchy.sql"
PROBLEM_VERSIONS_MIGRATION = ROOT / "migrations" / "versions" / "0008_problem_versions.sql"
PROBLEM_TEST_DATA_MIGRATION = ROOT / "migrations" / "versions" / "0009_problem_test_data.sql"
JUDGE_QUEUE_MIGRATION = ROOT / "migrations" / "versions" / "0010_judge_queue_jobs.sql"
COMPILER_CONFIG_MIGRATION = ROOT / "migrations" / "versions" / "0011_compiler_configs.sql"
CHECK_SCRIPT = ROOT / "scripts" / "check-migrations.py"
RUNNER = ROOT / "scripts" / "db-migrate.ps1"


def read_migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def table_block(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table)}\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    assert match, f"missing table {table}"
    return match.group(1)


def test_initial_postgres_migration_defines_empty_database_schema() -> None:
    sql = read_migration()
    for table in [
        "schema_migrations",
        "users",
        "problems",
        "problem_judge_config",
        "contests",
        "submissions",
        "clarifications",
        "judge_nodes",
        "audit_logs",
        "problem_sets",
        "teams",
        "assignments",
        "discussions",
        "notifications",
        "system_config",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    assert "INSERT INTO schema_migrations" in sql
    assert "0001" in sql


def test_problem_judge_config_is_not_on_public_problem_table() -> None:
    sql = read_migration()
    problems = table_block(sql, "problems").lower()
    judge_config = table_block(sql, "problem_judge_config").lower()

    assert "judge_config" not in problems
    assert "config jsonb" in judge_config
    assert "references problems(id) on delete cascade" in judge_config


def test_migration_runner_uses_postgres_url_and_psql() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    assert "GAYOJ_DATABASE_URL" in source
    assert "psql" in source
    assert "ON_ERROR_STOP=1" in source
    assert "migrations/versions" in source


def test_rbac_migration_defines_role_permission_tables_and_matrix() -> None:
    sql = RBAC_MIGRATION.read_text(encoding="utf-8")

    for table in ["roles", "permissions", "role_permissions", "user_roles"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    assert "CREATE OR REPLACE VIEW role_permission_matrix" in sql
    assert "INSERT INTO schema_migrations" in sql
    assert "0002" in sql
    assert "problem:create" in sql
    assert "submission:override" in sql
    assert "user:ban" in sql
    assert "user:role:update" in sql
    assert "system:config" in sql
    assert "SELECT id, role, 'global', '*'" in sql


def test_audit_log_migration_adds_query_indexes() -> None:
    sql = AUDIT_MIGRATION.read_text(encoding="utf-8")

    for index in [
        "idx_audit_logs_actor_created",
        "idx_audit_logs_action_created",
        "idx_audit_logs_resource_created",
    ]:
        assert f"CREATE INDEX IF NOT EXISTS {index}" in sql

    assert "INSERT INTO schema_migrations" in sql
    assert "0003" in sql


def test_permission_code_migration_extends_runtime_grants() -> None:
    sql = PERMISSION_MIGRATION.read_text(encoding="utf-8")

    for permission in [
        "submission:read:own",
        "submission:read:all",
        "problem_set:create",
        "analytics:read",
        "judge:monitor",
        "audit:read",
        "rbac:read",
    ]:
        assert permission in sql

    assert "ON CONFLICT (code) DO UPDATE" in sql
    assert "ON CONFLICT (role_code, permission_code) DO NOTHING" in sql
    assert "0004" in sql


def test_auth_security_migration_adds_lockout_state_and_defaults() -> None:
    sql = AUTH_SECURITY_MIGRATION.read_text(encoding="utf-8").lower()

    for column in [
        "failed_login_attempts",
        "locked_until",
        "last_login_at",
        "password_changed_at",
    ]:
        assert column in sql

    assert "idx_users_locked_until" in sql
    assert "password_min_length" in sql
    assert "login_max_failed_attempts" in sql
    assert "insert into schema_migrations" in sql
    assert "0005" in sql


def test_tag_hierarchy_migration_adds_tables_backfill_and_permission() -> None:
    sql = TAG_MIGRATION.read_text(encoding="utf-8")

    for table in ["tags", "problem_tags"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    assert "parent_id TEXT REFERENCES tags(id)" in sql
    assert "jsonb_array_elements_text(problems.tags)" in sql
    assert "tag:manage" in sql
    assert "idx_tags_parent_sort" in sql
    assert "idx_problem_tags_tag_problem" in sql
    assert "0007" in sql


def test_problem_versions_migration_adds_snapshot_history_table() -> None:
    sql = PROBLEM_VERSIONS_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists problem_versions" in sql
    assert "problem_id text not null references problems(id) on delete cascade" in sql
    assert "version integer not null" in sql
    assert "snapshot jsonb not null" in sql
    assert "unique (problem_id, version)" in sql
    assert "idx_problem_versions_problem_version" in sql
    assert "idx_problem_versions_saved_at" in sql
    assert "0008" in sql


def test_problem_test_data_migration_adds_object_metadata_table() -> None:
    sql = PROBLEM_TEST_DATA_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists problem_test_data" in sql
    assert "problem_id text primary key references problems(id) on delete cascade" in sql
    assert "storage_backend text not null" in sql
    assert "object_key text not null" in sql
    assert "archive_format text not null default 'zip'" in sql
    assert "case_names jsonb not null default '[]'::jsonb" in sql
    assert "idx_problem_test_data_uploaded_at" in sql
    assert "idx_problem_test_data_sha256" in sql
    assert "0009" in sql


def test_judge_queue_migration_adds_queue_task_table() -> None:
    sql = JUDGE_QUEUE_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists judge_queue_jobs" in sql
    assert "submission_id text not null references submissions(id) on delete cascade" in sql
    assert "source_ref text not null" in sql
    assert "source_sha256 text not null" in sql
    assert "testdata_ref text" in sql
    assert "idx_judge_queue_jobs_status_priority" in sql
    assert "idx_judge_queue_jobs_submission" in sql
    assert "0010" in sql


def test_compiler_config_migration_seeds_enabled_languages_and_table_constraints() -> None:
    sql = COMPILER_CONFIG_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists compiler_configs" in sql
    assert "code text primary key check (code in ('c', 'cpp', 'java', 'python'))" in sql
    assert "compile_command jsonb not null default '[]'::jsonb" in sql
    assert "run_command jsonb not null default '[]'::jsonb" in sql
    assert "insert into compiler_configs" in sql
    for language in ["'c'", "'cpp'", "'java'", "'python'"]:
        assert language in sql
    assert "insert into schema_migrations" in sql
    assert "0011" in sql


def test_migration_static_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
