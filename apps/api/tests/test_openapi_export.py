from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OPENAPI_EXPORT = ROOT / "api" / "openapi.json"
EXPORT_SCRIPT = ROOT / "scripts" / "export-openapi.py"


def test_openapi_export_file_matches_fastapi_schema() -> None:
    assert OPENAPI_EXPORT.exists()

    exported = json.loads(OPENAPI_EXPORT.read_text(encoding="utf-8"))

    assert exported == app.openapi()
    assert exported["info"]["title"] == "gayoj API"
    assert "/api/v1/problems" in exported["paths"]
    assert "/api/v1/problems/{problem_id}/submit-code" in exported["paths"]
    assert "/api/v1/training/offline-pack" in exported["paths"]
    assert "/api/v1/problem-sets/{problem_set_id}/offline-package" in exported["paths"]
    assert "/api/v1/judge/languages" in exported["paths"]
    assert "/api/v1/admin/compiler-configs" in exported["paths"]


def test_openapi_export_script_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

