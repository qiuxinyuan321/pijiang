from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.solution_factory.core import default_cache_root, get_user_environment_variable


DEFAULT_MODELS = [
    "bailian/kimi-k2.5",
    "bailian/glm-5",
    "bailian/MiniMax-M2.5",
    "bailian/qwen3.5-plus",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_opencode_executable(workspace_root: Path) -> Path:
    local_binary = (
        workspace_root
        / "opencode-src"
        / "packages"
        / "opencode"
        / "node_modules"
        / "opencode-windows-x64"
        / "bin"
        / "opencode.exe"
    )
    if local_binary.exists():
        return local_binary
    raise FileNotFoundError(f"opencode executable not found: {local_binary}")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def model_slug(model: str) -> str:
    return model.replace("/", "-").replace(".", "-")


@dataclass
class ProbeResult:
    model: str
    round_index: int
    status: str
    started_at: str
    finished_at: str
    exit_code: int
    stdout_path: str
    stderr_path: str
    prompt_path: str
    duration_sec: float


def build_prompt(model: str, round_index: int, rounds: int) -> str:
    return (
        f"这是百炼模型连通性探测，第 {round_index}/{rounds} 轮。\n"
        f"模型标识：{model}\n"
        "只回复一行文本，格式严格为：OK <model> <round>。\n"
        f"例如：OK {model} {round_index}\n"
        "不要调用工具，不要补充解释。"
    )


def run_probe(
    *,
    workspace_root: Path,
    probe_dir: Path,
    opencode_executable: Path,
    model: str,
    round_index: int,
    rounds: int,
    timeout_sec: int,
    api_key: str,
) -> ProbeResult:
    started_at = utc_now_iso()
    model_dir = ensure_directory(probe_dir / model_slug(model))
    round_dir = ensure_directory(model_dir / f"round-{round_index:02d}")
    prompt = build_prompt(model, round_index, rounds)
    prompt_path = round_dir / "prompt.txt"
    stdout_path = round_dir / "stdout.log"
    stderr_path = round_dir / "stderr.log"
    write_text(prompt_path, prompt)

    command = [
        str(opencode_executable),
        "run",
        "--format",
        "json",
        "--dir",
        str(workspace_root),
        "--model",
        model,
        prompt,
    ]
    env = dict(os.environ)
    env["BAILIAN_CODING_PLAN_API_KEY"] = api_key
    started_clock = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=workspace_root,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        env=env,
        check=False,
    )
    duration_sec = time.perf_counter() - started_clock
    write_text(stdout_path, completed.stdout or "")
    write_text(stderr_path, completed.stderr or "")
    finished_at = utc_now_iso()
    return ProbeResult(
        model=model,
        round_index=round_index,
        status="success" if completed.returncode == 0 else "failed",
        started_at=started_at,
        finished_at=finished_at,
        exit_code=completed.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        prompt_path=str(prompt_path),
        duration_sec=round(duration_sec, 3),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trigger repeated Alibaba Bailian Coding Plan requests via OpenCode.")
    parser.add_argument("--workspace", default=str(REPO_ROOT), help="Workspace root.")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per model.")
    parser.add_argument("--timeout-sec", type=int, default=180, help="Timeout per round.")
    parser.add_argument("--sleep-sec", type=float, default=1.0, help="Sleep between rounds.")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS, help="Models to probe.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace_root = Path(args.workspace).expanduser().resolve()
    cache_root = default_cache_root(workspace_root)
    probe_dir = ensure_directory(cache_root / "probes" / f"bailian-probe-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    opencode_executable = resolve_opencode_executable(workspace_root)
    api_key = get_user_environment_variable("BAILIAN_CODING_PLAN_API_KEY")
    if not api_key:
        raise RuntimeError("BAILIAN_CODING_PLAN_API_KEY is not available in user environment")

    results: list[ProbeResult] = []
    for model in args.models:
        for round_index in range(1, args.rounds + 1):
            result = run_probe(
                workspace_root=workspace_root,
                probe_dir=probe_dir,
                opencode_executable=opencode_executable,
                model=model,
                round_index=round_index,
                rounds=args.rounds,
                timeout_sec=args.timeout_sec,
                api_key=api_key,
            )
            results.append(result)
            if args.sleep_sec > 0:
                time.sleep(args.sleep_sec)

    payload = {
        "probe_dir": str(probe_dir),
        "started_at": min((item.started_at for item in results), default=""),
        "finished_at": max((item.finished_at for item in results), default=""),
        "results": [item.__dict__ for item in results],
    }
    write_json(probe_dir / "summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
