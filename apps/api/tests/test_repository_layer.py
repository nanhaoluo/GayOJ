from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from app.auth import verify_password
from app.db import Repository, SnapshotRepository, seed_data
from app.models import DEFAULT_STUDENT_SCHOOL, Problem, ProblemTestData


ROOT = Path(__file__).resolve().parents[3]
DEV_DB = ROOT / "apps" / "api" / "storage" / "dev-db.json"


def sqlite_repository(tmp_path: Path, seed_path: Path | None = None, name: str = "gayoj-test.sqlite3") -> SnapshotRepository:
    return SnapshotRepository.sqlite(tmp_path / name, seed_path=seed_path)


def read_sqlite_snapshot(repository: SnapshotRepository) -> dict[str, Any]:
    payload = repository.database.read_payload()
    assert payload is not None
    return json.loads(payload)


def test_sqlite_repository_loads_current_dev_db_seed(tmp_path: Path) -> None:
    target = tmp_path / "dev-db.json"
    target.write_text(DEV_DB.read_text(encoding="utf-8"), encoding="utf-8")
    before = json.loads(target.read_text(encoding="utf-8"))

    repository = sqlite_repository(tmp_path, target)

    assert repository.get_user_by_username("alice")
    assert repository.get_problem("P1001")
    assert repository.get_system_config()["site_name"] == "gayoj"
    assert repository.get_user_by_username("alice").school == DEFAULT_STUDENT_SCHOOL  # type: ignore[union-attr]
    after = read_sqlite_snapshot(repository)
    assert set(before) <= set(after)
    assert "problem_versions" in after
    assert "problem_test_data" in after
    blank_problem = next(problem for problem in after["problems"] if problem["id"] == "P1002")
    assert "judge_config" not in blank_problem
    assert blank_problem["offline_enabled"] is True
    assert blank_problem["offline_policy"]["answer_visibility"] == "full"
    assert after["problem_judge_config"]["P1002"]["answers"]["edge_formula"]
    assert repository.get_problem("P1002").judge_config == {}
    assert repository.get_problem_judge_config("P1002")["answers"]["edge_formula"]


def test_sqlite_repository_backfills_legacy_json_defaults(tmp_path: Path) -> None:
    data = seed_data()
    data.pop("notifications")
    data.pop("system_config")
    data["users"][0].pop("password_hash")
    target = tmp_path / "legacy-dev-db.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository: Repository = sqlite_repository(tmp_path, target)

    alice = repository.get_user_by_username("alice")
    assert alice is not None
    assert alice.password_hash.startswith("pbkdf2_sha256$")
    assert alice.school == DEFAULT_STUDENT_SCHOOL
    assert repository.get_system_config()["site_name"] == "gayoj"
    assert repository.list_notifications("u-student")
    assert repository.get_problem("P1001").offline_enabled is False  # type: ignore[union-attr]
    assert repository.get_problem_set("PS1001").offline_enabled is True  # type: ignore[union-attr]


def test_sqlite_repository_migrates_legacy_default_student_school(tmp_path: Path) -> None:
    data = seed_data()
    data["users"][0]["school"] = "gayoj Training Team"
    target = tmp_path / "legacy-student-school.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository: Repository = sqlite_repository(tmp_path, target)

    alice = repository.get_user_by_username("alice")
    assert alice is not None
    assert alice.school == DEFAULT_STUDENT_SCHOOL


def test_sqlite_repository_backfills_partial_system_config(tmp_path: Path) -> None:
    data = seed_data()
    data["system_config"] = {"site_name": "Legacy gayoj"}
    target = tmp_path / "partial-config-dev-db.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository = sqlite_repository(tmp_path, target)

    config = repository.get_system_config()
    assert config["site_name"] == "Legacy gayoj"
    assert config["default_language"] == "cpp"
    assert config["judge_submit_rate_limit_per_minute"] == 10
    after = read_sqlite_snapshot(repository)
    assert after["system_config"]["objective_submit_rate_limit_per_minute"] == 30


def test_sqlite_repository_migrates_legacy_embedded_judge_config(tmp_path: Path) -> None:
    data = seed_data()
    configs = data.pop("problem_judge_config")
    for problem in data["problems"]:
        problem["judge_config"] = configs[problem["id"]]
    data["problems"][1]["judge_config"]["answers"]["edge_formula"] = ["legacy-answer"]
    target = tmp_path / "legacy-embedded-dev-db.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository = sqlite_repository(tmp_path, target)
    repository.list_problems()

    after = read_sqlite_snapshot(repository)
    assert all("judge_config" not in problem for problem in after["problems"])
    assert after["problem_judge_config"]["P1002"]["answers"]["edge_formula"] == ["legacy-answer"]
    assert repository.get_problem("P1002").judge_config == {}
    assert repository.get_problem_judge_config("P1002")["answers"]["edge_formula"] == ["legacy-answer"]


def test_sqlite_repository_migrates_legacy_demo_password_hashes(tmp_path: Path) -> None:
    legacy_hash = "pbkdf2_sha256$gayoj-demo-salt$c1570f6999257d09d37c38805485340bf93efbe239c3003df724aee4e0a11e14"
    data = seed_data()
    data["users"][0]["username"] = "alice"
    data["users"][0]["password_hash"] = legacy_hash
    data["users"][1]["username"] = "custom"
    data["users"][1]["password_hash"] = legacy_hash
    target = tmp_path / "legacy-demo-passwords.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository: Repository = sqlite_repository(tmp_path, target)

    alice = repository.get_user_by_username("alice")
    custom = repository.get_user_by_username("custom")
    assert alice is not None
    assert custom is not None
    assert verify_password("gayoj123", alice.password_hash)
    assert custom.password_hash == legacy_hash


def test_sqlite_repository_stores_new_problem_judge_config_separately(tmp_path: Path) -> None:
    repository = sqlite_repository(tmp_path)
    problem = Problem(
        id="P9001",
        title="临时单选题",
        type="single_choice",
        statement="请选择 A。",
        options=[{"key": "A", "text": "A"}],
        author_id="u-coach",
        judge_config={"answer": "A", "score": 100},
        created_at=datetime.now(timezone.utc),
    )

    repository.add_problem(problem)

    data = read_sqlite_snapshot(repository)
    stored_problem = next(item for item in data["problems"] if item["id"] == "P9001")
    assert "judge_config" not in stored_problem
    assert data["problem_judge_config"]["P9001"] == {"answer": "A", "score": 100}
    assert repository.get_problem("P9001").judge_config == {}
    assert repository.get_problem_judge_config("P9001")["answer"] == "A"


def test_sqlite_repository_stores_problem_test_data_metadata(tmp_path: Path) -> None:
    repository = sqlite_repository(tmp_path)
    uploaded_at = datetime.now(timezone.utc)
    metadata = ProblemTestData(
        problem_id="P1001",
        filename="cases.zip",
        object_key="testdata/P1001/hash.zip",
        storage_backend="local",
        bucket="gayoj-testdata",
        archive_format="zip",
        size_bytes=128,
        sha256="hash",
        file_count=2,
        input_files=1,
        output_files=1,
        case_count=1,
        case_names=["1"],
        uploaded_by="u-admin",
        uploaded_at=uploaded_at,
    )

    saved = repository.set_problem_test_data(metadata)

    assert saved.problem_id == "P1001"
    assert repository.get_problem_test_data("P1001") == metadata
    data = read_sqlite_snapshot(repository)
    assert data["problem_test_data"]["P1001"]["object_key"] == "testdata/P1001/hash.zip"


def test_sqlite_repository_records_problem_versions_and_restores_snapshots(tmp_path: Path) -> None:
    repository = sqlite_repository(tmp_path)
    problem = repository.get_problem("P1003")
    assert problem is not None
    problem.judge_config = repository.get_problem_judge_config(problem.id)

    version = repository.add_problem_version(problem, "u-admin", "update")
    changed = problem.model_copy(deep=True)
    changed.title = "二分查找适用条件（改动后）"
    changed.statement = "临时改动题面。"
    changed.judge_config = {"answer": "A", "score": 100}
    repository.update_problem(changed)

    restored = repository.restore_problem_version(problem.id, version.id)

    assert restored is not None
    assert restored.title == problem.title
    assert restored.statement == problem.statement
    assert repository.get_problem_judge_config(problem.id)["answer"] == "B"
    versions = repository.list_problem_versions(problem.id)
    assert versions[0].snapshot.judge_config["answer"] == "B"
    data = read_sqlite_snapshot(repository)
    stored_problem = next(item for item in data["problems"] if item["id"] == problem.id)
    assert "judge_config" not in stored_problem
    assert data["problem_versions"][0]["snapshot"]["judge_config"]["answer"] == "B"


def test_sqlite_repository_persists_updates_across_instances(tmp_path: Path) -> None:
    first = sqlite_repository(tmp_path)
    config = first.get_system_config()
    first.update_system_config({"site_name": "SQLite gayoj"})

    second = sqlite_repository(tmp_path, name="gayoj-test.sqlite3")

    assert config["site_name"] == "gayoj"
    assert second.get_system_config()["site_name"] == "SQLite gayoj"

