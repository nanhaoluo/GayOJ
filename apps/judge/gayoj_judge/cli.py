from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .sandbox import DEFAULT_RUNNER_IMAGE, DockerSandboxExecutor, SandboxLimits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gayoj_judge",
        description="gayoj judge worker Docker sandbox smoke entrypoint.",
    )
    parser.add_argument("--language", default="python", choices=["c", "cpp", "java", "python"])
    parser.add_argument("--source-file", type=Path, help="Source file to execute inside the Docker sandbox.")
    parser.add_argument("--stdin", default="", help="stdin passed to the sandboxed process.")
    parser.add_argument("--time-limit-ms", type=int, default=1000)
    parser.add_argument("--memory-limit-mb", type=int, default=128)
    parser.add_argument("--image", default=os.getenv("GAYOJ_JUDGE_RUNNER_IMAGE", DEFAULT_RUNNER_IMAGE))
    parser.add_argument("--docker-bin", default=os.getenv("GAYOJ_DOCKER_BIN", "docker"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Docker command JSON without executing user code or requiring Docker.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    limits = SandboxLimits(time_limit_ms=args.time_limit_ms, memory_limit_mb=args.memory_limit_mb)
    executor = DockerSandboxExecutor(image=args.image, docker_bin=args.docker_bin)

    if args.dry_run:
        print(json.dumps(executor.preview_commands(language=args.language, limits=limits), ensure_ascii=False, indent=2))
        return 0

    if not args.source_file:
        parser.error("--source-file is required unless --dry-run is used")
    if not args.source_file.exists():
        parser.error(f"source file does not exist: {args.source_file}")

    result = executor.execute(
        language=args.language,
        source_code=args.source_file.read_text(encoding="utf-8"),
        stdin=args.stdin,
        limits=limits,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0 if result.verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

