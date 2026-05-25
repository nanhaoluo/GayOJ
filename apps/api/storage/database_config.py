from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus


STORAGE_DIR = Path(__file__).resolve().parent
API_ROOT = STORAGE_DIR.parent
REPO_ROOT = API_ROOT.parents[1]

DEFAULT_STORAGE_BACKEND = "mysql"
DEFAULT_DEV_DB_JSON_PATH = STORAGE_DIR / "dev-db.json"
DEFAULT_SQLITE_DB_PATH = STORAGE_DIR / "gayoj.sqlite3"


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def _resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


@dataclass(frozen=True)
class DatabaseSettings:
    storage_backend: str
    dev_db_json_path: Path
    sqlite_db_path: Path
    sqlite_busy_timeout_ms: int
    sqlite_cache_enabled: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_charset: str
    mysql_url: str
    mysql_connect_timeout_seconds: int

    @property
    def mysql_dsn(self) -> str:
        if self.mysql_url:
            return self.mysql_url
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        database = quote_plus(self.mysql_database)
        return (
            f"mysql+pymysql://{user}:{password}@{self.mysql_host}:{self.mysql_port}/"
            f"{database}?charset={quote_plus(self.mysql_charset)}"
        )

    def cache_key(self) -> str:
        return "|".join(
            [
                self.storage_backend,
                str(self.dev_db_json_path),
                str(self.sqlite_db_path),
                str(self.sqlite_busy_timeout_ms),
                str(self.sqlite_cache_enabled),
                self.mysql_host,
                str(self.mysql_port),
                self.mysql_user,
                self.mysql_password,
                self.mysql_database,
                self.mysql_charset,
                self.mysql_url,
                str(self.mysql_connect_timeout_seconds),
            ]
        )


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings(
        storage_backend=_get_env("GAYOJ_STORAGE_BACKEND", DEFAULT_STORAGE_BACKEND).strip().lower(),
        dev_db_json_path=_resolve_path(_get_env("GAYOJ_DEV_DB_JSON_PATH", str(DEFAULT_DEV_DB_JSON_PATH))),
        sqlite_db_path=_resolve_path(_get_env("GAYOJ_SQLITE_PATH", str(DEFAULT_SQLITE_DB_PATH))),
        sqlite_busy_timeout_ms=_get_int_env("GAYOJ_SQLITE_BUSY_TIMEOUT_MS", 5000),
        sqlite_cache_enabled=_get_bool_env("GAYOJ_SQLITE_CACHE_ENABLED", True),
        mysql_host=_get_env("GAYOJ_MYSQL_HOST", "127.0.0.1"),
        mysql_port=_get_int_env("GAYOJ_MYSQL_PORT", 3306),
        mysql_user=_get_env("GAYOJ_MYSQL_USER", "gayoj"),
        mysql_password=_get_env("GAYOJ_MYSQL_PASSWORD", "gayoj"),
        mysql_database=_get_env("GAYOJ_MYSQL_DATABASE", "gayoj"),
        mysql_charset=_get_env("GAYOJ_MYSQL_CHARSET", "utf8mb4"),
        mysql_url=_get_env("GAYOJ_MYSQL_URL", ""),
        mysql_connect_timeout_seconds=_get_int_env("GAYOJ_MYSQL_CONNECT_TIMEOUT_SECONDS", 2),
    )


__all__ = [
    "API_ROOT",
    "DEFAULT_DEV_DB_JSON_PATH",
    "DEFAULT_SQLITE_DB_PATH",
    "DEFAULT_STORAGE_BACKEND",
    "DatabaseSettings",
    "REPO_ROOT",
    "STORAGE_DIR",
    "get_database_settings",
]
