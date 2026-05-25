from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import OFFLINE_PACK_SECRET, OFFLINE_PACK_TTL_HOURS
from .models import ObjectiveItemResult, Problem


PACK_SECRET = OFFLINE_PACK_SECRET


def make_submission_id() -> str:
    return f"S{uuid4().hex[:10].upper()}"


def normalize_blank(value: Any, case_sensitive: bool, trim_space: bool) -> str:
    text = str(value)
    if trim_space:
        text = re.sub(r"\s+", "", text)
    if not case_sensitive:
        text = text.lower()
    return text


def blank_rule_for(config: dict[str, Any], key: str) -> dict[str, Any]:
    rules = config.get("blank_rules", {})
    if not isinstance(rules, dict):
        return {}
    rule = rules.get(key, {})
    return rule if isinstance(rule, dict) else {}


def numeric_value(value: Any, trim_space: bool) -> float | None:
    text = str(value)
    if trim_space:
        text = re.sub(r"\s+", "", text)
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def blank_answer_matches(
    received: Any,
    expected_values: list[Any],
    rule: dict[str, Any],
    *,
    case_sensitive: bool,
    trim_space: bool,
) -> bool:
    match_type = str(rule.get("match", "exact")).strip().lower() or "exact"

    if match_type == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        received_text = str(received)
        if trim_space:
            received_text = re.sub(r"\s+", "", received_text)
        for pattern in expected_values:
            try:
                if re.fullmatch(str(pattern), received_text, flags=flags):
                    return True
            except re.error:
                continue
        return False

    if match_type == "numeric":
        received_value = numeric_value(received, trim_space)
        if received_value is None:
            return False
        try:
            tolerance = max(float(rule.get("tolerance", 0)), 0.0)
        except (TypeError, ValueError):
            tolerance = 0.0
        for expected in expected_values:
            expected_value = numeric_value(expected, trim_space)
            if expected_value is not None and abs(received_value - expected_value) <= tolerance:
                return True
        return False

    expected_normalized = [normalize_blank(v, case_sensitive, trim_space) for v in expected_values]
    return normalize_blank(received, case_sensitive, trim_space) in expected_normalized


def judge_objective(
    problem: Problem,
    judge_config: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[int, int, list[ObjectiveItemResult]]:
    config = judge_config
    results: list[ObjectiveItemResult] = []

    if problem.type == "blank":
        case_sensitive = bool(config.get("case_sensitive", False))
        trim_space = bool(config.get("trim_space", True))
        scores: dict[str, int] = config.get("scores", {})
        expected_map: dict[str, list[str]] = config.get("answers", {})
        total = sum(int(v) for v in scores.values()) or 100
        score = 0
        for key, expected_values in expected_map.items():
            received = answers.get(key, "")
            correct = blank_answer_matches(
                received,
                expected_values,
                blank_rule_for(config, key),
                case_sensitive=case_sensitive,
                trim_space=trim_space,
            )
            item_score = int(scores.get(key, 0)) if correct else 0
            score += item_score
            results.append(
                ObjectiveItemResult(
                    key=key,
                    correct=correct,
                    expected=expected_values[0] if expected_values else None,
                    received=received,
                    score=item_score,
                )
            )
        return score, total, results

    if problem.type == "single_choice":
        expected = str(config.get("answer", ""))
        received = str(answers.get("choice", ""))
        total = int(config.get("score", 100))
        correct = received == expected
        return (
            total if correct else 0,
            total,
            [
                ObjectiveItemResult(
                    key="choice",
                    correct=correct,
                    expected=expected,
                    received=received,
                    score=total if correct else 0,
                )
            ],
        )

    if problem.type == "multiple_choice":
        expected = sorted(str(item) for item in config.get("answer", []))
        received = sorted(str(item) for item in answers.get("choices", []))
        total = int(config.get("score", 100))
        correct = received == expected
        return (
            total if correct else 0,
            total,
            [
                ObjectiveItemResult(
                    key="choices",
                    correct=correct,
                    expected=expected,
                    received=received,
                    score=total if correct else 0,
                )
            ],
        )

    raise ValueError("Unsupported objective problem type")


def sign_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(PACK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def build_offline_pack(
    problems: list[Problem],
    judge_configs: dict[str, dict[str, Any]],
    *,
    ttl_hours: int | None = None,
    source: dict[str, Any] | None = None,
    pack_id: str | None = None,
    lifecycle: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    expires_at = expires_at or generated_at + timedelta(hours=max(ttl_hours or OFFLINE_PACK_TTL_HOURS, 1))
    lifecycle_payload = lifecycle.model_dump(mode="json") if hasattr(lifecycle, "model_dump") else (lifecycle or {})
    pack = {
        "version": "1.0",
        "pack_id": pack_id or f"pack-{uuid4().hex[:16]}",
        "generated_at": generated_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "signature_algorithm": "hmac-sha256",
        "scope": "objective-only",
        "source": source or {"type": "training"},
        "lifecycle": lifecycle_payload,
        "problems": [
            {
                "id": p.id,
                "title": p.title,
                "type": p.type,
                "difficulty": p.difficulty,
                "tags": p.tags,
                "statement": p.statement,
                "options": p.options,
                "blanks": p.blanks,
                "judge_config": judge_configs.get(p.id, {}),
            }
            for p in problems
            if p.type != "code"
        ],
    }
    return {"payload": pack, "signature": sign_payload(pack)}
