from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

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
