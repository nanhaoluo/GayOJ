from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import OFFLINE_PACK_SECRET
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
            expected_normalized = [normalize_blank(v, case_sensitive, trim_space) for v in expected_values]
            correct = normalize_blank(received, case_sensitive, trim_space) in expected_normalized
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


def build_offline_pack(problems: list[Problem], judge_configs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pack = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "objective-only",
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
