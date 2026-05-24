from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.object_storage import LocalObjectStorage, get_object_storage


def code_problem_payload(title: str = "P3-04 测试数据题") -> dict[str, object]:
    return {
        "title": title,
        "type": "code",
        "difficulty": "入门",
        "tags": ["P3", "测试数据"],
        "statement": "读取两个整数并输出和。",
        "input_format": "一行两个整数。",
        "output_format": "一个整数。",
        "samples": [{"input": "1 2", "output": "3"}],
        "time_limit_ms": 1000,
        "memory_limit_mb": 128,
        "judge_config": {"mode": "standard"},
    }


def blank_problem_payload() -> dict[str, object]:
    return {
        "title": "P3-04 非代码题",
        "type": "blank",
        "difficulty": "基础",
        "tags": ["P3"],
        "statement": "完全图 K_n 的边数？",
        "blanks": [{"key": "edge_formula", "label": "边数公式", "score": 100}],
        "judge_config": {
            "answers": {"edge_formula": ["n(n-1)/2"]},
            "scores": {"edge_formula": 100},
        },
    }


def zip_payload(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def install_object_storage_override(tmp_path: Path) -> LocalObjectStorage:
    storage = LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[get_object_storage] = lambda: storage
    return storage


def test_code_problem_testdata_upload_validates_stores_and_downloads(
    client: TestClient,
    auth_headers,
    store,
    tmp_path: Path,
) -> None:
    install_object_storage_override(tmp_path)
    created = client.post("/api/v1/admin/problems", headers=auth_headers("admin"), json=code_problem_payload())
    assert created.status_code == 200, created.text
    problem_id = created.json()["id"]

    payload = zip_payload({"cases/1.in": "1 2\n", "cases/1.out": "3\n"})
    uploaded = client.post(
        f"/api/v1/admin/problems/{problem_id}/testdata",
        headers=auth_headers("admin"),
        files={"file": ("cases.zip", payload, "application/zip")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["problem_id"] == problem_id
    assert body["filename"] == "cases.zip"
    assert body["case_count"] == 1
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["object_key"].startswith(f"testdata/{problem_id}/")

    public_detail = client.get(f"/api/v1/problems/{problem_id}")
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()
    assert "test_data" not in public_detail.json()

    admin_detail = client.get(f"/api/v1/admin/problems/{problem_id}", headers=auth_headers("admin"))
    assert admin_detail.status_code == 200
    assert admin_detail.json()["test_data"]["sha256"] == body["sha256"]

    downloaded = client.get(f"/api/v1/admin/problems/{problem_id}/testdata/download", headers=auth_headers("admin"))
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == payload
    assert downloaded.headers["x-content-sha256"] == body["sha256"]

    judge_config = store.get_problem_judge_config(problem_id)
    assert judge_config["testdata_ref"] == body["object_key"]
    assert judge_config["testdata_sha256"] == body["sha256"]

    submission = client.post(
        f"/api/v1/problems/{problem_id}/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print(sum(map(int, input().split())))\n"},
    )
    assert submission.status_code == 200, submission.text
    assert submission.json()["status"] == "queued"
    assert submission.json()["judged_at"] is None


def test_testdata_upload_requires_problem_manager_and_code_problem(
    client: TestClient,
    auth_headers,
    tmp_path: Path,
) -> None:
    install_object_storage_override(tmp_path)
    code = client.post("/api/v1/admin/problems", headers=auth_headers("admin"), json=code_problem_payload())
    blank = client.post("/api/v1/admin/problems", headers=auth_headers("admin"), json=blank_problem_payload())
    assert code.status_code == 200, code.text
    assert blank.status_code == 200, blank.text
    payload = zip_payload({"1.in": "1 2\n", "1.out": "3\n"})

    forbidden = client.post(
        f"/api/v1/admin/problems/{code.json()['id']}/testdata",
        headers=auth_headers("alice"),
        files={"file": ("cases.zip", payload, "application/zip")},
    )
    assert forbidden.status_code == 403

    wrong_type = client.post(
        f"/api/v1/admin/problems/{blank.json()['id']}/testdata",
        headers=auth_headers("admin"),
        files={"file": ("cases.zip", payload, "application/zip")},
    )
    assert wrong_type.status_code == 400


def test_testdata_upload_rejects_invalid_zip_shapes(
    client: TestClient,
    auth_headers,
    tmp_path: Path,
) -> None:
    install_object_storage_override(tmp_path)
    created = client.post("/api/v1/admin/problems", headers=auth_headers("admin"), json=code_problem_payload())
    assert created.status_code == 200, created.text
    problem_id = created.json()["id"]

    not_zip = client.post(
        f"/api/v1/admin/problems/{problem_id}/testdata",
        headers=auth_headers("admin"),
        files={"file": ("cases.zip", b"not-a-zip", "application/zip")},
    )
    assert not_zip.status_code == 400

    traversal = client.post(
        f"/api/v1/admin/problems/{problem_id}/testdata",
        headers=auth_headers("admin"),
        files={"file": ("cases.zip", zip_payload({"../1.in": "1\n", "1.out": "1\n"}), "application/zip")},
    )
    assert traversal.status_code == 400

    missing_output = client.post(
        f"/api/v1/admin/problems/{problem_id}/testdata",
        headers=auth_headers("admin"),
        files={"file": ("cases.zip", zip_payload({"1.in": "1\n"}), "application/zip")},
    )
    assert missing_output.status_code == 400
