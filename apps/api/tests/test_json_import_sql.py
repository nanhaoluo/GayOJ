from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "export-dev-db-sql.py"
DEV_DB = ROOT / "apps" / "api" / "storage" / "dev-db.json"


def run_export(*args: str | Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def insert_statement(sql: str, table: str) -> str:
    start = sql.find(f"INSERT INTO {table} ")
    assert start >= 0, f"missing INSERT for {table}"
    candidates = [
        index
        for marker in ["\n\nINSERT INTO ", "\n\n-- no rows for ", "\n\nCOMMIT;"]
        if (index := sql.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(sql)
    return sql[start:end]


def test_dev_db_export_generates_core_business_import_sql() -> None:
    result = run_export("--input", DEV_DB)
    assert result.returncode == 0, result.stderr
    sql = result.stdout

    for table in [
        "users",
        "user_roles",
        "tags",
        "problems",
        "problem_tags",
        "problem_judge_config",
        "problem_test_data",
        "problem_versions",
        "contests",
        "submissions",
        "judge_queue_jobs",
        "judge_nodes",
        "compiler_configs",
        "problem_sets",
        "teams",
        "assignments",
        "discussions",
        "notifications",
        "contest_announcements",
        "system_config",
    ]:
        assert f"INSERT INTO {table}" in sql or f"-- no rows for {table}" in sql

    assert "'P1001'" in sql
    assert "'P1002'" in sql
    assert "'C1001'" in sql
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_problem_judge_config_is_split_from_public_problem_rows() -> None:
    result = run_export("--input", DEV_DB)
    assert result.returncode == 0, result.stderr
    sql = result.stdout

    problems_insert = insert_statement(sql, "problems")
    judge_config_insert = insert_statement(sql, "problem_judge_config")

    assert "judge_config" not in problems_insert
    assert "simulator_hint" not in problems_insert
    assert "answers" not in problems_insert
    assert "config" in judge_config_insert
    assert "simulator_hint" in judge_config_insert
    assert "answers" in judge_config_insert


def test_export_reads_isolated_problem_judge_config_section(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "coach",
                "display_name": "Coach",
                "role": "coach",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P2",
                "title": "Isolated",
                "type": "single_choice",
                "statement": "Choose A.",
                "options": [{"key": "A", "text": "A"}],
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "problem_judge_config": {"P2": {"answer": "A", "score": 100}},
        "contests": [],
        "submissions": [],
        "system_config": {},
    }
    input_path = tmp_path / "isolated-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    problems_insert = insert_statement(result.stdout, "problems")
    judge_config_insert = insert_statement(result.stdout, "problem_judge_config")

    assert "answer" not in problems_insert
    assert '{"answer":"A","score":100}' in judge_config_insert


def test_export_backfills_problem_tag_rows_from_legacy_problem_tags(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "coach",
                "display_name": "Coach",
                "role": "coach",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P2",
                "title": "Tagged",
                "type": "single_choice",
                "difficulty": "基础",
                "tags": ["图论", "二分"],
                "statement": "Choose A.",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "problem_judge_config": {"P2": {"answer": "A", "score": 100}},
        "contests": [],
        "submissions": [],
        "system_config": {},
    }
    input_path = tmp_path / "legacy-tags-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)

    assert result.returncode == 0, result.stderr
    assert "INSERT INTO tags" in result.stdout
    assert "INSERT INTO problem_tags" in result.stdout
    assert "图论" in result.stdout
    assert "二分" in result.stdout


def test_export_includes_problem_versions_as_management_snapshots(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "admin",
                "display_name": "Admin",
                "role": "admin",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P2",
                "title": "Current",
                "type": "single_choice",
                "statement": "Choose B.",
                "options": [{"key": "B", "text": "B"}],
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "problem_judge_config": {"P2": {"answer": "B", "score": 100}},
        "problem_versions": [
            {
                "id": "PV1",
                "problem_id": "P2",
                "version": 1,
                "saved_by": "u1",
                "action": "update",
                "saved_at": "2026-05-23T00:00:00Z",
                "snapshot": {
                    "id": "P2",
                    "title": "Old",
                    "type": "single_choice",
                    "statement": "Choose A.",
                    "options": [{"key": "A", "text": "A"}],
                    "author_id": "u1",
                    "visible": True,
                    "judge_config": {"answer": "A", "score": 100},
                    "created_at": "2026-05-22T00:00:00Z",
                },
            }
        ],
        "contests": [],
        "submissions": [],
        "system_config": {},
    }
    input_path = tmp_path / "versioned-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    problem_versions_insert = insert_statement(result.stdout, "problem_versions")

    assert "snapshot" in problem_versions_insert
    assert "PV1" in problem_versions_insert
    assert "Choose A." in problem_versions_insert
    assert "judge_config" in problem_versions_insert


def test_export_includes_problem_test_data_metadata(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "admin",
                "display_name": "Admin",
                "role": "admin",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P1",
                "title": "A+B",
                "type": "code",
                "statement": "Sum.",
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "problem_judge_config": {"P1": {"mode": "standard", "testdata_ref": "testdata/P1/hash.zip"}},
        "problem_test_data": {
            "P1": {
                "problem_id": "P1",
                "filename": "cases.zip",
                "object_key": "testdata/P1/hash.zip",
                "storage_backend": "local",
                "bucket": "gayoj-testdata",
                "archive_format": "zip",
                "size_bytes": 123,
                "sha256": "hash",
                "file_count": 2,
                "input_files": 1,
                "output_files": 1,
                "case_count": 1,
                "case_names": ["1"],
                "uploaded_by": "u1",
                "uploaded_at": "2026-05-23T00:00:00Z",
            }
        },
        "contests": [],
        "submissions": [],
        "system_config": {},
    }
    input_path = tmp_path / "testdata-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    test_data_insert = insert_statement(result.stdout, "problem_test_data")

    assert "testdata/P1/hash.zip" in test_data_insert
    assert "cases.zip" in test_data_insert
    assert "case_names" in test_data_insert


def test_submission_source_code_is_exported_as_data_only(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "role": "student",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P1",
                "title": "A+B",
                "type": "code",
                "statement": "Sum.",
                "author_id": "u1",
                "judge_config": {"mode": "standard"},
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "contests": [],
        "submissions": [
            {
                "id": "S1",
                "user_id": "u1",
                "problem_id": "P1",
                "problem_title": "A+B",
                "problem_type": "code",
                "language": "python",
                "source_code": "print('do not execute import data')",
                "status": "queued",
                "score": 0,
                "max_score": 100,
                "details": [],
                "message": "queued only",
                "created_at": "2026-05-22T00:00:01Z",
            }
        ],
        "system_config": {},
    }
    input_path = tmp_path / "dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    submissions_insert = insert_statement(result.stdout, "submissions")

    assert "source_code" in submissions_insert
    assert "do not execute import data" in submissions_insert
    assert "ONLINE JUDGE" not in result.stderr.upper()

    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ["subprocess", "os.system", "eval(", "exec(", "compile("]:
        assert forbidden not in source


def test_offline_result_key_is_exported_with_submissions(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "role": "student",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P1",
                "title": "Choice",
                "type": "single_choice",
                "statement": "Pick one.",
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "contests": [],
        "submissions": [
            {
                "id": "S1",
                "user_id": "u1",
                "problem_id": "P1",
                "problem_title": "Choice",
                "problem_type": "single_choice",
                "answers": {"choice": "B"},
                "offline_result_key": "cli:stable-result",
                "status": "accepted",
                "score": 100,
                "max_score": 100,
                "details": [],
                "message": "offline sync",
                "created_at": "2026-05-22T00:00:01Z",
                "judged_at": "2026-05-22T00:00:02Z",
            }
        ],
        "system_config": {},
    }
    input_path = tmp_path / "dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    submissions_insert = insert_statement(result.stdout, "submissions")

    assert "offline_result_key" in submissions_insert
    assert "cli:stable-result" in submissions_insert


def test_export_includes_judge_queue_jobs_as_metadata_only(tmp_path: Path) -> None:
    snapshot = {
        "users": [
            {
                "id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "role": "student",
                "password_hash": "hash",
            }
        ],
        "problems": [
            {
                "id": "P1",
                "title": "A+B",
                "type": "code",
                "statement": "Sum.",
                "author_id": "u1",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
        "submissions": [
            {
                "id": "S1",
                "user_id": "u1",
                "problem_id": "P1",
                "problem_title": "A+B",
                "problem_type": "code",
                "language": "python",
                "source_code": "print('queued only')",
                "queue_job_id": "JQ1",
                "status": "queued",
                "score": 0,
                "max_score": 100,
                "details": [],
                "message": "queued only",
                "created_at": "2026-05-22T00:00:01Z",
            }
        ],
        "judge_queue_jobs": [
            {
                "id": "JQ1",
                "submission_id": "S1",
                "problem_id": "P1",
                "user_id": "u1",
                "language": "python",
                "source_ref": "submission:S1:source",
                "source_sha256": "abc123",
                "limits": {"time_ms": 1000},
                "testdata_ref": "problem:P1:testdata",
                "status": "pending",
                "backend": "json",
                "created_at": "2026-05-22T00:00:01Z",
            }
        ],
        "contests": [],
        "system_config": {},
    }
    input_path = tmp_path / "queued-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    queue_insert = insert_statement(result.stdout, "judge_queue_jobs")

    assert "submission:S1:source" in queue_insert
    assert "source_ref" in queue_insert
    assert "source_code" not in queue_insert


def test_export_includes_compiler_configs_as_configuration_only(tmp_path: Path) -> None:
    snapshot = {
        "users": [],
        "problems": [],
        "submissions": [],
        "compiler_configs": [
            {
                "code": "python",
                "display_name": "Python",
                "version": "Python 3.12",
                "source_extension": ".py",
                "compile_command": ["python3", "-m", "py_compile", "Main.py"],
                "run_command": ["python3", "Main.py"],
                "enabled": True,
                "sort_order": 40,
                "updated_at": "2026-05-23T00:00:00Z",
            }
        ],
        "contests": [],
        "system_config": {},
    }
    input_path = tmp_path / "compiler-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    compiler_insert = insert_statement(result.stdout, "compiler_configs")

    assert "Python 3.12" in compiler_insert
    assert "py_compile" in compiler_insert
    assert "source_code" not in compiler_insert


def test_export_preserves_compiler_config_state_and_runtime_metadata(tmp_path: Path) -> None:
    snapshot = {
        "users": [],
        "problems": [],
        "submissions": [],
        "compiler_configs": [
            {
                "code": "cpp",
                "display_name": "C++17",
                "version": "GCC 14.2 / C++17",
                "source_extension": ".cpp",
                "compile_command": ["g++", "-std=c++17", "Main.cpp"],
                "run_command": ["./Main"],
                "enabled": False,
                "sort_order": 20,
                "updated_at": "2026-05-23T00:00:00Z",
            }
        ],
        "contests": [],
        "system_config": {},
    }
    input_path = tmp_path / "compiler-disabled-dev-db.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")

    result = run_export("--input", input_path)
    assert result.returncode == 0, result.stderr
    compiler_insert = insert_statement(result.stdout, "compiler_configs")

    assert "FALSE" in compiler_insert
    assert "GCC 14.2 / C++17" in compiler_insert
    assert "g++" in compiler_insert
    assert "source_code" not in compiler_insert


def test_export_script_supports_check_only_and_output_file(tmp_path: Path) -> None:
    output = tmp_path / "dev-db-import.sql"
    write_result = run_export("--input", DEV_DB, "--output", output)
    assert write_result.returncode == 0, write_result.stderr
    assert "INSERT INTO problems" in output.read_text(encoding="utf-8")

    check_result = run_export("--input", DEV_DB, "--check-only")
    assert check_result.returncode == 0, check_result.stderr
    assert "dev-db JSON is importable" in check_result.stdout
    assert "problems=" in check_result.stdout
    assert "submissions=" in check_result.stdout


def test_export_script_rejects_invalid_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")

    result = run_export("--input", invalid)

    assert result.returncode != 0
    assert "not valid JSON" in result.stderr
