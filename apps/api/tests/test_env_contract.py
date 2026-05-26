from __future__ import annotations

import json
from pathlib import Path

from app.config import DEFAULT_CORS_ORIGINS, parse_csv_env_value


ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.yml"
PACKAGE_JSON = ROOT / "package.json"
GITIGNORE = ROOT / ".gitignore"


def parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_env_example_documents_required_local_and_compose_keys() -> None:
    assert ENV_EXAMPLE.exists()
    values = parse_env_example()

    required_keys = {
        "GAYOJ_ENV",
        "GAYOJ_SECRET_KEY",
        "GAYOJ_TOKEN_TTL_HOURS",
        "GAYOJ_OFFLINE_PACK_SECRET",
        "GAYOJ_OFFLINE_PACK_TTL_HOURS",
        "GAYOJ_API_CORS_ORIGINS",
        "GAYOJ_STORAGE_BACKEND",
        "GAYOJ_DEV_DB_JSON_PATH",
        "GAYOJ_SQLITE_PATH",
        "GAYOJ_SQLITE_BUSY_TIMEOUT_MS",
        "GAYOJ_SQLITE_CACHE_ENABLED",
        "GAYOJ_MYSQL_HOST",
        "GAYOJ_MYSQL_PORT",
        "GAYOJ_MYSQL_USER",
        "GAYOJ_MYSQL_PASSWORD",
        "GAYOJ_MYSQL_DATABASE",
        "GAYOJ_MYSQL_CHARSET",
        "GAYOJ_MYSQL_URL",
        "GAYOJ_MYSQL_CONNECT_TIMEOUT_SECONDS",
        "GAYOJ_PRINT_BACKEND",
        "GAYOJ_PRINT_SPOOL_DIR",
        "GAYOJ_PRINT_DEFAULT_PRINTER",
        "GAYOJ_PRINT_COMMAND",
        "GAYOJ_PRINT_COMMAND_TIMEOUT_SECONDS",
        "GAYOJ_DATABASE_URL",
        "GAYOJ_API_HOST",
        "GAYOJ_API_PORT",
        "GAYOJ_API_RELOAD",
        "GAYOJ_WEB_HOST",
        "GAYOJ_WEB_PORT",
        "GAYOJ_WEB_PREVIEW_PORT",
        "VITE_DEV_PROXY_TARGET",
        "VITE_API_BASE_URL",
        "GAYOJ_API_BASE",
        "GAYOJ_HEALTH_URL",
        "GAYOJ_CLI_API_BASE",
        "GAYOJ_TOKEN",
        "GAYOJ_COMPOSE_API_PORT",
        "GAYOJ_COMPOSE_WEB_PORT",
    }

    assert required_keys <= values.keys()
    assert values["VITE_API_BASE_URL"] == "/api/v1"
    assert values["GAYOJ_STORAGE_BACKEND"] == "mysql"
    assert values["GAYOJ_PRINT_BACKEND"] == "file"
    assert values["GAYOJ_SQLITE_PATH"].endswith("gayoj.sqlite3")
    assert values["GAYOJ_TOKEN"] == ""
    assert "change-me-in-production" not in ENV_EXAMPLE.read_text(encoding="utf-8")


def test_docker_compose_uses_documented_environment_keys() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    for key in [
        "GAYOJ_ENV",
        "GAYOJ_SECRET_KEY",
        "GAYOJ_TOKEN_TTL_HOURS",
        "GAYOJ_OFFLINE_PACK_SECRET",
        "GAYOJ_OFFLINE_PACK_TTL_HOURS",
        "GAYOJ_API_CORS_ORIGINS",
        "GAYOJ_STORAGE_BACKEND",
        "GAYOJ_DEV_DB_JSON_PATH",
        "GAYOJ_SQLITE_PATH",
        "GAYOJ_SQLITE_BUSY_TIMEOUT_MS",
        "GAYOJ_SQLITE_CACHE_ENABLED",
        "GAYOJ_MYSQL_HOST",
        "GAYOJ_MYSQL_PORT",
        "GAYOJ_MYSQL_USER",
        "GAYOJ_MYSQL_PASSWORD",
        "GAYOJ_MYSQL_DATABASE",
        "GAYOJ_MYSQL_CHARSET",
        "GAYOJ_MYSQL_URL",
        "GAYOJ_MYSQL_CONNECT_TIMEOUT_SECONDS",
        "GAYOJ_PRINT_BACKEND",
        "GAYOJ_PRINT_SPOOL_DIR",
        "GAYOJ_PRINT_DEFAULT_PRINTER",
        "GAYOJ_PRINT_COMMAND",
        "GAYOJ_PRINT_COMMAND_TIMEOUT_SECONDS",
        "GAYOJ_COMPOSE_API_PORT",
        "GAYOJ_COMPOSE_WEB_PORT",
        "VITE_API_BASE_URL",
    ]:
        assert "${" + key in compose or f"{key}:" in compose


def test_package_scripts_route_dev_api_through_env_loader() -> None:
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["scripts"]

    assert "scripts/dev-api.ps1" in scripts["dev:api"]
    assert "--host 127.0.0.1" not in scripts["dev:web"]
    assert "--port 5173" not in scripts["dev:web"]


def test_gitignore_excludes_local_env_but_not_example() -> None:
    ignored = set(GITIGNORE.read_text(encoding="utf-8").splitlines())

    assert ".env" in ignored
    assert ".env.example" not in ignored
    assert "apps/api/storage/*.sqlite3" in ignored
    assert "apps/api/storage/*.db" in ignored
    assert "apps/api/storage/print-spool/" in ignored


def test_cors_csv_parser_defaults_and_trimming() -> None:
    assert parse_csv_env_value(None, DEFAULT_CORS_ORIGINS) == list(DEFAULT_CORS_ORIGINS)
    assert parse_csv_env_value(" http://a.test,https://b.test ,, ") == [
        "http://a.test",
        "https://b.test",
    ]
