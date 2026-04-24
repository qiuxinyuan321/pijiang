"""Provider presets for `cpj config add-provider <preset>`.

Each preset knows how to create a ProviderProfile with sensible defaults for a
specific relay / official API. The preset leaves ``config_status`` at
``needs_setup`` and picks a canonical ``api_key_env`` — the user still has to
set the env var; ``cpj doctor --fix`` will promote to ``configured`` once the
env is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import ProviderCapabilities, ProviderProfile


@dataclass
class ProviderPreset:
    """Recipe for materialising a ProviderProfile."""

    preset_id: str
    name: str
    description: str
    adapter_type: str
    default_model: str
    quality_tier: str = "strong"
    roles: list[str] = field(default_factory=list)
    base_url: str = ""
    api_key_env: str = ""
    transport: str = "openai-compatible"
    supports_json_schema: bool = True
    supports_planning: bool = False
    supports_external_search: bool = False
    priority: int = 100
    notes: str = ""

    def build_profile(
        self,
        *,
        profile_id: str | None = None,
        model: str | None = None,
    ) -> ProviderProfile:
        """Return a new ProviderProfile for this preset."""
        capabilities = ProviderCapabilities(
            supports_text=True,
            supports_structured_json=True,
            supports_json_schema=self.supports_json_schema,
            supports_planning=self.supports_planning,
            supports_external_search=self.supports_external_search,
            supports_toolless_readonly=True,
            transport=self.transport,
        )
        return ProviderProfile(
            id=profile_id or self.preset_id,
            adapter_type=self.adapter_type,
            model=model or self.default_model,
            roles=list(self.roles) if self.roles else ["controller"],
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            priority=self.priority,
            enabled=True,
            config_status="needs_setup",
            quality_tier=self.quality_tier,
            capabilities=capabilities,
            notes=self.notes,
        )


# Curated preset catalogue. Keep this list short; exotic relays can still use
# `cpj init` output as the base and edit by hand.
PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        preset_id="openai",
        name="OpenAI 官方",
        description="OpenAI 官方 API（chat/completions）。",
        adapter_type="openai_compatible",
        default_model="gpt-5.4",
        quality_tier="elite",
        roles=["controller"],
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        priority=10,
        notes="官方 API。强模型适合做 controller。",
    ),
    "openai-compatible": ProviderPreset(
        preset_id="openai-compatible",
        name="通用 OpenAI-compatible 中转",
        description="任意 OpenAI-compatible 中转。你需要手工填 base_url / relay_url。",
        adapter_type="openai_compatible",
        default_model="gpt-5.4",
        roles=["controller"],
        base_url="",
        api_key_env="OPENAI_API_KEY",
        priority=15,
        notes="add-provider 后请编辑 base_url 或 relay_url 指向你的中转。",
    ),
    "alibaba-coding-plan": ProviderPreset(
        preset_id="alibaba-coding-plan",
        name="阿里百炼 Coding Plan",
        description="阿里百炼官方 Planning Provider。",
        adapter_type="planning_api",
        default_model="alibaba-coding-plan",
        quality_tier="elite",
        roles=["planning"],
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="ALIBABA_CODING_PLAN_API_KEY",
        transport="planning-api",
        supports_planning=True,
        priority=20,
        notes="官方一等公民 Planning Provider。",
    ),
    "volcengine-coding-plan": ProviderPreset(
        preset_id="volcengine-coding-plan",
        name="火山引擎 Coding Plan",
        description="火山引擎官方 Planning Provider 备用位。",
        adapter_type="planning_api",
        default_model="volcengine-coding-plan",
        quality_tier="elite",
        roles=["planning"],
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key_env="VOLCENGINE_CODING_PLAN_API_KEY",
        transport="planning-api",
        supports_planning=True,
        priority=30,
        notes="官方一等公民 Planning Provider 备用位。",
    ),
    "ollama-local": ProviderPreset(
        preset_id="ollama-local",
        name="本机 Ollama",
        description="本机运行的 Ollama 服务，默认端口 11434。",
        adapter_type="ollama",
        default_model="llama3.1:8b-instruct",
        quality_tier="standard",
        roles=["controller"],
        base_url="http://127.0.0.1:11434",
        api_key_env="",
        transport="ollama",
        priority=40,
        notes="本地模型，适合离线 / 隐私敏感场景。",
    ),
    "openrouter": ProviderPreset(
        preset_id="openrouter",
        name="OpenRouter 聚合",
        description="OpenRouter 聚合平台（OpenAI-compatible）。",
        adapter_type="openai_compatible",
        default_model="openai/gpt-5.4",
        quality_tier="strong",
        roles=["controller"],
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        priority=25,
        notes="一把 key 打多家模型，适合测试期；生产建议直连官方。",
    ),
    "fushengyunsuan": ProviderPreset(
        preset_id="fushengyunsuan",
        name="浮生云算中转站",
        description="浮生云算 Claude/GPT/GLM 聚合中转（OpenAI-compatible）。",
        adapter_type="openai_compatible",
        default_model="claude-opus-5.2",
        quality_tier="elite",
        roles=["controller"],
        base_url="https://fushengyunsuan.cn/v1",
        api_key_env="FUSHENGYUNSUAN_API_KEY",
        priority=18,
        notes="社区中转站，支持 Claude / GPT / GLM 等。",
    ),
    "siliconflow": ProviderPreset(
        preset_id="siliconflow",
        name="硅基流动 SiliconFlow",
        description="硅基流动 OpenAI-compatible 聚合 API。",
        adapter_type="openai_compatible",
        default_model="Qwen/Qwen3.5-235B-A22B-Instruct-2507",
        quality_tier="strong",
        roles=["controller"],
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        priority=60,
        notes="真实 relay preset，默认 needs_setup；doctor --fix 会在 env 就绪后推进。",
    ),
    "deepseek": ProviderPreset(
        preset_id="deepseek",
        name="DeepSeek 官方",
        description="DeepSeek 官方 OpenAI-compatible API。",
        adapter_type="openai_compatible",
        default_model="deepseek-chat",
        quality_tier="strong",
        roles=["controller"],
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        priority=65,
        notes="适合作为强推理/代码讨论补充位，默认不自动启用为 configured。",
    ),
}


def list_presets() -> list[ProviderPreset]:
    """Return presets in a stable order (priority then id)."""
    return sorted(PROVIDER_PRESETS.values(), key=lambda item: (item.priority, item.preset_id))


def get_preset(preset_id: str) -> ProviderPreset | None:
    return PROVIDER_PRESETS.get(preset_id)
