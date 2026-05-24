from __future__ import annotations

from ..store import get_store as _get_json_store
from .json_repository import JsonRepository, create_json_repository, now, seed_data
from .repository import Repository


def get_repository() -> Repository:
    return _get_json_store()


__all__ = [
    "JsonRepository",
    "Repository",
    "create_json_repository",
    "get_repository",
    "now",
    "seed_data",
]
