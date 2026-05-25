from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from storage.database import FallbackStateDatabase, SqliteStateDatabase, create_state_database
from storage.database_config import DEFAULT_STORAGE_BACKEND, DatabaseSettings, get_database_settings


class MemoryStateDatabase:
    def __init__(self, label: str, payload: str | None = None, *, fail_reads: bool = False, fail_writes: bool = False):
        self.label = label
        self.payload = payload
        self.fail_reads = fail_reads
        self.fail_writes = fail_writes
        self.writes: list[str] = []

    def read_payload(self) -> str | None:
        if self.fail_reads:
            raise RuntimeError("read failed")
        return self.payload

    def write_payload(self, payload: str) -> None:
        if self.fail_writes:
            raise RuntimeError("write failed")
        self.payload = payload
        self.writes.append(payload)


def test_database_settings_default_to_mysql_with_sqlite_fallback() -> None:
    settings = get_database_settings()

    assert settings.storage_backend == DEFAULT_STORAGE_BACKEND == "mysql"
    assert settings.sqlite_db_path.name == "gayoj.sqlite3"
    assert settings.dev_db_json_path.name == "dev-db.json"
    assert settings.mysql_dsn.startswith("mysql+pymysql://")


def test_database_settings_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GAYOJ_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("GAYOJ_SQLITE_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("GAYOJ_SQLITE_BUSY_TIMEOUT_MS", "1234")
    monkeypatch.setenv("GAYOJ_SQLITE_CACHE_ENABLED", "false")
    monkeypatch.setenv("GAYOJ_MYSQL_URL", "mysql+pymysql://user:pass@db.example:3307/ctoj?charset=utf8mb4")

    settings = get_database_settings()

    assert settings.storage_backend == "sqlite"
    assert settings.sqlite_db_path == tmp_path / "state.sqlite3"
    assert settings.sqlite_busy_timeout_ms == 1234
    assert settings.sqlite_cache_enabled is False
    assert settings.mysql_dsn == "mysql+pymysql://user:pass@db.example:3307/ctoj?charset=utf8mb4"


def test_sqlite_state_database_parameterizes_state_key_and_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "safe.sqlite3"
    malicious_key = "default'; DROP TABLE app_state; --"
    malicious_payload = '{"text": "x' + "'; DROP TABLE app_state; --" + '"}'
    database = SqliteStateDatabase(db_path, state_key=malicious_key)

    database.write_payload(malicious_payload)

    assert database.read_payload() == malicious_payload
    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "app_state"),
        ).fetchone()
        assert table == ("app_state",)
        row = connection.execute(
            "SELECT payload FROM app_state WHERE state_key = ?",
            (malicious_key,),
        ).fetchone()
    assert row == (malicious_payload,)


@pytest.mark.parametrize("state_key", ["", "x" * 65, "bad\x00key"])
def test_sqlite_state_database_rejects_invalid_state_keys(tmp_path: Path, state_key: str) -> None:
    with pytest.raises(ValueError):
        SqliteStateDatabase(tmp_path / "invalid.sqlite3", state_key=state_key)


def test_create_state_database_falls_back_to_sqlite_when_mysql_is_unavailable(tmp_path: Path) -> None:
    settings = DatabaseSettings(
        storage_backend="mysql",
        dev_db_json_path=tmp_path / "dev-db.json",
        sqlite_db_path=tmp_path / "fallback.sqlite3",
        sqlite_busy_timeout_ms=5000,
        sqlite_cache_enabled=True,
        mysql_host="127.0.0.1",
        mysql_port=1,
        mysql_user="missing",
        mysql_password="missing",
        mysql_database="missing",
        mysql_charset="utf8mb4",
        mysql_url="",
        mysql_connect_timeout_seconds=1,
    )

    database = create_state_database(settings)

    assert isinstance(database, SqliteStateDatabase)
    database.write_payload('{"fallback": true}')
    assert database.read_payload() == '{"fallback": true}'


def test_fallback_state_database_writes_to_sqlite_after_primary_failure() -> None:
    primary = MemoryStateDatabase("mysql", fail_writes=True)
    fallback = MemoryStateDatabase("sqlite")
    database = FallbackStateDatabase(primary, fallback)

    database.write_payload('{"ok": true}')

    assert fallback.payload == '{"ok": true}'
    assert "unavailable" in database.label


def test_fallback_state_database_backfills_empty_primary_from_sqlite() -> None:
    primary = MemoryStateDatabase("mysql")
    fallback = MemoryStateDatabase("sqlite", '{"from": "sqlite"}')
    database = FallbackStateDatabase(primary, fallback)

    payload = database.read_payload()

    assert payload == '{"from": "sqlite"}'
    assert primary.payload == '{"from": "sqlite"}'
    assert primary.writes == ['{"from": "sqlite"}']


def test_storage_database_module_keeps_sql_queries_centralized() -> None:
    import storage.database as database_module

    public_names = set(database_module.__all__)
    assert {"SqliteStateDatabase", "MySqlStateDatabase", "FallbackStateDatabase", "create_state_database"} <= public_names
