from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUMMARY = ROOT / "docs" / "p0-development-summary.md"
README = ROOT / "README.md"


def test_p0_summary_exists_and_covers_all_phase_zero_tasks() -> None:
    assert SUMMARY.exists()

    source = SUMMARY.read_text(encoding="utf-8")
    for task_id in ["P0-01", "P0-02", "P0-03", "P0-04", "P0-05"]:
        assert task_id in source

    for command in [
        "npm run check:api",
        "npm run typecheck",
        "npm run build:web",
        "npm run check:openapi",
        "npm run smoke:api",
    ]:
        assert command in source


def test_p0_summary_preserves_security_boundaries() -> None:
    source = SUMMARY.read_text(encoding="utf-8")

    required_fragments = [
        "Web、API、CLI 不在本地执行用户代码",
        "普通题面接口不得返回客观题 `judge_config`",
        "CLI 只允许填空题、单选题、多选题",
        "未改变 JSON 数据结构",
    ]
    for fragment in required_fragments:
        assert fragment in source


def test_p0_summary_records_judge_machine_contract() -> None:
    source = SUMMARY.read_text(encoding="utf-8")

    required_fragments = [
        "Ubuntu Server 24.04",
        "gcc/g++ 14.2.0",
        "OpenJDK 21.x",
        "python3 -m py_compile Main.py",
        "gcc -std=c17 -O2 -Wall -Wextra -DONLINE_JUDGE -static",
        "g++ -std=c++17 -O2 -Wall -Wextra -DONLINE_JUDGE -static",
        "javac -J-Xms1024M -J-Xmx1024M -J-Xss64M -encoding UTF-8 Main.java",
        "stdin",
        "stdout",
        "Runtime Error",
        "Compile Error",
        "Judge Error",
    ]
    for fragment in required_fragments:
        assert fragment in source


def test_readme_links_to_p0_summary() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "docs/p0-development-summary.md" in readme
