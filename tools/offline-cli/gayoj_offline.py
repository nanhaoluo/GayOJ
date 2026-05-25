from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACK_SECRET = os.getenv("GAYOJ_OFFLINE_PACK_SECRET", "gayoj-offline-dev-secret")
DEFAULT_API_BASE = (
    os.getenv("GAYOJ_CLI_API_BASE")
    or os.getenv("GAYOJ_API_BASE")
    or "http://127.0.0.1:8000/api/v1"
)


def sign_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(PACK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def load_pack(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = data.get("payload")
    signature = data.get("signature", "")
    if not isinstance(payload, dict):
        raise SystemExit("离线包格式错误：缺少 payload")
    if not hmac.compare_digest(sign_payload(payload), signature):
        raise SystemExit("离线包签名校验失败，文件可能被篡改或密钥不一致。")
    return payload


def normalize_blank(value: Any, case_sensitive: bool, trim_space: bool) -> str:
    text = str(value)
    if trim_space:
        text = "".join(text.split())
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
        text = "".join(text.split())
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
            received_text = "".join(received_text.split())
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

    expected = [normalize_blank(item, case_sensitive, trim_space) for item in expected_values]
    return normalize_blank(received, case_sensitive, trim_space) in expected


def judge(problem: dict[str, Any], answers: dict[str, Any]) -> tuple[int, int]:
    config = problem.get("judge_config", {})
    if problem["type"] == "blank":
        total = sum(int(v) for v in config.get("scores", {}).values()) or 100
        score = 0
        case_sensitive = bool(config.get("case_sensitive", False))
        trim_space = bool(config.get("trim_space", True))
        for key, expected_values in config.get("answers", {}).items():
            received = answers.get(key, "")
            if blank_answer_matches(
                received,
                expected_values,
                blank_rule_for(config, key),
                case_sensitive=case_sensitive,
                trim_space=trim_space,
            ):
                score += int(config.get("scores", {}).get(key, 0))
        return score, total

    if problem["type"] == "single_choice":
        total = int(config.get("score", 100))
        return (total, total) if answers.get("choice") == config.get("answer") else (0, total)

    if problem["type"] == "multiple_choice":
        total = int(config.get("score", 100))
        expected = sorted(config.get("answer", []))
        received = sorted(answers.get("choices", []))
        return (total, total) if received == expected else (0, total)

    raise SystemExit("离线 CLI 只支持填空题、单选题和多选题。")


def request_json(url: str, method: str = "GET", token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"请求失败：HTTP {exc.code} {detail}") from exc


def cmd_login(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password: ")
    data = request_json(
        f"{args.api.rstrip('/')}/auth/login",
        method="POST",
        body={"username": args.username, "password": password},
    )
    print(data["access_token"])


def cmd_download(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("GAYOJ_TOKEN")
    if not token:
        raise SystemExit("请通过 --token 或 GAYOJ_TOKEN 提供登录令牌。")
    data = request_json(f"{args.api.rstrip('/')}/training/offline-pack", token=token)
    output = Path(args.output)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已下载离线训练包：{output}")


def cmd_practice(args: argparse.Namespace) -> None:
    payload = load_pack(Path(args.pack))
    problems = payload.get("problems", [])
    if not problems:
        raise SystemExit("离线包中没有可训练题目。")

    total_score = 0
    total_max = 0
    saved_results: list[dict[str, Any]] = []
    for problem in problems:
        print(f"\n[{problem['id']}] {problem['title']} ({problem['type']})")
        print(problem["statement"])
        answers: dict[str, Any] = {}
        if problem["type"] == "blank":
            for blank in problem.get("blanks", []):
                answers[blank["key"]] = input(f"{blank['label']}: ").strip()
        elif problem["type"] == "single_choice":
            for option in problem.get("options", []):
                print(f"  {option['key']}. {option['text']}")
            answers["choice"] = input("答案: ").strip().upper()
        elif problem["type"] == "multiple_choice":
            for option in problem.get("options", []):
                print(f"  {option['key']}. {option['text']}")
            raw = input("答案，多选用逗号分隔: ").strip().upper()
            answers["choices"] = [item.strip() for item in raw.replace(" ", "").split(",") if item.strip()]
        score, max_score = judge(problem, answers)
        saved_results.append(
            {
                "problem_id": problem["id"],
                "answers": answers,
                "practiced_at": datetime.now(timezone.utc).isoformat(),
                "local_score": score,
                "local_max_score": max_score,
            }
        )
        total_score += score
        total_max += max_score
        print(f"得分：{score}/{max_score}")

    print(f"\n训练完成：{total_score}/{total_max}")
    if args.output:
        output = Path(args.output)
        output.write_text(json.dumps({"results": saved_results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"练习结果已保存：{output}")


def cmd_sync_results(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("GAYOJ_TOKEN")
    if not token:
        raise SystemExit("请通过 --token 或 GAYOJ_TOKEN 提供登录令牌。")
    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    payload = {
        "results": [
            {
                "problem_id": item["problem_id"],
                "answers": item["answers"],
                "practiced_at": item.get("practiced_at"),
            }
            for item in data.get("results", [])
        ]
    }
    response = request_json(
        f"{args.api.rstrip('/')}/offline-results/sync",
        method="POST",
        token=token,
        body=payload,
    )
    print(f"同步完成：{len(response.get('synced', []))} 条，拒绝 {len(response.get('rejected', []))} 条")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="gayoj 客观题离线训练 CLI（不执行代码题）")
    sub = parser.add_subparsers(required=True)

    login_parser = sub.add_parser("login", help="登录并输出访问令牌")
    login_parser.add_argument("--api", default=DEFAULT_API_BASE)
    login_parser.add_argument("-u", "--username", default="alice")
    login_parser.add_argument("-p", "--password")
    login_parser.set_defaults(func=cmd_login)

    download_parser = sub.add_parser("download", help="下载签名离线训练包")
    download_parser.add_argument("--api", default=DEFAULT_API_BASE)
    download_parser.add_argument("--token")
    download_parser.add_argument("-o", "--output", default="offline-pack.json")
    download_parser.set_defaults(func=cmd_download)

    practice_parser = sub.add_parser("practice", help="使用离线训练包答题并本地判分")
    practice_parser.add_argument("pack")
    practice_parser.add_argument("-o", "--output", default="offline-results.json", help="保存本地练习结果，便于恢复联网后同步")
    practice_parser.set_defaults(func=cmd_practice)

    sync_parser = sub.add_parser("sync-results", help="同步本地客观题练习结果")
    sync_parser.add_argument("results")
    sync_parser.add_argument("--api", default=DEFAULT_API_BASE)
    sync_parser.add_argument("--token")
    sync_parser.set_defaults(func=cmd_sync_results)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

