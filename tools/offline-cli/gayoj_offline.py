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
SIGNATURE_ALGORITHM = "hmac-sha256"
SUPPORTED_PROBLEM_TYPES = {"blank", "single_choice", "multiple_choice"}
DEFAULT_API_BASE = (
    os.getenv("GAYOJ_CLI_API_BASE")
    or os.getenv("GAYOJ_API_BASE")
    or "http://127.0.0.1:8000/api/v1"
)


def sign_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(PACK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def make_result_key(problem_id: str, answers: dict[str, Any], practiced_at: str | None) -> str:
    payload = {"problem_id": problem_id, "answers": answers, "practiced_at": practiced_at or ""}
    return f"cli:{hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()}"


def parse_pack_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_pack(path: Path) -> dict[str, Any]:
    data = load_json(path)
    payload = data.get("payload")
    signature = data.get("signature", "")
    if not isinstance(payload, dict):
        raise SystemExit("Offline pack format error: missing payload.")
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise SystemExit("Offline pack signature algorithm is not supported.")
    if not hmac.compare_digest(sign_payload(payload), signature):
        raise SystemExit("Offline pack signature verification failed: 签名校验失败.")
    expires_at = parse_pack_datetime(payload.get("expires_at"))
    if expires_at is None:
        raise SystemExit("Offline pack format error: missing expires_at.")
    if expires_at <= datetime.now(timezone.utc):
        raise SystemExit("Offline pack has expired: 已过期. Download it again.")
    return payload


def problem_type_counts(problems: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for problem in problems:
        problem_type = str(problem.get("type", "unknown"))
        counts[problem_type] = counts.get(problem_type, 0) + 1
    return counts


def format_type_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"


def print_pack_summary(payload: dict[str, Any], *, output: Path | None = None) -> None:
    problems = payload.get("problems", [])
    problems = problems if isinstance(problems, list) else []
    prefix = f"Offline pack saved: {output}" if output else "Offline pack summary"
    print(prefix)
    print(
        "Pack summary: "
        f"scope={payload.get('scope', 'unknown')} "
        f"problems={len(problems)} "
        f"expires_at={payload.get('expires_at', 'unknown')}"
    )
    print(f"Problem types: {format_type_counts(problem_type_counts(problems))}")


def ensure_supported_problem(problem: dict[str, Any]) -> None:
    problem_type = str(problem.get("type", ""))
    if problem_type not in SUPPORTED_PROBLEM_TYPES:
        problem_id = problem.get("id", "<unknown>")
        raise SystemExit(
            f"Offline CLI only supports blank, single_choice, and multiple_choice problems; "
            f"{problem_id} is {problem_type or 'unknown'}."
        )


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
    ensure_supported_problem(problem)
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

    raise SystemExit("Offline CLI only supports blank, single_choice, and multiple_choice problems.")


def normalize_choice_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = value.replace(" ", "").split(",")
    elif isinstance(value, list):
        items = value
    else:
        items = []
    return [str(item).strip().upper() for item in items if str(item).strip()]


def normalize_answers_for_problem(problem: dict[str, Any], raw_answers: Any) -> dict[str, Any]:
    ensure_supported_problem(problem)
    problem_type = problem["type"]

    if problem_type == "blank":
        if not isinstance(raw_answers, dict):
            raise SystemExit(f"Answers for {problem['id']} must be an object keyed by blank id.")
        normalized: dict[str, Any] = {}
        for blank in problem.get("blanks", []):
            key = blank.get("key")
            if key:
                normalized[str(key)] = raw_answers.get(key, "")
        return normalized

    if problem_type == "single_choice":
        if isinstance(raw_answers, dict):
            choice = raw_answers.get("choice", "")
        else:
            choice = raw_answers
        return {"choice": str(choice).strip().upper()}

    if problem_type == "multiple_choice":
        if isinstance(raw_answers, dict):
            choices = raw_answers.get("choices", raw_answers.get("choice", []))
        else:
            choices = raw_answers
        return {"choices": normalize_choice_list(choices)}

    raise SystemExit("Offline CLI only supports blank, single_choice, and multiple_choice problems.")


def load_answers(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("answers"), dict):
        return data["answers"]
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        answers: dict[str, Any] = {}
        for item in data:
            if isinstance(item, dict) and item.get("problem_id") and "answers" in item:
                answers[str(item["problem_id"])] = item["answers"]
        return answers
    raise SystemExit("Answers file must be a JSON object or a list of result items.")


def prompt_answers(problem: dict[str, Any]) -> dict[str, Any]:
    ensure_supported_problem(problem)
    answers: dict[str, Any] = {}
    if problem["type"] == "blank":
        for blank in problem.get("blanks", []):
            answers[blank["key"]] = input(f"{blank['label']}: ").strip()
    elif problem["type"] == "single_choice":
        for option in problem.get("options", []):
            print(f"  {option['key']}. {option['text']}")
        answers["choice"] = input("Answer: ").strip().upper()
    elif problem["type"] == "multiple_choice":
        for option in problem.get("options", []):
            print(f"  {option['key']}. {option['text']}")
        raw = input("Answer, separate multiple choices with commas: ").strip().upper()
        answers["choices"] = normalize_choice_list(raw)
    return answers


def answers_for_problem(
    problem: dict[str, Any],
    answers_by_problem: dict[str, Any] | None,
) -> dict[str, Any]:
    if answers_by_problem is None:
        return prompt_answers(problem)
    problem_id = str(problem.get("id", ""))
    if problem_id not in answers_by_problem:
        raise SystemExit(f"Missing answers for problem {problem_id} in answers file.")
    return normalize_answers_for_problem(problem, answers_by_problem[problem_id])


def default_cache_path(output: str | None) -> Path:
    if output:
        return Path(f"{output}.cache.json")
    return Path("offline-results.cache.json")


def load_practice_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_json(path)
    results = data.get("results", []) if isinstance(data, dict) else []
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict) and item.get("problem_id")]


def write_practice_cache(path: Path, payload: dict[str, Any], results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    problems = payload.get("problems", [])
    problem_ids = [problem.get("id") for problem in problems if isinstance(problem, dict)]
    cache_payload = {
        "pack": {
            "version": payload.get("version"),
            "generated_at": payload.get("generated_at"),
            "expires_at": payload.get("expires_at"),
            "problem_ids": problem_ids,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    path.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        raise SystemExit(f"Request failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed: {exc.reason}") from exc


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
        raise SystemExit("Provide a login token with --token or GAYOJ_TOKEN.")
    api_base = args.api.rstrip("/")
    if getattr(args, "problem_set_id", None):
        data = request_json(f"{api_base}/problem-sets/{args.problem_set_id}/offline-package", token=token)
    else:
        data = request_json(f"{api_base}/training/offline-pack", token=token)
    output = Path(args.output)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = data.get("payload", {}) if isinstance(data, dict) else {}
    if isinstance(payload, dict):
        print_pack_summary(payload, output=output)
    else:
        print(f"Offline pack saved: {output}")


def cmd_pull_set(args: argparse.Namespace) -> None:
    args.problem_set_id = args.problem_set_id.strip()
    cmd_download(args)


def cmd_inspect(args: argparse.Namespace) -> None:
    payload = load_pack(Path(args.pack))
    for problem in payload.get("problems", []):
        ensure_supported_problem(problem)
    print_pack_summary(payload)


def cmd_practice(args: argparse.Namespace) -> None:
    payload = load_pack(Path(args.pack))
    problems = payload.get("problems", [])
    if not isinstance(problems, list) or not problems:
        raise SystemExit("Offline pack does not contain practice problems.")

    answers_by_problem = load_answers(Path(args.answers)) if args.answers else None
    cache_path = Path(args.cache) if args.cache else default_cache_path(args.output)
    saved_results: list[dict[str, Any]] = load_practice_cache(cache_path) if args.resume else []
    completed_problem_ids = {str(item["problem_id"]) for item in saved_results}
    print_pack_summary(payload)
    if args.resume and completed_problem_ids:
        print(f"Resuming cached practice: cache={cache_path} completed={len(completed_problem_ids)}")

    for problem in problems:
        ensure_supported_problem(problem)
        if str(problem.get("id")) in completed_problem_ids:
            print(f"Skipping cached result: {problem['id']}")
            continue
        print(f"\n[{problem['id']}] {problem['title']} ({problem['type']})")
        if not args.answers:
            print(problem["statement"])
        answers = answers_for_problem(problem, answers_by_problem)
        score, max_score = judge(problem, answers)
        practiced_at = datetime.now(timezone.utc).isoformat()
        saved_results.append(
            {
                "problem_id": problem["id"],
                "answers": answers,
                "practiced_at": practiced_at,
                "client_result_key": make_result_key(problem["id"], answers, practiced_at),
                "local_score": score,
                "local_max_score": max_score,
            }
        )
        print(f"Score: {score}/{max_score}")
        write_practice_cache(cache_path, payload, saved_results)

    total_score = sum(int(item.get("local_score", 0)) for item in saved_results)
    total_max = sum(int(item.get("local_max_score", 0)) for item in saved_results)
    print(f"\nPractice summary: solved={len(saved_results)} score={total_score}/{total_max}")
    if args.output:
        output = Path(args.output)
        output.write_text(json.dumps({"results": saved_results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Results saved: {output}")
    write_practice_cache(cache_path, payload, saved_results)
    print(f"Practice cache saved: {cache_path}")


def cmd_sync_results(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("GAYOJ_TOKEN")
    if not token:
        raise SystemExit("Provide a login token with --token or GAYOJ_TOKEN.")
    data = load_json(Path(args.results))
    results = []
    for item in data.get("results", []):
        practiced_at = item.get("practiced_at")
        client_result_key = item.get("client_result_key") or make_result_key(
            item["problem_id"],
            item["answers"],
            practiced_at,
        )
        results.append(
            {
                "problem_id": item["problem_id"],
                "answers": item["answers"],
                "practiced_at": practiced_at,
                "client_result_key": client_result_key,
            }
        )
    response = request_json(
        f"{args.api.rstrip('/')}/offline-results/sync",
        method="POST",
        token=token,
        body={"results": results},
    )
    synced_count = len(response.get("synced", []))
    merged_count = len(response.get("merged", []))
    rejected_count = len(response.get("rejected", []))
    print(f"Sync summary: synced={synced_count} merged={merged_count} rejected={rejected_count}")
    if rejected_count:
        for rejected in response.get("rejected", []):
            print(f"Rejected {rejected.get('problem_id')}: {rejected.get('reason')}")
        if getattr(args, "fail_on_rejected", False):
            raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="gayoj objective offline training CLI. Code problems are never executed locally."
    )
    sub = parser.add_subparsers(required=True)

    login_parser = sub.add_parser("login", help="Log in and print an access token")
    login_parser.add_argument("--api", default=DEFAULT_API_BASE)
    login_parser.add_argument("-u", "--username", default="alice")
    login_parser.add_argument("-p", "--password")
    login_parser.set_defaults(func=cmd_login)

    download_parser = sub.add_parser("download", help="Download a signed objective offline pack")
    download_parser.add_argument("--api", default=DEFAULT_API_BASE)
    download_parser.add_argument("--token")
    download_parser.add_argument("--problem-set-id", help="Download only objective problems from a problem set")
    download_parser.add_argument("-o", "--output", default="offline-pack.json")
    download_parser.set_defaults(func=cmd_download)

    pull_set_parser = sub.add_parser("pull-set", help="Download an objective offline pack for one problem set")
    pull_set_parser.add_argument("problem_set_id")
    pull_set_parser.add_argument("--api", default=DEFAULT_API_BASE)
    pull_set_parser.add_argument("--token")
    pull_set_parser.add_argument("-o", "--output", default="offline-pack.json")
    pull_set_parser.set_defaults(func=cmd_pull_set)

    inspect_parser = sub.add_parser("inspect", help="Verify a pack and print its summary")
    inspect_parser.add_argument("pack")
    inspect_parser.set_defaults(func=cmd_inspect)

    practice_parser = sub.add_parser("practice", help="Practice objective problems and save local results")
    practice_parser.add_argument("pack")
    practice_parser.add_argument(
        "--answers",
        help="JSON answers file for non-interactive practice. Use {\"answers\": {\"P1003\": {\"choice\": \"B\"}}}.",
    )
    practice_parser.add_argument("--cache", help="Path for local practice progress cache")
    practice_parser.add_argument("--resume", action="store_true", help="Resume from the local practice progress cache")
    practice_parser.add_argument("-o", "--output", default="offline-results.json", help="Path to save local results")
    practice_parser.set_defaults(func=cmd_practice)

    sync_parser = sub.add_parser("sync-results", help="Sync local objective practice results")
    sync_parser.add_argument("results")
    sync_parser.add_argument("--api", default=DEFAULT_API_BASE)
    sync_parser.add_argument("--token")
    sync_parser.add_argument("--fail-on-rejected", action="store_true", help="Exit with code 2 if any result is rejected")
    sync_parser.set_defaults(func=cmd_sync_results)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
