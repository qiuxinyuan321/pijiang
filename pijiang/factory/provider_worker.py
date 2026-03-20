from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .providers import adapter_for_profile, profile_from_payload
from .types import ExecutionRequest, ExecutionResponse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a provider request in an isolated worker process.")
    parser.add_argument("--input", required=True, help="Input JSON payload path.")
    parser.add_argument("--output", required=True, help="Output JSON payload path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    profile = profile_from_payload(payload["profile"])
    request_payload = payload["request"]
    request = ExecutionRequest(
        prompt=str(request_payload["prompt"]),
        output_mode=str(request_payload["output_mode"]),
        schema=request_payload.get("schema"),
        timeout_sec=int(request_payload.get("timeout_sec", 900)),
        output_path=Path(request_payload["output_path"]).expanduser().resolve() if request_payload.get("output_path") else None,
    )
    response: ExecutionResponse = adapter_for_profile(profile).execute(request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(response), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
