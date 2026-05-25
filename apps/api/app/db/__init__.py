from __future__ import annotations

from ..store import now, seed_data
from .repository import Repository
from .snapshot_repository import SnapshotRepository, create_snapshot_repository
from storage.database_config import get_database_settings


_repository_cache: dict[str, Repository] = {}


def create_repository() -> Repository:
    settings = get_database_settings()
    return create_snapshot_repository(settings)


def get_repository() -> Repository:
    settings = get_database_settings()
    key = settings.cache_key()
    repository = _repository_cache.get(key)
    if repository is None:
        repository = create_repository()
        _repository_cache.clear()
        _repository_cache[key] = repository
    return repository


__all__ = [
    "Repository",
    "SnapshotRepository",
    "create_repository",
    "create_snapshot_repository",
    "get_repository",
    "now",
    "seed_data",
]
