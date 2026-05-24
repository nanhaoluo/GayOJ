from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from .config import SECRET_KEY, TOKEN_TTL_HOURS
from .models import PublicUser, Role, User
from .rbac import permission_codes_for_role, role_has_permissions
from .db import Repository, get_repository


ACCOUNT_DISABLED_DETAIL = "Account is disabled"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, digest = encoded.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(hash_password(password, salt), encoded)


def _config_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def validate_password_policy(password: str, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    min_length = _config_int(config, "password_min_length", 6, 1, 128)
    if len(password) < min_length:
        errors.append(f"Must be at least {min_length} characters long")
    if bool(config.get("password_require_letter", True)) and not any(ch.isalpha() for ch in password):
        errors.append("Must contain at least one letter")
    if bool(config.get("password_require_digit", True)) and not any(ch.isdigit() for ch in password):
        errors.append("Must contain at least one digit")
    return errors


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    payload_data = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(SECRET_KEY.encode(), payload_data.encode(), hashlib.sha256).digest()
    return f"{payload_data}.{_b64(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload_data, signature_data = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    expected = _b64(hmac.new(SECRET_KEY.encode(), payload_data.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature_data):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
    payload = json.loads(_unb64(payload_data))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def public_user(user: User) -> PublicUser:
    return PublicUser(
        **user.model_dump(exclude={"password_hash"}),
        permissions=permission_codes_for_role(user.role),
    )


def require_active_user(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
    if user.disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCOUNT_DISABLED_DETAIL)
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    store: Repository = Depends(get_repository),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    payload = decode_token(authorization.split(" ", 1)[1])
    user = store.get_user(str(payload["sub"]))
    return require_active_user(user)


def get_optional_user(
    authorization: str | None = Header(default=None),
    store: Repository = Depends(get_repository),
) -> User | None:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
    except HTTPException:
        return None
    user = store.get_user(str(payload["sub"]))
    if not user or user.disabled:
        return None
    return user


def require_roles(*roles: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency


def require_permissions(*permissions: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not role_has_permissions(user.role, permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency
