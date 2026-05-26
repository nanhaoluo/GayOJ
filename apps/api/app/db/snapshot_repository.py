from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from ..store import Store, seed_data
from storage.database import StateDatabase, SqliteStateDatabase, create_state_database
from storage.database_config import DatabaseSettings


class SnapshotRepository(Store):
    """Repository adapter that stores the normalized app state through storage.database."""

    def __init__(self, database: StateDatabase, *, seed_path: Path | None = None) -> None:
        self.path = seed_path or Path("<database-state>")
        self.database = database
        self._lock = threading.RLock()
        self._cached_payload: str | None = None
        self._cached_data: dict[str, Any] | None = None
        self._ensure_seeded()

    @classmethod
    def from_settings(cls, settings: DatabaseSettings) -> "SnapshotRepository":
        return cls(create_state_database(settings), seed_path=settings.dev_db_json_path)

    @classmethod
    def sqlite(
        cls,
        path: Path,
        *,
        seed_path: Path | None = None,
        busy_timeout_ms: int = 5000,
        cache_enabled: bool = True,
    ) -> "SnapshotRepository":
        return cls(
            SqliteStateDatabase(
                path,
                busy_timeout_ms=busy_timeout_ms,
                cache_enabled=cache_enabled,
            ),
            seed_path=seed_path,
        )

    def _ensure_seeded(self) -> None:
        with self._lock:
            if self.database.read_payload() is not None:
                return
            data = self._load_seed_data()
            data, _changed = self._normalize_data(data)
            self._write(data)

    def _load_seed_data(self) -> dict[str, Any]:
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        return seed_data()

    def _read(self) -> dict[str, Any]:
        with self._lock:
            payload = self.database.read_payload()
            if payload is None:
                data = self._load_seed_data()
                data, _changed = self._normalize_data(data)
                self._write(data)
                return copy.deepcopy(data)
            if self._cached_data is not None and self._cached_payload == payload:
                return copy.deepcopy(self._cached_data)
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = seed_data()
            if not isinstance(data, dict):
                data = seed_data()
            data, changed = self._normalize_data(data)
            if changed:
                self._write(data)
                return copy.deepcopy(data)
            self._cache_snapshot(payload, data)
            return copy.deepcopy(data)

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            self.database.write_payload(payload)
            self._cache_snapshot(payload, data)

    def _cache_snapshot(self, payload: str, data: dict[str, Any]) -> None:
        self._cached_payload = payload
        self._cached_data = copy.deepcopy(data)


def create_snapshot_repository(settings: DatabaseSettings) -> SnapshotRepository:
    return SnapshotRepository.from_settings(settings)


__all__ = ["SnapshotRepository", "create_snapshot_repository"]
