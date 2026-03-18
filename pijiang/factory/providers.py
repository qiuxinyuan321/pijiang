from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .endpoints import build_chat_endpoint
from .types import ExecutionRequest, ExecutionResponse, ProviderProfile


class ProviderExecutionError(RuntimeError):
    pass


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
                "# 系统架构\n10 席多模型议会 + Obsidian 可视化。\n\n"
                "# 模块拆分\ncpj init / doctor / demo / run。\n\n"
                "# 关键流程\ndemo 配置 -> 10 席产物 -> fusion -> 可视化。\n\n"
                "# 技术选型\nPython + Markdown + Obsidian 模板。\n\n"
                "# 风险与取舍\n演示模式不代表真实 provider 已配置完成。\n\n"
                "# 里程碑\n先验证安装，再配置真实 provider。\n\n"
                "# 待确认问题\n无。\n"
            )
        elif stage == "idea-map":
            content = "# 共识点\n先让用户看到价值。\n\n# 独特亮点\n10 席完整议会。\n\n# 冲突点\n真实 provider 仍需单独配置。\n\n# 质疑焦点\n默认配置会不会误导可直接 real run。\n\n# 可组合点\ndemo + doctor + readiness。\n"
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
                            "content": "先通过 demo 看到 10 席拓扑与完整产物链，再进入真实 provider 配置。",
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


def adapter_for_profile(profile: ProviderProfile) -> BaseProviderAdapter:
    if profile.adapter_type == "openai_compatible":
        return OpenAICompatibleAdapter(profile)
    if profile.adapter_type == "planning_api":
        return PlanningApiAdapter(profile)
    if profile.adapter_type == "ollama":
        return OllamaAdapter(profile)
    if profile.adapter_type == "command_bridge":
        return CommandBridgeAdapter(profile)
    if profile.adapter_type == "demo":
        return DemoAdapter(profile)
    raise ProviderExecutionError(f"unsupported adapter type: {profile.adapter_type}")
