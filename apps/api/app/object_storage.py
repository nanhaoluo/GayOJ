from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol

from .config import (
    LOCAL_OBJECT_STORAGE_DIR,
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    OBJECT_STORAGE_BACKEND,
    OBJECT_STORAGE_BUCKET,
)


class ObjectNotFoundError(FileNotFoundError):
    pass


class ObjectStorage(Protocol):
    backend: str
    bucket: str

    def put_bytes(self, object_key: str, payload: bytes, content_type: str = "application/octet-stream") -> None: ...

    def get_bytes(self, object_key: str) -> bytes: ...


def _safe_object_path(root: Path, object_key: str) -> Path:
    path = PurePosixPath(object_key.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        raise ValueError("Invalid object key")
    if any(part in {"", ".", ".."} or ":" in part for part in path.parts):
        raise ValueError("Invalid object key")
    return root.joinpath(*path.parts)


class LocalObjectStorage:
    backend = "local"

    def __init__(self, root: Path | str = LOCAL_OBJECT_STORAGE_DIR, bucket: str = OBJECT_STORAGE_BUCKET):
        self.root = Path(root)
        self.bucket = bucket
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, object_key: str, payload: bytes, content_type: str = "application/octet-stream") -> None:
        path = _safe_object_path(self.root, object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def get_bytes(self, object_key: str) -> bytes:
        path = _safe_object_path(self.root, object_key)
        if not path.exists() or not path.is_file():
            raise ObjectNotFoundError(object_key)
        return path.read_bytes()


class MinioObjectStorage:
    backend = "minio"

    def __init__(
        self,
        endpoint: str = MINIO_ENDPOINT,
        access_key: str = MINIO_ACCESS_KEY,
        secret_key: str = MINIO_SECRET_KEY,
        bucket: str = OBJECT_STORAGE_BUCKET,
        secure: bool = MINIO_SECURE,
    ):
        try:
            from minio import Minio
            from minio.error import S3Error
        except ImportError as exc:
            raise RuntimeError("MinIO storage requires the minio Python package") from exc

        self._s3_error = S3Error
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put_bytes(self, object_key: str, payload: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(payload),
            length=len(payload),
            content_type=content_type,
        )

    def get_bytes(self, object_key: str) -> bytes:
        response = None
        try:
            response = self.client.get_object(self.bucket, object_key)
            return response.read()
        except self._s3_error as exc:
            if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchBucket"}:
                raise ObjectNotFoundError(object_key) from exc
            raise
        finally:
            if response is not None:
                response.close()
                response.release_conn()


@lru_cache
def get_object_storage() -> ObjectStorage:
    if OBJECT_STORAGE_BACKEND == "local":
        return LocalObjectStorage()
    if OBJECT_STORAGE_BACKEND == "minio":
        return MinioObjectStorage()
    raise RuntimeError(f"Unsupported object storage backend: {OBJECT_STORAGE_BACKEND}")
