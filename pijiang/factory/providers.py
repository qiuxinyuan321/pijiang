from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .endpoints import build_chat_endpoint
from .types import ExecutionRequest, ExecutionResponse, ProviderCapabilities, ProviderProfile


class ProviderExecutionError(RuntimeError):
    pass


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def profile_from_payload(payload: dict[str, Any]) -> ProviderProfile:
    capabilities = ProviderCapabilities(**dict(payload.get("capabilities") or {}))
    data = dict(payload)
    data["capabilities"] = capabilities
    return ProviderProfile(**data)


def _extract_json_block(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def _message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise ProviderExecutionError("provider response does not contain choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts).strip()
    return str(content).strip()


def _parse_opencode_event_stream(stdout_text: str) -> str:
    text_parts: list[str] = []
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = payload.get("part", {})
        if payload.get("type") == "text" and isinstance(part, dict):
            text = str(part.get("text", "")).strip()
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts).strip()


_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _semver_key(value: str) -> tuple[int, int, int]:
    matched = _SEMVER_RE.search(value)
    if not matched:
        return (0, 0, 0)
    return tuple(int(part) for part in matched.groups())


def _resolve_opencode_command() -> list[str]:
    explicit = os.environ.get("PIJIANG_OPENCODE_PATH", "").strip() or os.environ.get("OPENCODE_PATH", "").strip()
    if explicit and Path(explicit).expanduser().exists():
        return [str(Path(explicit).expanduser())]
    resolved = shutil.which("opencode")
    if resolved:
        return [resolved]
    bun_root = Path.home() / ".bun" / "install" / "cache"
    candidates: list[Path] = []
    if bun_root.exists():
        for directory in bun_root.glob("opencode-windows-x64@*"):
            executable = directory / "bin" / "opencode.exe"
            if executable.exists():
                candidates.append(executable)
    if candidates:
        candidates.sort(key=lambda item: (_semver_key(item.parent.parent.name), item.stat().st_mtime), reverse=True)
        return [str(candidates[0])]
    raise ProviderExecutionError("unable to resolve an opencode executable")


@dataclass
class BaseProviderAdapter:
    profile: ProviderProfile

    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        raise NotImplementedError


class OpenAICompatibleAdapter(BaseProviderAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        api_key = os.environ.get(self.profile.api_key_env, "").strip()
        if self.profile.api_key_env and not api_key:
            raise ProviderExecutionError(f"profile {self.profile.id} requires env {self.profile.api_key_env}")

        try:
            url = build_chat_endpoint(self.profile)
        except ValueError as exc:
            raise ProviderExecutionError(str(exc)) from exc
        payload: dict[str, Any] = {
            "model": self.profile.model,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.schema is not None:
            payload["response_format"] = {"type": "json_object"}
        raw = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        http_request = urllib.request.Request(url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=request.timeout_sec) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ProviderExecutionError(f"{self.profile.id} request failed: {exc}") from exc
        parsed = json.loads(body)
        content = _message_content(parsed)
        if request.schema is not None:
            content = json.dumps(_extract_json_block(content), ensure_ascii=False)
        return ExecutionResponse(
            content=content,
            raw_stdout=body,
            provider_id=self.profile.id,
            model=self.profile.model,
            metadata={"transport": "openai-compatible"},
        )


class PlanningApiAdapter(OpenAICompatibleAdapter):
    pass


class OllamaAdapter(BaseProviderAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        try:
            url = build_chat_endpoint(self.profile)
        except ValueError as exc:
            raise ProviderExecutionError(str(exc)) from exc
        payload: dict[str, Any] = {
            "model": self.profile.model,
            "stream": False,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.schema is not None:
            payload["format"] = "json"
        raw = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        http_request = urllib.request.Request(url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=request.timeout_sec) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ProviderExecutionError(f"{self.profile.id} request failed: {exc}") from exc
        parsed = json.loads(body)
        message = parsed.get("message", {})
        content = str(message.get("content", "")).strip()
        if request.schema is not None:
            content = json.dumps(_extract_json_block(content), ensure_ascii=False)
        return ExecutionResponse(
            content=content,
            raw_stdout=body,
            provider_id=self.profile.id,
            model=self.profile.model,
            metadata={"transport": "ollama"},
        )


class CommandBridgeAdapter(BaseProviderAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        if not self.profile.command:
            raise ProviderExecutionError(f"profile {self.profile.id} is missing command bridge settings")
        command = [str(item) for item in self.profile.command]
        schema_path: Path | None = None
        if request.output_path is not None:
            command.extend(["--output-last-message", str(request.output_path)])
        if request.schema is not None and request.output_path is not None:
            schema_path = request.output_path.with_suffix(".schema.json")
            schema_path.write_text(json.dumps(request.schema, ensure_ascii=False, indent=2), encoding="utf-8")
            command.extend(["--output-schema", str(schema_path)])
        completed = subprocess.run(
            command,
            input=request.prompt,
            text=True,
            capture_output=True,
            timeout=request.timeout_sec,
            check=False,
        )
        if completed.returncode != 0:
            raise ProviderExecutionError(
                f"{self.profile.id} command bridge failed with {completed.returncode}: {(completed.stderr or completed.stdout).strip()}"
            )
        content = ""
        if request.output_path is not None and request.output_path.exists():
            content = request.output_path.read_text(encoding="utf-8").strip()
        if not content:
            content = (completed.stdout or "").strip()
        if request.schema is not None:
            content = json.dumps(_extract_json_block(content), ensure_ascii=False)
        return ExecutionResponse(
            content=content,
            raw_stdout=completed.stdout or "",
            raw_stderr=completed.stderr or "",
            provider_id=self.profile.id,
            model=self.profile.model,
            metadata={"transport": "command-bridge", "command": command},
        )


class OpencodeAdapter(BaseProviderAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        command = _resolve_opencode_command() + [
            "run",
            "--format",
            "json",
            "--dir",
            str(Path.cwd()),
            "--model",
            self.profile.model,
            "--variant",
            "max",
            request.prompt,
        ]
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=request.timeout_sec,
            check=False,
        )
        if completed.returncode != 0:
            raise ProviderExecutionError(
                f"{self.profile.id} opencode failed with {completed.returncode}: {(completed.stderr or completed.stdout).strip()}"
            )
        content = _parse_opencode_event_stream(completed.stdout or "")
        if not content:
            raise ProviderExecutionError(f"{self.profile.id} opencode returned no final text content")
        if request.schema is not None:
            content = json.dumps(_extract_json_block(content), ensure_ascii=False)
        return ExecutionResponse(
            content=content,
            raw_stdout=completed.stdout or "",
            raw_stderr=completed.stderr or "",
            provider_id=self.profile.id,
            model=self.profile.model,
            metadata={"transport": "opencode", "command": command},
        )


class DemoAdapter(BaseProviderAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        prompt = request.prompt
        lane_id = "unknown-seat"
        stage = "variant"
        for line in prompt.splitlines():
            if line.startswith("SF-LANE-ID:"):
                lane_id = line.split(":", 1)[1].strip()
            if line.startswith("SF-STAGE:"):
                stage = line.split(":", 1)[1].strip()
        if stage == "variant":
            evidence_block = ""
            if lane_id in {"search-1", "search-2"}:
                evidence_block = (
                    "- 证据：https://example.com/pijiang/demo-search-note\n"
                    "- 证据：https://github.com/example/pijiang-demo-case\n"
                    "- 证据：https://example.com/pijiang/demo-benchmark\n\n"
                )
            content = (
                f"# 问题定义\n{lane_id} 的示例输出\n\n"
                f"{evidence_block}"
                "# 目标与非目标\n演示皮匠安装后无需真实 API 也能看到完整链路。\n\n"
                "# 用户/场景\n新用户首次安装后的 demo 体验。\n\n"
                "# 系统架构\n11 席公开议会 + Obsidian 可视化。\n\n"
                "# 模块拆分\ncpj init / doctor / demo / run。\n\n"
                "# 关键流程\ndemo 配置 -> 11 席产物 -> final-synthesis -> 可视化。\n\n"
                "# 技术选型\nPython + Markdown + Obsidian 模板。\n\n"
                "# 风险与取舍\n演示模式不代表真实 provider 已配置完成。\n\n"
                "# 里程碑\n先验证安装，再配置真实 provider。\n\n"
                "# 待确认问题\n无。\n"
            )
        elif stage == "idea-map":
            content = "# 共识点\n先让用户看到价值。\n\n# 独特亮点\n11 席公开议会。\n\n# 冲突点\n真实 provider 仍需单独配置。\n\n# 质疑焦点\n默认配置会不会误导可直接 real run。\n\n# 可组合点\ndemo + doctor + readiness。\n"
        elif stage.startswith("debate-round-"):
            content = f"# {stage}\n- 议题：先验证体验，再接真实 API。\n- 结论：demo 模式作为新手第一步。\n"
        elif stage == "final-decisions-json":
            content = json.dumps(
                {
                    "decisions": [
                        {
                            "topic": "demo-first onboarding",
                            "decision": "新用户先跑 demo，再配置真实 providers。",
                            "sources": [lane_id],
                            "reason": "避免默认配置下直接撞到 provider 缺失与环境变量错误。",
                            "skeptic_challenge": "demo 会不会掩盖真实复杂度？",
                            "skeptic_rebuttal": "doctor 和 readiness 会明确告诉用户哪些席位仍未就绪。",
                            "rejected_options": [
                                {
                                    "lane": lane_id,
                                    "option": "默认直接 real run",
                                    "reason": "会让新用户在安装后第一时间遇到报错。",
                                }
                            ],
                            "open_questions": [],
                        }
                    ],
                    "fallback_options": [{"topic": "运行模式", "option": "reduced_council_mode"}],
                    "next_validation_steps": ["配置真实 provider 后运行 cpj run"],
                },
                ensure_ascii=False,
            )
        elif stage == "final-draft-json":
            content = json.dumps(
                {
                    "title": "皮匠 demo 终版草案",
                    "sections": [
                        {
                            "title": "demo-first",
                            "content": "先通过 demo 看到 11 席拓扑与完整产物链，再进入真实 provider 配置。",
                            "sources": [lane_id],
                            "rationale": "这样更适合新用户部署与验收。",
                            "status": "accepted",
                        }
                    ],
                    "open_questions": [],
                    "validation_plan": ["运行 cpj doctor", "运行 cpj demo", "配置真实 provider 后再运行 cpj run"],
                },
                ensure_ascii=False,
            )
        else:
            content = f"# {stage}\n来自 {lane_id} 的 demo 输出。\n"
        if request.output_path is not None:
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_text(content, encoding="utf-8")
        return ExecutionResponse(
            content=content,
            raw_stdout=content,
            provider_id=self.profile.id,
            model=self.profile.model,
            metadata={"transport": "demo"},
        )


def _execute_command_bridge_request(
    profile: ProviderProfile,
    request: ExecutionRequest,
    *,
    cancel_event: Any | None = None,
) -> ExecutionResponse:
    if not profile.command:
        raise ProviderExecutionError(f"profile {profile.id} is missing command bridge settings")
    command = [str(item) for item in profile.command]
    if request.output_path is not None:
        command.extend(["--output-last-message", str(request.output_path)])
    if request.schema is not None and request.output_path is not None:
        schema_path = request.output_path.with_suffix(".schema.json")
        schema_path.write_text(json.dumps(request.schema, ensure_ascii=False, indent=2), encoding="utf-8")
        command.extend(["--output-schema", str(schema_path)])
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdin is not None:
        process.stdin.write(request.prompt)
        process.stdin.close()
    started = time.monotonic()
    while True:
        if process.poll() is not None:
            break
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process_tree(process)
            raise ProviderExecutionError(f"{profile.id} command bridge canceled after quorum cutover")
        if request.timeout_sec > 0 and time.monotonic() - started >= request.timeout_sec:
            _terminate_process_tree(process)
            raise ProviderExecutionError(f"{profile.id} command bridge timed out after {request.timeout_sec}s")
        time.sleep(0.25)
    stdout = process.stdout.read() if process.stdout is not None else ""
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.returncode != 0:
        raise ProviderExecutionError(
            f"{profile.id} command bridge failed with {process.returncode}: {(stderr or stdout).strip()}"
        )
    content = ""
    if request.output_path is not None and request.output_path.exists():
        content = request.output_path.read_text(encoding="utf-8").strip()
    if not content:
        content = (stdout or "").strip()
    if request.schema is not None:
        content = json.dumps(_extract_json_block(content), ensure_ascii=False)
    return ExecutionResponse(
        content=content,
        raw_stdout=stdout or "",
        raw_stderr=stderr or "",
        provider_id=profile.id,
        model=profile.model,
        metadata={"transport": "command-bridge", "command": command},
    )


def _execute_http_request_in_worker(
    profile: ProviderProfile,
    request: ExecutionRequest,
    *,
    cancel_event: Any | None = None,
    worker_dir: Path | None = None,
) -> ExecutionResponse:
    root = (worker_dir or Path.cwd()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    input_path = root / f"{profile.id}.worker-input.json"
    output_path = root / f"{profile.id}.worker-output.json"
    input_path.write_text(
        json.dumps(
            {
                "profile": asdict(profile),
                "request": {
                    "prompt": request.prompt,
                    "output_mode": request.output_mode,
                    "schema": request.schema,
                    "timeout_sec": request.timeout_sec,
                    "output_path": str(request.output_path) if request.output_path is not None else "",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "pijiang.factory.provider_worker", "--input", str(input_path), "--output", str(output_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    started = time.monotonic()
    while True:
        if process.poll() is not None:
            break
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process_tree(process)
            raise ProviderExecutionError(f"{profile.id} worker canceled after quorum cutover")
        if request.timeout_sec > 0 and time.monotonic() - started >= request.timeout_sec:
            _terminate_process_tree(process)
            raise ProviderExecutionError(f"{profile.id} worker timed out after {request.timeout_sec}s")
        time.sleep(0.25)
    stdout = process.stdout.read() if process.stdout is not None else ""
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.returncode != 0:
        raise ProviderExecutionError(f"{profile.id} worker failed with {process.returncode}: {(stderr or stdout).strip()}")
    if not output_path.exists():
        raise ProviderExecutionError(f"{profile.id} worker finished without output payload")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    return ExecutionResponse(
        content=str(payload.get("content", "")),
        raw_stdout=str(payload.get("raw_stdout", "")),
        raw_stderr=str(payload.get("raw_stderr", "")),
        provider_id=str(payload.get("provider_id", profile.id)),
        model=str(payload.get("model", profile.model)),
        metadata=dict(payload.get("metadata") or {}),
    )


def execute_profile_request(
    profile: ProviderProfile,
    request: ExecutionRequest,
    *,
    cancel_event: Any | None = None,
    worker_dir: Path | None = None,
) -> ExecutionResponse:
    if profile.adapter_type == "command_bridge":
        return _execute_command_bridge_request(profile, request, cancel_event=cancel_event)
    if profile.adapter_type == "opencode":
        return OpencodeAdapter(profile).execute(request)
    if profile.adapter_type in {"openai_compatible", "planning_api", "ollama"}:
        return _execute_http_request_in_worker(profile, request, cancel_event=cancel_event, worker_dir=worker_dir)
    return adapter_for_profile(profile).execute(request)


def adapter_for_profile(profile: ProviderProfile) -> BaseProviderAdapter:
    if profile.adapter_type == "openai_compatible":
        return OpenAICompatibleAdapter(profile)
    if profile.adapter_type == "planning_api":
        return PlanningApiAdapter(profile)
    if profile.adapter_type == "ollama":
        return OllamaAdapter(profile)
    if profile.adapter_type == "command_bridge":
        return CommandBridgeAdapter(profile)
    if profile.adapter_type == "opencode":
        return OpencodeAdapter(profile)
    if profile.adapter_type == "demo":
        return DemoAdapter(profile)
    raise ProviderExecutionError(f"unsupported adapter type: {profile.adapter_type}")
