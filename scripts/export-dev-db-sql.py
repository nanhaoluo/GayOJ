from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "apps" / "api" / "storage" / "dev-db.json"

SECTION_NAMES = [
    "users",
    "problems",
    "tags",
    "problem_versions",
    "submissions",
    "judge_queue_jobs",
    "contests",
    "contest_announcements",
    "clarifications",
    "judge_nodes",
    "compiler_configs",
    "audit_logs",
    "problem_sets",
    "teams",
    "assignments",
    "discussions",
    "notifications",
]

ROLE_CODES = {"student", "coach", "judge", "admin"}


class RawSql(str):
    pass


def fail(message: str) -> None:
    print(f"dev-db SQL export failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"input file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"input file is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("input JSON root must be an object")
    return data


def sql_literal(value: Any) -> str:
    if isinstance(value, RawSql):
        return str(value)
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("non-finite numeric values cannot be exported to PostgreSQL")
        return repr(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sql_json(value: Any, *, nullable: bool = False) -> str:
    if nullable and value is None:
        return "NULL"
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{sql_literal(payload)}::jsonb"


def sql_time(value: Any, *, nullable: bool = False) -> str:
    if value in (None, ""):
        return "NULL" if nullable else "DEFAULT"
    return f"{sql_literal(value)}::timestamptz"


def values_clause(columns: list[str], rows: list[dict[str, str]]) -> str:
    lines = []
    for row in rows:
        values = ", ".join(row[column] for column in columns)
        lines.append(f"    ({values})")
    return ",\n".join(lines)


def emit_upsert(
    table: str,
    columns: list[str],
    rows: list[dict[str, str]],
    conflict_columns: list[str],
    *,
    update_columns: list[str] | None = None,
) -> list[str]:
    if not rows:
        return [f"-- no rows for {table}", ""]

    conflict = ", ".join(conflict_columns)
    update_targets = update_columns
    if update_targets is None:
        update_targets = [column for column in columns if column not in conflict_columns and column != "created_at"]

    statement = [
        f"INSERT INTO {table} ({', '.join(columns)})",
        "VALUES",
        values_clause(columns, rows),
    ]
    if update_targets:
        assignments = ",\n    ".join(f"{column} = EXCLUDED.{column}" for column in update_targets)
        statement.append(f"ON CONFLICT ({conflict}) DO UPDATE SET\n    {assignments};")
    else:
        statement.append(f"ON CONFLICT ({conflict}) DO NOTHING;")
    statement.append("")
    return statement


def as_items(data: dict[str, Any], section: str) -> list[dict[str, Any]]:
    value = data.get(section, [])
    if value is None:
        return []
    if not isinstance(value, list):
        fail(f"{section} must be an array")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            fail(f"{section}[{index}] must be an object")
        items.append(item)
    return items


def object_section(data: dict[str, Any], section: str) -> dict[str, Any]:
    value = data.get(section, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail(f"{section} must be an object")
    return value


def clean_tag_name(value: Any) -> str:
    return str(value or "").strip()


def tag_slug(name: str) -> str:
    return "-".join(name.lower().replace("，", " ").replace(",", " ").split())


def next_tag_id(items: list[dict[str, Any]]) -> str:
    numeric = [
        int(str(item.get("id", ""))[3:])
        for item in items
        if str(item.get("id", "")).startswith("TAG") and str(item.get("id", ""))[3:].isdigit()
    ]
    return f"TAG{max(numeric, default=1000) + 1}"


def tag_items(data: dict[str, Any], problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = data.get("tags", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        fail("tags must be an array")

    items: list[dict[str, Any]] = []
    names: set[str] = set()
    ids: set[str] = set()
    for index, raw_item in enumerate(raw):
        if isinstance(raw_item, str):
            raw_item = {"name": raw_item}
        if not isinstance(raw_item, dict):
            fail(f"tags[{index}] must be an object")
        name = clean_tag_name(raw_item.get("name"))
        if not name or name in names:
            continue
        tag_id = str(raw_item.get("id") or "").strip()
        if not tag_id or tag_id in ids:
            tag_id = next_tag_id(items)
        item = {
            "id": tag_id,
            "name": name,
            "slug": clean_tag_name(raw_item.get("slug")) or tag_slug(name),
            "parent_id": str(raw_item.get("parent_id") or "").strip() or None,
            "sort_order": raw_item.get("sort_order", 0),
            "created_at": raw_item.get("created_at"),
        }
        items.append(item)
        names.add(name)
        ids.add(tag_id)

    valid_ids = {item["id"] for item in items}
    for item in items:
        if item["parent_id"] and item["parent_id"] not in valid_ids:
            item["parent_id"] = None

    for problem in problems:
        problem_tags = problem.get("tags", [])
        if isinstance(problem_tags, str):
            problem_tags = problem_tags.replace("，", ",").split(",")
        if not isinstance(problem_tags, list):
            continue
        for tag_name in problem_tags:
            name = clean_tag_name(tag_name)
            if not name or name in names:
                continue
            item = {
                "id": next_tag_id(items),
                "name": name,
                "slug": tag_slug(name),
                "parent_id": None,
                "sort_order": len(items) * 10,
                "created_at": problem.get("created_at"),
            }
            items.append(item)
            names.add(name)
    return items


def problem_judge_config_section(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("problem_judge_config", {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail("problem_judge_config must be an object")
    return value


def problem_test_data_section(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("problem_test_data", {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail("problem_test_data must be an object")
    return value


def user_rows(users: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for user in users:
        rows.append(
            {
                "id": sql_literal(user.get("id", "")),
                "username": sql_literal(user.get("username", "")),
                "display_name": sql_literal(user.get("display_name", "")),
                "role": sql_literal(user.get("role", "student")),
                "school": sql_literal(user.get("school", "")),
                "email": sql_literal(user.get("email", "")),
                "rating": sql_literal(user.get("rating", 1500)),
                "solved": sql_literal(user.get("solved", 0)),
                "disabled": sql_literal(user.get("disabled", False)),
                "password_hash": sql_literal(user.get("password_hash", "")),
                "failed_login_attempts": sql_literal(user.get("failed_login_attempts", 0)),
                "locked_until": sql_time(user.get("locked_until"), nullable=True),
                "last_login_at": sql_time(user.get("last_login_at"), nullable=True),
                "password_changed_at": sql_time(user.get("password_changed_at"), nullable=True),
            }
        )
    return rows


def user_role_rows(users: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for user in users:
        role = user.get("role")
        if role not in ROLE_CODES:
            continue
        rows.append(
            {
                "user_id": sql_literal(user.get("id", "")),
                "role_code": sql_literal(role),
                "scope_type": sql_literal("global"),
                "scope_id": sql_literal("*"),
            }
        )
    return rows


def tag_rows(tags: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    valid_ids = {tag.get("id") for tag in tags}
    for tag in tags:
        rows.append(
            {
                "id": sql_literal(tag.get("id", "")),
                "name": sql_literal(tag.get("name", "")),
                "slug": sql_literal(tag.get("slug") or tag_slug(str(tag.get("name", "")))),
                "parent_id": sql_literal(tag.get("parent_id") if tag.get("parent_id") in valid_ids else None),
                "sort_order": sql_literal(tag.get("sort_order", 0)),
                "created_at": sql_time(tag.get("created_at")),
            }
        )
    return rows


def problem_tag_rows(problems: list[dict[str, Any]], tags: list[dict[str, Any]]) -> list[dict[str, str]]:
    tag_ids_by_name = {clean_tag_name(tag.get("name")): tag.get("id") for tag in tags}
    rows = []
    seen: set[tuple[str, str]] = set()
    for problem in problems:
        problem_id = str(problem.get("id", ""))
        problem_tags = problem.get("tags", [])
        if isinstance(problem_tags, str):
            problem_tags = problem_tags.replace("，", ",").split(",")
        if not isinstance(problem_tags, list):
            continue
        for raw_name in problem_tags:
            name = clean_tag_name(raw_name)
            tag_id = tag_ids_by_name.get(name)
            if not problem_id or not tag_id or (problem_id, str(tag_id)) in seen:
                continue
            seen.add((problem_id, str(tag_id)))
            rows.append(
                {
                    "problem_id": sql_literal(problem_id),
                    "tag_id": sql_literal(tag_id),
                }
            )
    return rows


def problem_rows(problems: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for problem in problems:
        rows.append(
            {
                "id": sql_literal(problem.get("id", "")),
                "title": sql_literal(problem.get("title", "")),
                "problem_type": sql_literal(problem.get("type", "code")),
                "difficulty": sql_literal(problem.get("difficulty", "基础")),
                "tags": sql_json(problem.get("tags", [])),
                "statement": sql_literal(problem.get("statement", "")),
                "input_format": sql_literal(problem.get("input_format", "")),
                "output_format": sql_literal(problem.get("output_format", "")),
                "samples": sql_json(problem.get("samples", [])),
                "options": sql_json(problem.get("options", [])),
                "blanks": sql_json(problem.get("blanks", [])),
                "time_limit_ms": sql_literal(problem.get("time_limit_ms")),
                "memory_limit_mb": sql_literal(problem.get("memory_limit_mb")),
                "author_id": sql_literal(problem.get("author_id", "")),
                "visible": sql_literal(problem.get("visible", True)),
                "offline_enabled": sql_literal(problem.get("offline_enabled", problem.get("type") != "code")),
                "offline_policy": sql_json(problem.get("offline_policy", {})),
                "created_at": sql_time(problem.get("created_at")),
            }
        )
    return rows


def problem_judge_config_rows(
    problems: list[dict[str, Any]],
    judge_configs: dict[str, Any],
) -> list[dict[str, str]]:
    rows = []
    for problem in problems:
        problem_id = str(problem.get("id", ""))
        config = judge_configs.get(problem_id, problem.get("judge_config", {}))
        rows.append(
            {
                "problem_id": sql_literal(problem_id),
                "config": sql_json(config),
                "created_at": sql_time(problem.get("created_at")),
            }
        )
    return rows


def problem_test_data_rows(test_data: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for problem_id, item in sorted(test_data.items()):
        if not isinstance(item, dict):
            fail(f"problem_test_data[{problem_id}] must be an object")
        rows.append(
            {
                "problem_id": sql_literal(item.get("problem_id") or problem_id),
                "storage_backend": sql_literal(item.get("storage_backend", "local")),
                "bucket": sql_literal(item.get("bucket", "gayoj-testdata")),
                "object_key": sql_literal(item.get("object_key", "")),
                "filename": sql_literal(item.get("filename", "")),
                "archive_format": sql_literal(item.get("archive_format", "zip")),
                "size_bytes": sql_literal(item.get("size_bytes", 0)),
                "sha256": sql_literal(item.get("sha256", "")),
                "file_count": sql_literal(item.get("file_count", 0)),
                "input_files": sql_literal(item.get("input_files", 0)),
                "output_files": sql_literal(item.get("output_files", 0)),
                "case_count": sql_literal(item.get("case_count", 0)),
                "case_names": sql_json(item.get("case_names", [])),
                "uploaded_by": sql_literal(item.get("uploaded_by")),
                "uploaded_at": sql_time(item.get("uploaded_at")),
            }
        )
    return rows


def problem_version_rows(versions: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in versions:
        rows.append(
            {
                "id": sql_literal(item.get("id", "")),
                "problem_id": sql_literal(item.get("problem_id", "")),
                "version": sql_literal(item.get("version", 1)),
                "saved_by": sql_literal(item.get("saved_by")),
                "action": sql_literal(item.get("action", "update")),
                "snapshot": sql_json(item.get("snapshot", {})),
                "saved_at": sql_time(item.get("saved_at")),
            }
        )
    return rows


def contest_rows(contests: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for contest in contests:
        rows.append(
            {
                "id": sql_literal(contest.get("id", "")),
                "title": sql_literal(contest.get("title", "")),
                "rule": sql_literal(contest.get("rule", "ACM")),
                "start_at": sql_time(contest.get("start_at")),
                "end_at": sql_time(contest.get("end_at")),
                "problem_ids": sql_json(contest.get("problem_ids", [])),
                "status": sql_literal(contest.get("status", "scheduled")),
                "visibility": sql_literal(contest.get("visibility", "public")),
                "participation_mode": sql_literal(contest.get("participation_mode", "open")),
                "registered_user_ids": sql_json(contest.get("registered_user_ids", [])),
                "registered_team_ids": sql_json(contest.get("registered_team_ids", [])),
                "roster_locked": sql_literal(bool(contest.get("roster_locked", False))),
                "roster_locked_at": sql_time(contest.get("roster_locked_at")),
                "roster_locked_by": sql_literal(contest.get("roster_locked_by")),
                "access_mode": sql_literal(contest.get("access_mode", "open")),
                "access_code_hash": sql_literal(contest.get("access_code_hash", "")),
                "team_ids": sql_json(contest.get("team_ids", [])),
                "participant_user_ids": sql_json(contest.get("participant_user_ids", [])),
                "access_unlocked_user_ids": sql_json(contest.get("access_unlocked_user_ids", [])),
            }
        )
    return rows


def submission_rows(submissions: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for submission in submissions:
        rows.append(
            {
                "id": sql_literal(submission.get("id", "")),
                "user_id": sql_literal(submission.get("user_id", "")),
                "problem_id": sql_literal(submission.get("problem_id", "")),
                "problem_title": sql_literal(submission.get("problem_title", "")),
                "problem_type": sql_literal(submission.get("problem_type", "code")),
                "contest_id": sql_literal(submission.get("contest_id")),
                "language": sql_literal(submission.get("language")),
                "source_code": sql_literal(submission.get("source_code")),
                "offline_result_key": sql_literal(submission.get("offline_result_key")),
                "answers": sql_json(submission.get("answers"), nullable=True),
                "status": sql_literal(submission.get("status", "queued")),
                "score": sql_literal(submission.get("score", 0)),
                "max_score": sql_literal(submission.get("max_score", 100)),
                "details": sql_json(submission.get("details", [])),
                "message": sql_literal(submission.get("message", "")),
                "created_at": sql_time(submission.get("created_at")),
                "judged_at": sql_time(submission.get("judged_at"), nullable=True),
            }
        )
    return rows


def judge_queue_job_rows(
    jobs: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    judge_configs: dict[str, Any],
) -> list[dict[str, str]]:
    if not jobs:
        jobs = [
            {
                "id": submission.get("queue_job_id") or f"JQ-{submission.get('id', '')}",
                "submission_id": submission.get("id", ""),
                "problem_id": submission.get("problem_id", ""),
                "user_id": submission.get("user_id", ""),
                "contest_id": submission.get("contest_id"),
                "language": submission.get("language"),
                "source_ref": f"submission:{submission.get('id', '')}:source_code",
                "source_sha256": hashlib.sha256(str(submission.get("source_code") or "").encode("utf-8")).hexdigest(),
                "priority": 10 if submission.get("contest_id") else 0,
                "status": "leased" if submission.get("status") == "judging" else "pending",
                "backend": "json",
                "created_at": submission.get("queued_at") or submission.get("created_at"),
            }
            for submission in submissions
            if submission.get("problem_type") == "code" and submission.get("status") in {"queued", "judging"}
        ]

    problems_by_id = {str(problem.get("id")): problem for problem in problems if problem.get("id")}
    submissions_by_id = {str(submission.get("id")): submission for submission in submissions if submission.get("id")}
    rows = []
    for job in jobs:
        submission = submissions_by_id.get(str(job.get("submission_id") or ""), {})
        problem_id = str(job.get("problem_id") or submission.get("problem_id") or "")
        problem = problems_by_id.get(problem_id, {})
        config = judge_configs.get(problem_id, {}) if isinstance(judge_configs.get(problem_id, {}), dict) else {}
        source = str(submission.get("source_code") or "")
        rows.append(
            {
                "id": sql_literal(job.get("id", "")),
                "submission_id": sql_literal(job.get("submission_id", "")),
                "problem_id": sql_literal(problem_id),
                "user_id": sql_literal(job.get("user_id") or submission.get("user_id", "")),
                "contest_id": sql_literal(job.get("contest_id") if job.get("contest_id") is not None else submission.get("contest_id")),
                "language": sql_literal(job.get("language") or submission.get("language") or ""),
                "source_ref": sql_literal(job.get("source_ref") or f"submission:{job.get('submission_id', '')}:source_code"),
                "source_sha256": sql_literal(
                    job.get("source_sha256") or hashlib.sha256(source.encode("utf-8")).hexdigest()
                ),
                "limits": sql_json(
                    job.get("limits")
                    if isinstance(job.get("limits"), dict)
                    else {
                        "time_limit_ms": problem.get("time_limit_ms"),
                        "memory_limit_mb": problem.get("memory_limit_mb"),
                    }
                ),
                "testdata_ref": sql_literal(
                    job.get("testdata_ref")
                    or config.get("testdata_ref")
                    or config.get("dataset_ref")
                    or (f"problem:{problem_id}:testdata" if problem_id else None)
                ),
                "priority": sql_literal(job.get("priority", 10 if submission.get("contest_id") else 0)),
                "status": sql_literal(job.get("status", "pending")),
                "backend": sql_literal(job.get("backend", "json")),
                "assigned_node_id": sql_literal(job.get("assigned_node_id")),
                "attempts": sql_literal(job.get("attempts", 0)),
                "last_error": sql_literal(job.get("last_error", "")),
                "created_at": sql_time(job.get("created_at") or submission.get("created_at")),
                "leased_at": sql_time(job.get("leased_at"), nullable=True),
                "completed_at": sql_time(job.get("completed_at"), nullable=True),
            }
        )
    return rows


def clarification_rows(clarifications: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in clarifications:
        rows.append(
            {
                "id": sql_literal(item.get("id", "")),
                "contest_id": sql_literal(item.get("contest_id", "")),
                "user_id": sql_literal(item.get("user_id", "")),
                "question": sql_literal(item.get("question", "")),
                "answer": sql_literal(item.get("answer")),
                "public": sql_literal(item.get("public", False)),
                "created_at": sql_time(item.get("created_at")),
            }
        )
    return rows


def contest_announcement_rows(announcements: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in announcements:
        rows.append(
            {
                "id": sql_literal(item.get("id", "")),
                "contest_id": sql_literal(item.get("contest_id", "")),
                "title": sql_literal(item.get("title", "")),
                "content": sql_literal(item.get("content", "")),
                "created_by": sql_literal(item.get("created_by", "")),
                "created_by_name": sql_literal(item.get("created_by_name", "")),
                "created_at": sql_time(item.get("created_at")),
            }
        )
    return rows


def judge_node_rows(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for node in nodes:
        rows.append(
            {
                "id": sql_literal(node.get("id", "")),
                "name": sql_literal(node.get("name", "")),
                "status": sql_literal(node.get("status", "offline")),
                "languages": sql_json(node.get("languages", [])),
                "queue_depth": sql_literal(node.get("queue_depth", 0)),
                "load": sql_literal(node.get("load", 0)),
                "last_heartbeat": sql_time(node.get("last_heartbeat")),
            }
        )
    return rows


def compiler_config_rows(configs: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for config in configs:
        rows.append(
            {
                "code": sql_literal(config.get("code", "")),
                "display_name": sql_literal(config.get("display_name", "")),
                "version": sql_literal(config.get("version", "")),
                "source_extension": sql_literal(config.get("source_extension", "")),
                "compile_command": sql_json(config.get("compile_command", [])),
                "run_command": sql_json(config.get("run_command", [])),
                "enabled": sql_literal(config.get("enabled", True)),
                "sort_order": sql_literal(config.get("sort_order", 0)),
                "updated_at": sql_time(config.get("updated_at"), nullable=True),
            }
        )
    return rows


def audit_log_rows(logs: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for log in logs:
        rows.append(
            {
                "id": sql_literal(log.get("id", "")),
                "actor_id": sql_literal(log.get("actor_id")),
                "action": sql_literal(log.get("action", "")),
                "resource": sql_literal(log.get("resource", "")),
                "metadata": sql_json(log.get("metadata", {})),
                "created_at": sql_time(log.get("created_at")),
            }
        )
    return rows


def problem_set_rows(problem_sets: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for problem_set in problem_sets:
        rows.append(
            {
                "id": sql_literal(problem_set.get("id", "")),
                "title": sql_literal(problem_set.get("title", "")),
                "description": sql_literal(problem_set.get("description", "")),
                "set_type": sql_literal(problem_set.get("type", "set")),
                "visibility": sql_literal(problem_set.get("visibility", "public")),
                "problem_ids": sql_json(problem_set.get("problem_ids", [])),
                "owner_id": sql_literal(problem_set.get("owner_id", "")),
                "duration_minutes": sql_literal(problem_set.get("duration_minutes")),
                "due_at": sql_time(problem_set.get("due_at"), nullable=True),
                "offline_enabled": sql_literal(problem_set.get("offline_enabled", True)),
                "offline_policy": sql_json(problem_set.get("offline_policy", {})),
                "created_at": sql_time(problem_set.get("created_at")),
                "updated_at": sql_time(problem_set.get("updated_at")),
            }
        )
    return rows


def team_rows(teams: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for team in teams:
        rows.append(
            {
                "id": sql_literal(team.get("id", "")),
                "name": sql_literal(team.get("name", "")),
                "description": sql_literal(team.get("description", "")),
                "invite_code": sql_literal(team.get("invite_code", "")),
                "owner_id": sql_literal(team.get("owner_id", "")),
                "member_ids": sql_json(team.get("member_ids", [])),
                "created_at": sql_time(team.get("created_at")),
            }
        )
    return rows


def assignment_rows(assignments: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for assignment in assignments:
        rows.append(
            {
                "id": sql_literal(assignment.get("id", "")),
                "title": sql_literal(assignment.get("title", "")),
                "description": sql_literal(assignment.get("description", "")),
                "problem_set_id": sql_literal(assignment.get("problem_set_id", "")),
                "team_id": sql_literal(assignment.get("team_id")),
                "due_at": sql_time(assignment.get("due_at")),
                "created_by": sql_literal(assignment.get("created_by", "")),
                "created_at": sql_time(assignment.get("created_at")),
            }
        )
    return rows


def discussion_rows(discussions: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for discussion in discussions:
        rows.append(
            {
                "id": sql_literal(discussion.get("id", "")),
                "discussion_type": sql_literal(discussion.get("type", "general")),
                "target_id": sql_literal(discussion.get("target_id")),
                "title": sql_literal(discussion.get("title", "")),
                "content": sql_literal(discussion.get("content", "")),
                "author_id": sql_literal(discussion.get("author_id", "")),
                "author_name": sql_literal(discussion.get("author_name", "")),
                "pinned": sql_literal(discussion.get("pinned", False)),
                "likes": sql_literal(discussion.get("likes", 0)),
                "solution_category": sql_literal(discussion.get("solution_category")),
                "liked_by": sql_json(discussion.get("liked_by", [])),
                "bookmarked_by": sql_json(discussion.get("bookmarked_by", [])),
                "replies": sql_json(discussion.get("replies", [])),
                "created_at": sql_time(discussion.get("created_at")),
                "updated_at": sql_time(discussion.get("updated_at")),
            }
        )
    return rows


def notification_rows(notifications: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for notification in notifications:
        rows.append(
            {
                "id": sql_literal(notification.get("id", "")),
                "user_id": sql_literal(notification.get("user_id", "")),
                "title": sql_literal(notification.get("title", "")),
                "content": sql_literal(notification.get("content", "")),
                "notification_type": sql_literal(notification.get("type", "system")),
                "is_read": sql_literal(notification.get("is_read", False)),
                "created_at": sql_time(notification.get("created_at")),
            }
        )
    return rows


def system_config_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": sql_literal(key), "value": sql_json(value)} for key, value in sorted(config.items())]


def generate_sql(data: dict[str, Any]) -> str:
    users = as_items(data, "users")
    problems = as_items(data, "problems")
    tags = tag_items(data, problems)
    judge_configs = problem_judge_config_section(data)
    test_data = problem_test_data_section(data)
    contests = as_items(data, "contests")
    submissions = as_items(data, "submissions")

    lines = [
        "-- gayoj P1-04 JSON import generated by scripts/export-dev-db-sql.py.",
        "-- Apply after all checked-in schema migrations.",
        "-- Submission source_code is imported as text data only; this script never compiles or runs it.",
        "BEGIN;",
        "",
    ]

    lines.extend(
        emit_upsert(
            "users",
            [
                "id",
                "username",
                "display_name",
                "role",
                "school",
                "email",
                "rating",
                "solved",
                "disabled",
                "password_hash",
                "failed_login_attempts",
                "locked_until",
                "last_login_at",
                "password_changed_at",
            ],
            user_rows(users),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "user_roles",
            ["user_id", "role_code", "scope_type", "scope_id"],
            user_role_rows(users),
            ["user_id", "role_code", "scope_type", "scope_id"],
            update_columns=[],
        )
    )
    lines.extend(
        emit_upsert(
            "tags",
            ["id", "name", "slug", "parent_id", "sort_order", "created_at"],
            tag_rows(tags),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "problems",
            [
                "id",
                "title",
                "problem_type",
                "difficulty",
                "tags",
                "statement",
                "input_format",
                "output_format",
                "samples",
                "options",
                "blanks",
                "time_limit_ms",
                "memory_limit_mb",
                "author_id",
                "visible",
                "offline_enabled",
                "offline_policy",
                "created_at",
            ],
            problem_rows(problems),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "problem_tags",
            ["problem_id", "tag_id"],
            problem_tag_rows(problems, tags),
            ["problem_id", "tag_id"],
            update_columns=[],
        )
    )
    lines.extend(
        emit_upsert(
            "problem_judge_config",
            ["problem_id", "config", "created_at"],
            problem_judge_config_rows(problems, judge_configs),
            ["problem_id"],
        )
    )
    lines.extend(
        emit_upsert(
            "problem_test_data",
            [
                "problem_id",
                "storage_backend",
                "bucket",
                "object_key",
                "filename",
                "archive_format",
                "size_bytes",
                "sha256",
                "file_count",
                "input_files",
                "output_files",
                "case_count",
                "case_names",
                "uploaded_by",
                "uploaded_at",
            ],
            problem_test_data_rows(test_data),
            ["problem_id"],
        )
    )
    lines.extend(
        emit_upsert(
            "problem_versions",
            ["id", "problem_id", "version", "saved_by", "action", "snapshot", "saved_at"],
            problem_version_rows(as_items(data, "problem_versions")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "contests",
            [
                "id",
                "title",
                "rule",
                "start_at",
                "end_at",
                "problem_ids",
                "status",
                "visibility",
                "participation_mode",
                "registered_user_ids",
                "registered_team_ids",
                "roster_locked",
                "roster_locked_at",
                "roster_locked_by",
                "access_mode",
                "access_code_hash",
                "team_ids",
                "participant_user_ids",
                "access_unlocked_user_ids",
            ],
            contest_rows(contests),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "contest_announcements",
            ["id", "contest_id", "title", "content", "created_by", "created_by_name", "created_at"],
            contest_announcement_rows(as_items(data, "contest_announcements")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "submissions",
            [
                "id",
                "user_id",
                "problem_id",
                "problem_title",
                "problem_type",
                "contest_id",
                "language",
                "source_code",
                "offline_result_key",
                "answers",
                "status",
                "score",
                "max_score",
                "details",
                "message",
                "created_at",
                "judged_at",
            ],
            submission_rows(submissions),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "clarifications",
            ["id", "contest_id", "user_id", "question", "answer", "public", "created_at"],
            clarification_rows(as_items(data, "clarifications")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "judge_nodes",
            ["id", "name", "status", "languages", "queue_depth", "load", "last_heartbeat"],
            judge_node_rows(as_items(data, "judge_nodes")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "compiler_configs",
            [
                "code",
                "display_name",
                "version",
                "source_extension",
                "compile_command",
                "run_command",
                "enabled",
                "sort_order",
                "updated_at",
            ],
            compiler_config_rows(as_items(data, "compiler_configs")),
            ["code"],
        )
    )
    lines.extend(
        emit_upsert(
            "judge_queue_jobs",
            [
                "id",
                "submission_id",
                "problem_id",
                "user_id",
                "contest_id",
                "language",
                "source_ref",
                "source_sha256",
                "limits",
                "testdata_ref",
                "priority",
                "status",
                "backend",
                "assigned_node_id",
                "attempts",
                "last_error",
                "created_at",
                "leased_at",
                "completed_at",
            ],
            judge_queue_job_rows(
                as_items(data, "judge_queue_jobs"),
                submissions,
                problems,
                judge_configs,
            ),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "audit_logs",
            ["id", "actor_id", "action", "resource", "metadata", "created_at"],
            audit_log_rows(as_items(data, "audit_logs")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "problem_sets",
            [
                "id",
                "title",
                "description",
                "set_type",
                "visibility",
                "problem_ids",
                "owner_id",
                "duration_minutes",
                "due_at",
                "offline_enabled",
                "offline_policy",
                "created_at",
                "updated_at",
            ],
            problem_set_rows(as_items(data, "problem_sets")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "teams",
            ["id", "name", "description", "invite_code", "owner_id", "member_ids", "created_at"],
            team_rows(as_items(data, "teams")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "assignments",
            ["id", "title", "description", "problem_set_id", "team_id", "due_at", "created_by", "created_at"],
            assignment_rows(as_items(data, "assignments")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "discussions",
            [
                "id",
                "discussion_type",
                "target_id",
                "title",
                "content",
                "author_id",
                "author_name",
                "pinned",
                "likes",
                "solution_category",
                "liked_by",
                "bookmarked_by",
                "replies",
                "created_at",
                "updated_at",
            ],
            discussion_rows(as_items(data, "discussions")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "notifications",
            ["id", "user_id", "title", "content", "notification_type", "is_read", "created_at"],
            notification_rows(as_items(data, "notifications")),
            ["id"],
        )
    )
    lines.extend(
        emit_upsert(
            "system_config",
            ["key", "value"],
            system_config_rows(object_section(data, "system_config")),
            ["key"],
            update_columns=["value"],
        )
    )
    lines.extend(["COMMIT;", ""])
    return "\n".join(lines)


def summarize(data: dict[str, Any]) -> str:
    problems = as_items(data, "problems")
    parts = []
    for section in SECTION_NAMES:
        if section == "tags":
            parts.append(f"tags={len(tag_items(data, problems))}")
        else:
            parts.append(f"{section}={len(as_items(data, section))}")
    parts.append(f"problem_judge_config={len(problem_judge_config_section(data))}")
    parts.append(f"problem_test_data={len(problem_test_data_section(data))}")
    parts.append(f"system_config={len(object_section(data, 'system_config'))}")
    return "dev-db JSON is importable: " + ", ".join(parts)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export gayoj dev-db.json as idempotent PostgreSQL SQL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to apps/api/storage/dev-db.json")
    parser.add_argument("--output", type=Path, help="Write SQL to this file instead of stdout")
    parser.add_argument("--check-only", action="store_true", help="Validate and summarize JSON without writing SQL")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data = load_snapshot(args.input)
    if args.check_only:
        print(summarize(data))
        return 0

    sql = generate_sql(data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(sql, encoding="utf-8")
    else:
        print(sql, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

