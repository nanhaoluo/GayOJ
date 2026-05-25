from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import ProblemCreate
from app.models import Problem
from app.services import judge_objective


def make_problem(problem_type: str, **overrides: Any) -> Problem:
    payload: dict[str, Any] = {
        "id": f"P5-{problem_type}",
        "title": "P5 objective rule case",
        "type": problem_type,
        "statement": "P5 objective rule test.",
        "author_id": "u-coach",
        "created_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return Problem(**payload)


def assert_api_cli_score_match(
    offline_cli_module: Any,
    problem: Problem,
    judge_config: dict[str, Any],
    answers: dict[str, Any],
    expected_score: int,
    expected_max_score: int,
) -> None:
    api_score, api_max_score, details = judge_objective(problem, judge_config, answers)
    cli_score, cli_max_score = offline_cli_module.judge(
        {
            "id": problem.id,
            "title": problem.title,
            "type": problem.type,
            "statement": problem.statement,
            "options": problem.options,
            "blanks": problem.blanks,
            "judge_config": judge_config,
        },
        answers,
    )

    assert (api_score, api_max_score) == (expected_score, expected_max_score)
    assert (cli_score, cli_max_score) == (expected_score, expected_max_score)
    assert sum(item.score for item in details) == expected_score


def test_blank_rules_match_cli_for_case_and_space_normalization(offline_cli_module: Any) -> None:
    problem = make_problem(
        "blank",
        blanks=[
            {"key": "formula", "label": "Formula", "score": 60},
            {"key": "word", "label": "Word", "score": 40},
        ],
    )
    judge_config = {
        "case_sensitive": False,
        "trim_space": True,
        "answers": {
            "formula": ["n(n-1)/2", "n*(n-1)/2"],
            "word": ["BinarySearch"],
        },
        "scores": {"formula": 60, "word": 40},
    }

    assert_api_cli_score_match(
        offline_cli_module,
        problem,
        judge_config,
        {"formula": " N * ( N - 1 ) / 2 ", "word": "linear"},
        60,
        100,
    )

    assert_api_cli_score_match(
        offline_cli_module,
        problem,
        judge_config,
        {"formula": "n(n-1)/2", "word": "binarysearch"},
        100,
        100,
    )


def test_blank_rules_match_cli_when_case_sensitive_and_spaces_preserved(offline_cli_module: Any) -> None:
    problem = make_problem(
        "blank",
        blanks=[{"key": "token", "label": "Token", "score": 100}],
    )
    judge_config = {
        "case_sensitive": True,
        "trim_space": False,
        "answers": {"token": ["OpenAI"]},
        "scores": {"token": 100},
    }

    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"token": "openai"}, 0, 100)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"token": "OpenAI"}, 100, 100)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"token": "Open AI"}, 0, 100)


def test_blank_regex_rules_match_cli_and_respect_case_setting(offline_cli_module: Any) -> None:
    problem = make_problem(
        "blank",
        blanks=[{"key": "identifier", "label": "Identifier", "score": 100}],
    )
    judge_config = {
        "case_sensitive": False,
        "trim_space": True,
        "answers": {"identifier": [r"node-[a-z]{3}-\d{2}"]},
        "scores": {"identifier": 100},
        "blank_rules": {"identifier": {"match": "regex"}},
    }

    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"identifier": " NODE-ABC-12 "}, 100, 100)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"identifier": "node-ab-12"}, 0, 100)


def test_blank_numeric_rules_match_cli_with_tolerance(offline_cli_module: Any) -> None:
    problem = make_problem(
        "blank",
        blanks=[{"key": "pi", "label": "Pi", "score": 100}],
    )
    judge_config = {
        "case_sensitive": False,
        "trim_space": True,
        "answers": {"pi": ["3.14159"]},
        "scores": {"pi": 100},
        "blank_rules": {"pi": {"match": "numeric", "tolerance": 0.01}},
    }

    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"pi": "3.15"}, 100, 100)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"pi": "3.20"}, 0, 100)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"pi": "not-a-number"}, 0, 100)


def test_single_choice_rules_match_cli_for_exact_option_key(offline_cli_module: Any) -> None:
    problem = make_problem(
        "single_choice",
        options=[
            {"key": "A", "text": "Array is random."},
            {"key": "B", "text": "Search space is monotonic."},
        ],
    )
    judge_config = {"answer": "B", "score": 25}

    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choice": "B"}, 25, 25)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choice": "b"}, 0, 25)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choice": "A"}, 0, 25)


def test_multiple_choice_rules_match_cli_independent_of_selection_order(offline_cli_module: Any) -> None:
    problem = make_problem(
        "multiple_choice",
        options=[
            {"key": "A", "text": "Limit CPU time."},
            {"key": "B", "text": "Allow public network."},
            {"key": "C", "text": "Disable network."},
        ],
    )
    judge_config = {"answer": ["A", "C"], "score": 70}

    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choices": ["C", "A"]}, 70, 70)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choices": ["A"]}, 0, 70)
    assert_api_cli_score_match(offline_cli_module, problem, judge_config, {"choices": ["A", "B", "C"]}, 0, 70)


def test_code_problem_is_not_supported_by_objective_rule_paths(offline_cli_module: Any) -> None:
    problem = make_problem("code")

    with pytest.raises(ValueError, match="Unsupported objective problem type"):
        judge_objective(problem, {}, {})

    with pytest.raises(SystemExit):
        offline_cli_module.judge({"type": "code", "judge_config": {}}, {})


def test_blank_rule_validation_rejects_invalid_regex_and_tolerance() -> None:
    base_payload: dict[str, Any] = {
        "title": "P5 validation",
        "type": "blank",
        "difficulty": "基础",
        "statement": "Validate blank rules.",
        "blanks": [{"key": "answer", "label": "Answer", "score": 100}],
        "judge_config": {
            "answers": {"answer": ["ok"]},
            "scores": {"answer": 100},
            "blank_rules": {"answer": {"match": "regex"}},
        },
    }

    ProblemCreate(**base_payload)

    with pytest.raises(ValueError, match="invalid"):
        ProblemCreate(
            **{
                **base_payload,
                "judge_config": {
                    "answers": {"answer": ["["]},
                    "scores": {"answer": 100},
                    "blank_rules": {"answer": {"match": "regex"}},
                },
            }
        )

    with pytest.raises(ValueError, match="non-negative"):
        ProblemCreate(
            **{
                **base_payload,
                "judge_config": {
                    "answers": {"answer": ["1"]},
                    "scores": {"answer": 100},
                    "blank_rules": {"answer": {"match": "numeric", "tolerance": -0.1}},
                },
            }
        )


def test_blank_rule_management_api_keeps_public_detail_safe(client: TestClient, auth_headers) -> None:
    payload = {
        "title": "P5 regex blank rule",
        "type": "blank",
        "difficulty": "基础",
        "tags": ["P5"],
        "statement": "Enter a node id.",
        "blanks": [{"key": "node_id", "label": "Node ID", "score": 100}],
        "judge_config": {
            "case_sensitive": False,
            "trim_space": True,
            "answers": {"node_id": [r"node-\d{2}"]},
            "scores": {"node_id": 100},
            "blank_rules": {"node_id": {"match": "regex"}},
        },
    }

    created = client.post("/api/v1/admin/problems", headers=auth_headers("coach"), json=payload)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["judge_config"]["blank_rules"]["node_id"]["match"] == "regex"

    public_detail = client.get(f"/api/v1/problems/{body['id']}")
    assert public_detail.status_code == 200, public_detail.text
    assert "judge_config" not in public_detail.json()

    submitted = client.post(
        f"/api/v1/problems/{body['id']}/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"node_id": " NODE-42 "}},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["score"] == submitted.json()["max_score"] == 100
