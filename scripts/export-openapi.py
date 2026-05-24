from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
DEFAULT_OUTPUT = ROOT / "api" / "openapi.json"


def load_schema() -> dict:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    from app.main import app

    return app.openapi()


def render_schema(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the gayoj FastAPI OpenAPI schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write the OpenAPI JSON file. Defaults to api/openapi.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that the output file already matches the current FastAPI schema.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    content = render_schema(load_schema())

    if args.check:
        if not output.exists():
            print(f"OpenAPI export is missing: {output}", file=sys.stderr)
            return 1
        current = output.read_text(encoding="utf-8")
        if current != content:
            print(f"OpenAPI export is stale: {output}", file=sys.stderr)
            print("Run: npm run export:openapi", file=sys.stderr)
            return 1
        print(f"OpenAPI export is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Exported OpenAPI schema to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

