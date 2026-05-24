from __future__ import annotations

import os
from pathlib import Path


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
)


def get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def parse_csv_env_value(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    if value in (None, ""):
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = get_env("GAYOJ_SECRET_KEY", "gayoj-dev-secret-change-me")
TOKEN_TTL_HOURS = get_int_env("GAYOJ_TOKEN_TTL_HOURS", 12)
OFFLINE_PACK_SECRET = get_env("GAYOJ_OFFLINE_PACK_SECRET", "gayoj-offline-dev-secret")
API_CORS_ORIGINS = parse_csv_env_value(os.getenv("GAYOJ_API_CORS_ORIGINS"), DEFAULT_CORS_ORIGINS)
JUDGE_QUEUE_BACKEND = get_env("GAYOJ_JUDGE_QUEUE_BACKEND", "json").lower()
JUDGE_QUEUE_TOPIC = get_env("GAYOJ_JUDGE_QUEUE_TOPIC", "gayoj.judge.submissions")
JUDGE_NODE_TOKEN = get_env("GAYOJ_JUDGE_NODE_TOKEN", "gayoj-dev-judge-node-token")
JUDGE_NODE_HEARTBEAT_TTL_SECONDS = get_int_env("GAYOJ_JUDGE_NODE_HEARTBEAT_TTL_SECONDS", 60)
REDIS_URL = get_env("GAYOJ_REDIS_URL", "")
KAFKA_BOOTSTRAP_SERVERS = get_env("GAYOJ_KAFKA_BOOTSTRAP_SERVERS", "")

API_ROOT = Path(__file__).resolve().parents[1]
OBJECT_STORAGE_BACKEND = get_env("GAYOJ_OBJECT_STORAGE_BACKEND", "local").lower()
OBJECT_STORAGE_BUCKET = get_env("GAYOJ_OBJECT_STORAGE_BUCKET", "gayoj-testdata")
LOCAL_OBJECT_STORAGE_DIR = get_env("GAYOJ_LOCAL_OBJECT_STORAGE_DIR", str(API_ROOT / "storage" / "objects"))
MINIO_ENDPOINT = get_env("GAYOJ_MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = get_env("GAYOJ_MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = get_env("GAYOJ_MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = get_env("GAYOJ_MINIO_SECURE", "false").lower() in {"1", "true", "yes"}

TESTDATA_MAX_ARCHIVE_BYTES = get_int_env("GAYOJ_TESTDATA_MAX_ARCHIVE_MB", 50) * 1024 * 1024
TESTDATA_MAX_UNCOMPRESSED_BYTES = get_int_env("GAYOJ_TESTDATA_MAX_UNCOMPRESSED_MB", 200) * 1024 * 1024
TESTDATA_MAX_FILES = get_int_env("GAYOJ_TESTDATA_MAX_FILES", 1000)
