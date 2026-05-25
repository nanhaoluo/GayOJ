from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


def signed_pack(offline_cli_module: Any, problems: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "signature_algorithm": "hmac-sha256",
        "scope": "objective-only",
        "source": {"type": "test"},
        "problems": problems,
    }
    return {"payload": payload, "signature": offline_cli_module.sign_payload(payload)}


def write_pack(offline_cli_module: Any, tmp_path: Path, problems: list[dict[str, Any]]) -> Path:
    path = tmp_path / "offline-pack.json"
    path.write_text(json.dumps(signed_pack(offline_cli_module, problems), ensure_ascii=False), encoding="utf-8")
    return path


def test_cli_practice_accepts_answers_file_and_saves_summary_results(
    offline_cli_module: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path = write_pack(
        offline_cli_module,
        tmp_path,
        [
            {
                "id": "P-BLANK",
                "title": "Blank",
                "type": "blank",
                "difficulty": "basic",
                "tags": [],
                "statement": "Fill blank.",
                "options": [],
                "blanks": [{"key": "answer", "label": "Answer", "score": 40}],
                "judge_config": {"answers": {"answer": ["ctoj"]}, "scores": {"answer": 40}},
            },
            {
                "id": "P-SINGLE",
                "title": "Single",
                "type": "single_choice",
                "difficulty": "basic",
                "tags": [],
                "statement": "Pick one.",
                "options": [{"key": "A", "text": "Wrong"}, {"key": "B", "text": "Right"}],
                "blanks": [],
                "judge_config": {"answer": "B", "score": 60},
            },
        ],
    )
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"answers": {"P-BLANK": {"answer": " CTOJ "}, "P-SINGLE": "b"}}),
        encoding="utf-8",
    )
    results_path = tmp_path / "offline-results.json"

    offline_cli_module.cmd_practice(
        argparse.Namespace(pack=str(pack_path), answers=str(answers_path), output=str(results_path), cache=None, resume=False)
    )

    output = capsys.readouterr().out
    assert "Practice summary: solved=2 score=100/100" in output
    data = json.loads(results_path.read_text(encoding="utf-8"))
    assert [item["problem_id"] for item in data["results"]] == ["P-BLANK", "P-SINGLE"]
    assert all(item["client_result_key"].startswith("cli:") for item in data["results"])
    assert data["results"][0]["answers"] == {"answer": " CTOJ "}
    assert data["results"][1]["answers"] == {"choice": "B"}


def test_cli_practice_can_resume_from_progress_cache(
    offline_cli_module: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path = write_pack(
        offline_cli_module,
        tmp_path,
        [
            {
                "id": "P-SINGLE",
                "title": "Single",
                "type": "single_choice",
                "difficulty": "basic",
                "tags": [],
                "statement": "Pick one.",
                "options": [{"key": "A", "text": "Wrong"}, {"key": "B", "text": "Right"}],
                "blanks": [],
                "judge_config": {"answer": "B", "score": 100},
            }
        ],
    )
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps({"answers": {"P-SINGLE": "B"}}), encoding="utf-8")
    results_path = tmp_path / "offline-results.json"
    cache_path = tmp_path / "practice-cache.json"

    args = argparse.Namespace(
        pack=str(pack_path),
        answers=str(answers_path),
        output=str(results_path),
        cache=str(cache_path),
        resume=False,
    )
    offline_cli_module.cmd_practice(args)
    first = json.loads(results_path.read_text(encoding="utf-8"))
    assert len(first["results"]) == 1
    assert cache_path.exists()

    args.resume = True
    offline_cli_module.cmd_practice(args)

    output = capsys.readouterr().out
    second = json.loads(results_path.read_text(encoding="utf-8"))
    assert "Skipping cached result: P-SINGLE" in output
    assert len(second["results"]) == 1
    assert second["results"][0]["client_result_key"] == first["results"][0]["client_result_key"]


def test_cli_practice_rejects_missing_answers_file_entry(offline_cli_module: Any, tmp_path: Path) -> None:
    pack_path = write_pack(
        offline_cli_module,
        tmp_path,
        [
            {
                "id": "P-SINGLE",
                "title": "Single",
                "type": "single_choice",
                "difficulty": "basic",
                "tags": [],
                "statement": "Pick one.",
                "options": [{"key": "A", "text": "Wrong"}, {"key": "B", "text": "Right"}],
                "blanks": [],
                "judge_config": {"answer": "B", "score": 100},
            }
        ],
    )
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps({"answers": {}}), encoding="utf-8")

    with pytest.raises(SystemExit, match="Missing answers for problem P-SINGLE"):
        offline_cli_module.cmd_practice(
            argparse.Namespace(
                pack=str(pack_path),
                answers=str(answers_path),
                output=str(tmp_path / "out.json"),
                cache=None,
                resume=False,
            )
        )


def test_cli_pack_commands_print_summary_and_use_problem_set_endpoint(
    offline_cli_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack = signed_pack(
        offline_cli_module,
        [
            {
                "id": "P-SINGLE",
                "title": "Single",
                "type": "single_choice",
                "difficulty": "basic",
                "tags": [],
                "statement": "Pick one.",
                "options": [],
                "blanks": [],
                "judge_config": {"answer": "B", "score": 100},
            }
        ],
    )
    captured: dict[str, Any] = {}

    def fake_request_json(url: str, method: str = "GET", token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        captured.update({"url": url, "method": method, "token": token, "body": body})
        return pack

    monkeypatch.setattr(offline_cli_module, "request_json", fake_request_json)
    output_path = tmp_path / "ps1001-pack.json"
    offline_cli_module.cmd_pull_set(
        argparse.Namespace(
            problem_set_id=" PS1001 ",
            api="http://example.test/api/v1",
            token="token-1",
            output=str(output_path),
        )
    )

    output = capsys.readouterr().out
    assert captured["url"] == "http://example.test/api/v1/problem-sets/PS1001/offline-package"
    assert captured["method"] == "GET"
    assert "Offline pack saved:" in output
    assert "Pack summary: scope=objective-only problems=1" in output
    assert output_path.exists()


def test_cli_sync_results_prints_counts_and_can_fail_on_rejected(
    offline_cli_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results_path = tmp_path / "offline-results.json"
    results_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "problem_id": "P1003",
                        "answers": {"choice": "B"},
                        "practiced_at": "2026-05-25T00:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_request_json(url: str, method: str = "GET", token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        captured.update({"url": url, "method": method, "token": token, "body": body})
        return {"synced": [{"id": "S1"}], "merged": [{"id": "S0"}], "rejected": [{"problem_id": "PX", "reason": "no"}]}

    monkeypatch.setattr(offline_cli_module, "request_json", fake_request_json)

    with pytest.raises(SystemExit) as exc:
        offline_cli_module.cmd_sync_results(
            argparse.Namespace(
                results=str(results_path),
                api="http://example.test/api/v1",
                token="token-1",
                fail_on_rejected=True,
            )
        )

    output = capsys.readouterr().out
    assert exc.value.code == 2
    assert "Sync summary: synced=1 merged=1 rejected=1" in output
    assert captured["body"]["results"][0]["client_result_key"].startswith("cli:")


def test_cli_inspect_rejects_non_objective_pack(offline_cli_module: Any, tmp_path: Path) -> None:
    pack_path = write_pack(
        offline_cli_module,
        tmp_path,
        [
            {
                "id": "P-CODE",
                "title": "Code",
                "type": "code",
                "difficulty": "basic",
                "tags": [],
                "statement": "Do not run.",
                "options": [],
                "blanks": [],
                "judge_config": {},
            }
        ],
    )

    with pytest.raises(SystemExit, match="Offline CLI only supports"):
        offline_cli_module.cmd_inspect(argparse.Namespace(pack=str(pack_path)))
