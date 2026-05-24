from __future__ import annotations

from pathlib import Path

from ..store import STORAGE_PATH, Store, now, seed_data
from .repository import Repository


JsonRepository = Store


def create_json_repository(path: Path | None = None) -> Repository:
    return JsonRepository(path or STORAGE_PATH)


__all__ = ["JsonRepository", "create_json_repository", "now", "seed_data"]
