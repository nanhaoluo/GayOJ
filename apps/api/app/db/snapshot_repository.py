from __future__ import annotations

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
            else:
                data = json.loads(payload)
                if not isinstance(data, dict):
                    data = seed_data()
            data, changed = self._normalize_data(data)
            if changed or payload is None:
                self._write(data)
            return data

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.database.write_payload(json.dumps(data, ensure_ascii=False, indent=2))


def create_snapshot_repository(settings: DatabaseSettings) -> SnapshotRepository:
    return SnapshotRepository.from_settings(settings)


__all__ = ["SnapshotRepository", "create_snapshot_repository"]
