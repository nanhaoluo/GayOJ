from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlparse

from .database_config import DatabaseSettings


MAX_SQLITE_BUSY_TIMEOUT_MS = 60_000
MAX_MYSQL_CONNECT_TIMEOUT_SECONDS = 30


class StateDatabase(Protocol):
    label: str

    def read_payload(self) -> str | None: ...

    def write_payload(self, payload: str) -> None: ...


def _validate_state_key(state_key: str) -> str:
    if not state_key or len(state_key) > 64:
        raise ValueError("state_key must be between 1 and 64 characters.")
    if "\x00" in state_key:
        raise ValueError("state_key must not contain NUL bytes.")
    return state_key


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class SqliteStateDatabase:
    """SQLite fallback layer with WAL, busy timeout, and in-process payload cache."""

    def __init__(
        self,
        path: Path,
        *,
        state_key: str = "default",
        busy_timeout_ms: int = 5000,
        cache_enabled: bool = True,
    ) -> None:
        self.path = path
        self.state_key = _validate_state_key(state_key)
        self.busy_timeout_ms = max(0, min(int(busy_timeout_ms), MAX_SQLITE_BUSY_TIMEOUT_MS))
        self.cache_enabled = cache_enabled
        self._lock = threading.RLock()
        self._cached_payload: str | None = None
        self._cached_version: int | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def label(self) -> str:
        return f"sqlite:{self.path}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=max(1.0, self.busy_timeout_ms / 1000), isolation_level=None)
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms:d}")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    state_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def read_payload(self) -> str | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT version FROM app_state WHERE state_key = ?",
                    (self.state_key,),
                ).fetchone()
                if row is None:
                    self._cached_payload = None
                    self._cached_version = None
                    return None

                version = int(row[0])
                if self.cache_enabled and self._cached_payload is not None and self._cached_version == version:
                    return self._cached_payload

                payload_row = connection.execute(
                    "SELECT payload, version FROM app_state WHERE state_key = ?",
                    (self.state_key,),
                ).fetchone()
                if payload_row is None:
                    self._cached_payload = None
                    self._cached_version = None
                    return None

                payload = str(payload_row[0])
                self._cached_payload = payload
                self._cached_version = int(payload_row[1])
                return payload

    def write_payload(self, payload: str) -> None:
        with self._lock:
            updated_at = _utc_timestamp()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        INSERT INTO app_state (state_key, payload, version, updated_at)
                        VALUES (?, ?, 1, ?)
                        ON CONFLICT(state_key) DO UPDATE SET
                            payload = excluded.payload,
                            version = app_state.version + 1,
                            updated_at = excluded.updated_at
                        """,
                        (self.state_key, payload, updated_at),
                    )
                    version_row = connection.execute(
                        "SELECT version FROM app_state WHERE state_key = ?",
                        (self.state_key,),
                    ).fetchone()
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise

                self._cached_payload = payload
                self._cached_version = int(version_row[0]) if version_row else None


class MySqlStateDatabase:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        charset: str,
        connect_timeout_seconds: int,
        state_key: str = "default",
        cache_enabled: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connect_timeout_seconds = max(1, min(int(connect_timeout_seconds), MAX_MYSQL_CONNECT_TIMEOUT_SECONDS))
        self.state_key = _validate_state_key(state_key)
        self.cache_enabled = cache_enabled
        self._lock = threading.RLock()
        self._cached_payload: str | None = None
        self._cached_version: int | None = None
        self._pymysql = self._load_pymysql()
        self._ensure_schema()

    @property
    def label(self) -> str:
        return f"mysql:{self.user}@{self.host}:{self.port}/{self.database}"

    @staticmethod
    def _load_pymysql() -> Any:
        try:
            import pymysql  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("PyMySQL is required for MySQL storage.") from exc
        return pymysql

    def _connect(self) -> Any:
        return self._pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset=self.charset,
            connect_timeout=self.connect_timeout_seconds,
            read_timeout=self.connect_timeout_seconds,
            write_timeout=self.connect_timeout_seconds,
            autocommit=True,
        )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_state (
                        state_key VARCHAR(64) PRIMARY KEY,
                        payload LONGTEXT NOT NULL,
                        version BIGINT NOT NULL DEFAULT 1,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute("SHOW COLUMNS FROM app_state LIKE 'version'")
                if cursor.fetchone() is None:
                    cursor.execute("ALTER TABLE app_state ADD COLUMN version BIGINT NOT NULL DEFAULT 1")

    def read_payload(self) -> str | None:
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT version FROM app_state WHERE state_key = %s", (self.state_key,))
                    row = cursor.fetchone()
                    if row is None:
                        self._cached_payload = None
                        self._cached_version = None
                        return None

                    version = int(row[0])
                    if self.cache_enabled and self._cached_payload is not None and self._cached_version == version:
                        return self._cached_payload

                    cursor.execute("SELECT payload, version FROM app_state WHERE state_key = %s", (self.state_key,))
                    payload_row = cursor.fetchone()
                    if payload_row is None:
                        self._cached_payload = None
                        self._cached_version = None
                        return None

                    payload = str(payload_row[0])
                    self._cached_payload = payload
                    self._cached_version = int(payload_row[1])
                    return payload

    def write_payload(self, payload: str) -> None:
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO app_state (state_key, payload, version, updated_at)
                        VALUES (%s, %s, 1, %s)
                        ON DUPLICATE KEY UPDATE
                            payload = VALUES(payload),
                            version = version + 1,
                            updated_at = VALUES(updated_at)
                        """,
                        (self.state_key, payload, _utc_timestamp()),
                    )
                    cursor.execute("SELECT version FROM app_state WHERE state_key = %s", (self.state_key,))
                    version_row = cursor.fetchone()
                    self._cached_payload = payload
                    self._cached_version = int(version_row[0]) if version_row else None


class FallbackStateDatabase:
    def __init__(self, primary: StateDatabase, fallback: StateDatabase) -> None:
        self.primary = primary
        self.fallback = fallback
        self._primary_available = True
        self._lock = threading.RLock()
        self._last_synced_payload: str | None = None

    @property
    def label(self) -> str:
        status = "active" if self._primary_available else "unavailable"
        return f"{self.primary.label} ({status}); fallback={self.fallback.label}"

    def read_payload(self) -> str | None:
        with self._lock:
            if self._primary_available:
                try:
                    payload = self.primary.read_payload()
                    if payload is not None:
                        self._sync_fallback(payload)
                        return payload
                    fallback_payload = self.fallback.read_payload()
                    if fallback_payload is not None:
                        self.primary.write_payload(fallback_payload)
                        self._last_synced_payload = fallback_payload
                        return fallback_payload
                    return payload
                except Exception:
                    self._primary_available = False
            return self.fallback.read_payload()

    def write_payload(self, payload: str) -> None:
        with self._lock:
            if self._primary_available:
                try:
                    self.primary.write_payload(payload)
                except Exception:
                    self._primary_available = False
            self.fallback.write_payload(payload)
            self._last_synced_payload = payload

    def _sync_fallback(self, payload: str) -> None:
        if payload == self._last_synced_payload:
            return
        try:
            if self.fallback.read_payload() != payload:
                self.fallback.write_payload(payload)
            self._last_synced_payload = payload
        except Exception:
            return


def create_sqlite_database(settings: DatabaseSettings) -> SqliteStateDatabase:
    return SqliteStateDatabase(
        settings.sqlite_db_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        cache_enabled=settings.sqlite_cache_enabled,
    )


def create_mysql_database(settings: DatabaseSettings) -> MySqlStateDatabase:
    mysql_url = settings.mysql_url.strip()
    if mysql_url:
        parsed = urlparse(mysql_url.replace("mysql+pymysql://", "mysql://", 1))
        query = parse_qs(parsed.query)
        return MySqlStateDatabase(
            host=parsed.hostname or settings.mysql_host,
            port=parsed.port or settings.mysql_port,
            user=unquote(parsed.username or settings.mysql_user),
            password=unquote(parsed.password or settings.mysql_password),
            database=unquote(parsed.path.lstrip("/") or settings.mysql_database),
            charset=query.get("charset", [settings.mysql_charset])[0],
            connect_timeout_seconds=settings.mysql_connect_timeout_seconds,
            cache_enabled=settings.sqlite_cache_enabled,
        )
    return MySqlStateDatabase(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset=settings.mysql_charset,
        connect_timeout_seconds=settings.mysql_connect_timeout_seconds,
        cache_enabled=settings.sqlite_cache_enabled,
    )


def create_state_database(settings: DatabaseSettings) -> StateDatabase:
    if settings.storage_backend == "sqlite":
        return create_sqlite_database(settings)
    if settings.storage_backend != "mysql":
        raise RuntimeError(
            f"Unsupported GAYOJ_STORAGE_BACKEND={settings.storage_backend!r}. "
            "Use 'mysql' or 'sqlite'."
        )
    fallback = create_sqlite_database(settings)
    try:
        primary = create_mysql_database(settings)
    except Exception:
        return fallback
    return FallbackStateDatabase(primary, fallback)


__all__ = [
    "FallbackStateDatabase",
    "MySqlStateDatabase",
    "SqliteStateDatabase",
    "StateDatabase",
    "create_mysql_database",
    "create_sqlite_database",
    "create_state_database",
]
