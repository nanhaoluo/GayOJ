from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
CLI_PATH = ROOT / "tools" / "offline-cli" / "gayoj_offline.py"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db import Repository, SnapshotRepository, get_repository  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> Repository:
    return SnapshotRepository.sqlite(tmp_path / "gayoj-test.sqlite3")


@pytest.fixture()
def client(store: Repository) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client: TestClient):
    def login(username: str = "alice", password: str = "gayoj123") -> dict[str, str]:
        response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return login


@pytest.fixture(scope="session")
def offline_cli_module():
    spec = importlib.util.spec_from_file_location("gayoj_offline", CLI_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
