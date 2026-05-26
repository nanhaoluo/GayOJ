from __future__ import annotations

import sqlite3
import threading
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlparse

from .database_config import DatabaseSettings


MAX_SQLITE_BUSY_TIMEOUT_MS = 60_000
MAX_MYSQL_CONNECT_TIMEOUT_SECONDS = 30
HOT_COLLECTIONS = {
    "contests": "hot_contests",
    "submissions": "hot_submissions",
    "judge_queue_jobs": "hot_judge_queue_jobs",
    "clarifications": "hot_clarifications",
    "contest_announcements": "hot_contest_announcements",
    "contest_print_jobs": "hot_contest_print_jobs",
    "contest_balloons": "hot_contest_balloons",
    "judge_nodes": "hot_judge_nodes",
}


class StateDatabase(Protocol):
    label: str

    def read_payload(self) -> str | None: ...

    def write_payload(self, payload: str) -> None: ...

    def list_hot_items(
        self,
        collection: str,
        *,
        contest_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_hot_item(self, collection: str, item_id: str) -> dict[str, Any] | None: ...

    def upsert_hot_item(self, collection: str, item: dict[str, Any], *, sort_order: int = 0) -> None: ...

    def delete_hot_item(self, collection: str, item_id: str) -> None: ...

    def replace_hot_collection(self, collection: str, items: list[dict[str, Any]]) -> None: ...

    def replace_hot_collections(self, data: dict[str, Any]) -> None: ...


def _validate_state_key(state_key: str) -> str:
    if not state_key or len(state_key) > 64:
        raise ValueError("state_key must be between 1 and 64 characters.")
    if "\x00" in state_key:
        raise ValueError("state_key must not contain NUL bytes.")
    return state_key


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _hot_table(collection: str) -> str:
    try:
        return HOT_COLLECTIONS[collection]
    except KeyError as exc:
        raise ValueError(f"Unsupported hot collection: {collection}") from exc


def _hot_item_id(collection: str, item: dict[str, Any]) -> str:
    if collection == "contest_balloons":
        contest_id = str(item.get("contest_id") or "")
        user_id = str(item.get("user_id") or "")
        problem_id = str(item.get("problem_id") or "")
        return f"{contest_id}:{user_id}:{problem_id}"
    return str(item.get("id") or item.get("submission_id") or "")


def _hot_created_at(collection: str, item: dict[str, Any]) -> str:
    for key in {
        "contests": ("start_at", "created_at"),
        "submissions": ("created_at", "judged_at"),
        "judge_queue_jobs": ("created_at", "leased_at", "completed_at"),
        "clarifications": ("created_at", "answered_at"),
        "contest_announcements": ("created_at",),
        "contest_print_jobs": ("requested_at", "printed_at"),
        "contest_balloons": ("judged_at", "released_at"),
        "judge_nodes": ("last_heartbeat",),
    }[collection]:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _hot_row(collection: str, item: dict[str, Any], sort_order: int) -> tuple[Any, ...] | None:
    item_id = _hot_item_id(collection, item)
    if not item_id:
        return None
    payload = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    contest_id = str(item.get("id") or "") if collection == "contests" else str(item.get("contest_id") or "")
    return (
        item_id,
        payload,
        contest_id,
        str(item.get("user_id") or ""),
        str(item.get("problem_id") or ""),
        str(item.get("submission_id") or ""),
        str(item.get("status") or ""),
        str(item.get("language") or ""),
        int(item.get("priority", 0) or 0),
        _hot_created_at(collection, item),
        sort_order,
        _utc_timestamp(),
    )


def _loads_hot_payload(value: Any) -> dict[str, Any]:
    loaded = json.loads(str(value))
    return loaded if isinstance(loaded, dict) else {}


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
            self._ensure_hot_schema(connection)

    def _ensure_hot_schema(self, connection: sqlite3.Connection) -> None:
        for table in HOT_COLLECTIONS.values():
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    item_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    contest_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT '',
                    problem_id TEXT NOT NULL DEFAULT '',
                    submission_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            for index_name, columns in {
                f"idx_{table}_contest_created": "contest_id, created_at DESC, sort_order ASC",
                f"idx_{table}_contest_status": "contest_id, status, created_at DESC",
                f"idx_{table}_status_priority": "status, priority DESC, created_at ASC",
                f"idx_{table}_submission": "submission_id",
                f"idx_{table}_problem_user": "problem_id, user_id",
            }.items():
                connection.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})")

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

    def list_hot_items(
        self,
        collection: str,
        *,
        contest_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        table = _hot_table(collection)
        clauses: list[str] = []
        params: list[Any] = []
        if contest_id is not None:
            clauses.append("contest_id = ?")
            params.append(contest_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(max(1, int(limit)))
        sql = f"SELECT payload FROM {table}{where} ORDER BY sort_order ASC, created_at DESC, item_id ASC{limit_sql}"
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(sql, params).fetchall()
        return [_loads_hot_payload(row[0]) for row in rows]

    def get_hot_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        table = _hot_table(collection)
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(f"SELECT payload FROM {table} WHERE item_id = ?", (item_id,)).fetchone()
        return _loads_hot_payload(row[0]) if row else None

    def upsert_hot_item(self, collection: str, item: dict[str, Any], *, sort_order: int = 0) -> None:
        table = _hot_table(collection)
        row = _hot_row(collection, item, sort_order)
        if row is None:
            return
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    INSERT INTO {table} (
                        item_id, payload, contest_id, user_id, problem_id, submission_id,
                        status, language, priority, created_at, sort_order, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        payload = excluded.payload,
                        contest_id = excluded.contest_id,
                        user_id = excluded.user_id,
                        problem_id = excluded.problem_id,
                        submission_id = excluded.submission_id,
                        status = excluded.status,
                        language = excluded.language,
                        priority = excluded.priority,
                        created_at = excluded.created_at,
                        sort_order = excluded.sort_order,
                        updated_at = excluded.updated_at
                    """,
                    row,
                )

    def delete_hot_item(self, collection: str, item_id: str) -> None:
        table = _hot_table(collection)
        with self._lock:
            with self._connect() as connection:
                connection.execute(f"DELETE FROM {table} WHERE item_id = ?", (item_id,))

    def replace_hot_collection(self, collection: str, items: list[dict[str, Any]]) -> None:
        table = _hot_table(collection)
        rows = [row for index, item in enumerate(items) if (row := _hot_row(collection, item, index)) is not None]
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(f"DELETE FROM {table}")
                    connection.executemany(
                        f"""
                        INSERT INTO {table} (
                            item_id, payload, contest_id, user_id, problem_id, submission_id,
                            status, language, priority, created_at, sort_order, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise

    def replace_hot_collections(self, data: dict[str, Any]) -> None:
        for collection in HOT_COLLECTIONS:
            items = data.get(collection, [])
            self.replace_hot_collection(collection, items if isinstance(items, list) else [])


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
                self._ensure_hot_schema(cursor)

    def _ensure_hot_schema(self, cursor: Any) -> None:
        for table in HOT_COLLECTIONS.values():
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    item_id VARCHAR(160) PRIMARY KEY,
                    payload JSON NOT NULL,
                    contest_id VARCHAR(64) NOT NULL DEFAULT '',
                    user_id VARCHAR(128) NOT NULL DEFAULT '',
                    problem_id VARCHAR(64) NOT NULL DEFAULT '',
                    submission_id VARCHAR(64) NOT NULL DEFAULT '',
                    status VARCHAR(64) NOT NULL DEFAULT '',
                    language VARCHAR(32) NOT NULL DEFAULT '',
                    priority INT NOT NULL DEFAULT 0,
                    created_at VARCHAR(64) NOT NULL DEFAULT '',
                    sort_order INT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_{table}_contest_created (contest_id, created_at, sort_order),
                    INDEX idx_{table}_contest_status (contest_id, status, created_at),
                    INDEX idx_{table}_status_priority (status, priority, created_at),
                    INDEX idx_{table}_submission (submission_id),
                    INDEX idx_{table}_problem_user (problem_id, user_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )

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

    def list_hot_items(
        self,
        collection: str,
        *,
        contest_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        table = _hot_table(collection)
        clauses: list[str] = []
        params: list[Any] = []
        if contest_id is not None:
            clauses.append("contest_id = %s")
            params.append(contest_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT %s"
            params.append(max(1, int(limit)))
        sql = f"SELECT payload FROM {table}{where} ORDER BY sort_order ASC, created_at DESC, item_id ASC{limit_sql}"
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, tuple(params))
                    rows = cursor.fetchall()
        return [_loads_hot_payload(row[0]) for row in rows]

    def get_hot_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        table = _hot_table(collection)
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT payload FROM {table} WHERE item_id = %s", (item_id,))
                    row = cursor.fetchone()
        return _loads_hot_payload(row[0]) if row else None

    def upsert_hot_item(self, collection: str, item: dict[str, Any], *, sort_order: int = 0) -> None:
        table = _hot_table(collection)
        row = _hot_row(collection, item, sort_order)
        if row is None:
            return
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {table} (
                            item_id, payload, contest_id, user_id, problem_id, submission_id,
                            status, language, priority, created_at, sort_order, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            payload = VALUES(payload),
                            contest_id = VALUES(contest_id),
                            user_id = VALUES(user_id),
                            problem_id = VALUES(problem_id),
                            submission_id = VALUES(submission_id),
                            status = VALUES(status),
                            language = VALUES(language),
                            priority = VALUES(priority),
                            created_at = VALUES(created_at),
                            sort_order = VALUES(sort_order),
                            updated_at = VALUES(updated_at)
                        """,
                        row,
                    )

    def delete_hot_item(self, collection: str, item_id: str) -> None:
        table = _hot_table(collection)
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM {table} WHERE item_id = %s", (item_id,))

    def replace_hot_collection(self, collection: str, items: list[dict[str, Any]]) -> None:
        table = _hot_table(collection)
        rows = [row for index, item in enumerate(items) if (row := _hot_row(collection, item, index)) is not None]
        with self._lock:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("START TRANSACTION")
                    try:
                        cursor.execute(f"DELETE FROM {table}")
                        if rows:
                            cursor.executemany(
                                f"""
                                INSERT INTO {table} (
                                    item_id, payload, contest_id, user_id, problem_id, submission_id,
                                    status, language, priority, created_at, sort_order, updated_at
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                rows,
                            )
                        cursor.execute("COMMIT")
                    except Exception:
                        cursor.execute("ROLLBACK")
                        raise

    def replace_hot_collections(self, data: dict[str, Any]) -> None:
        for collection in HOT_COLLECTIONS:
            items = data.get(collection, [])
            self.replace_hot_collection(collection, items if isinstance(items, list) else [])


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

    def list_hot_items(
        self,
        collection: str,
        *,
        contest_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            if self._primary_available:
                try:
                    return self.primary.list_hot_items(collection, contest_id=contest_id, status=status, limit=limit)
                except Exception:
                    self._primary_available = False
            return self.fallback.list_hot_items(collection, contest_id=contest_id, status=status, limit=limit)

    def get_hot_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self._primary_available:
                try:
                    return self.primary.get_hot_item(collection, item_id)
                except Exception:
                    self._primary_available = False
            return self.fallback.get_hot_item(collection, item_id)

    def upsert_hot_item(self, collection: str, item: dict[str, Any], *, sort_order: int = 0) -> None:
        with self._lock:
            if self._primary_available:
                try:
                    self.primary.upsert_hot_item(collection, item, sort_order=sort_order)
                except Exception:
                    self._primary_available = False
            self.fallback.upsert_hot_item(collection, item, sort_order=sort_order)

    def delete_hot_item(self, collection: str, item_id: str) -> None:
        with self._lock:
            if self._primary_available:
                try:
                    self.primary.delete_hot_item(collection, item_id)
                except Exception:
                    self._primary_available = False
            self.fallback.delete_hot_item(collection, item_id)

    def replace_hot_collection(self, collection: str, items: list[dict[str, Any]]) -> None:
        with self._lock:
            if self._primary_available:
                try:
                    self.primary.replace_hot_collection(collection, items)
                except Exception:
                    self._primary_available = False
            self.fallback.replace_hot_collection(collection, items)

    def replace_hot_collections(self, data: dict[str, Any]) -> None:
        with self._lock:
            if self._primary_available:
                try:
                    self.primary.replace_hot_collections(data)
                except Exception:
                    self._primary_available = False
            self.fallback.replace_hot_collections(data)

    def _sync_fallback(self, payload: str) -> None:
        if payload == self._last_synced_payload:
            return
        try:
            if self.fallback.read_payload() != payload:
                self.fallback.write_payload(payload)
                try:
                    loaded = json.loads(payload)
                    if isinstance(loaded, dict):
                        self.fallback.replace_hot_collections(loaded)
                except Exception:
                    pass
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
    "HOT_COLLECTIONS",
    "MySqlStateDatabase",
    "SqliteStateDatabase",
    "StateDatabase",
    "create_mysql_database",
    "create_sqlite_database",
    "create_state_database",
]
