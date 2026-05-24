from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke-api.ps1"


def test_api_smoke_script_exists_and_covers_p0_03_flows() -> None:
    assert SMOKE_SCRIPT.exists()

    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    required_fragments = [
        "/auth/login",
        "/auth/me",
        "/users/me/profile",
        "/problems",
        "/tags",
        "/admin/tags",
        "/problems/P1002",
        "judge_config",
        "checking P3-04 code test-data upload and download",
        "/admin/problems/$($managedCodeProblem.id)/testdata",
        "tag:manage",
        "/problems/P1003/submit-objective",
        "/problems/P1001/submit-code",
        "/submissions?mine=true",
        "/problem-sets",
        "/notifications",
        "/read",
        "/admin/users/$($me.id)/ban?disabled=true",
        "/admin/compiler-configs",
        "/judge/languages",
        "/offline-results/sync",
        "/users/me/profile",
        "/users/me/password",
        "ExpectedStatus 403",
    ]

    for fragment in required_fragments:
        assert fragment in source


def test_api_smoke_script_keeps_code_submission_on_api_path() -> None:
    source = SMOKE_SCRIPT.read_text(encoding="utf-8").lower()

    assert "/problems/p1001/submit-code" in source
    assert '$codesubmission.status -eq "queued"' in source
    assert "api must not mark code submissions judged locally" in source
    assert "/admin/compiler-configs/c" in source
    assert 'public judge languages must not expose compile commands' in source
    forbidden_local_execution_markers = [
        "python $codesource",
        "py -3.12",
        "gcc ",
        "g++ ",
        "javac ",
        "go run",
        "cargo run",
    ]
    for marker in forbidden_local_execution_markers:
        assert marker not in source
