# Changelog

本文件记录对外可见的版本变动。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，版本号遵循 SemVer。

## [0.4.0] - 2026-04-24

### 新增

- **`cpj runs`**：列出最近 N 次议会运行，附带 truth-audit 摘要（成功/降级/失败）、席位完成率与开始时间。同时扫描真实运行目录 `cache_root/runs/` 与 demo 目录 `cache_root/demo/runs/`。
- **`cpj show <run-id>`**：展示单次运行的 manifest、status、audit 结论与 25 项标准产物清单；`run-id` 支持唯一前缀匹配。
- **`cpj doctor --fix`**：保守自动修复。把 `api_key_env` 已在环境中就绪的 HTTP provider (`openai_compatible` / `planning_api`) 从 `needs_setup` 推进到 `configured`；不改 endpoint，也不触碰 `opencode` 等非 env 依赖的 adapter。
- **`cpj config list-presets`** / **`cpj config add-provider <preset>`**：内置 7 个常见 provider preset —— OpenAI 官方、通用 OpenAI-compatible 中转、阿里百炼 Coding Plan、火山引擎 Coding Plan、本机 Ollama、OpenRouter、浮生云算。`--force / --id / --model / --relay-url / --base-url / --roles / --json` 全面支持覆盖与自定义。
- **新模块 `pijiang.factory.run_inspect`**：`list_run_summaries` / `find_run_by_id` / `list_run_artifacts` 纯函数式读操作，供 CLI 与未来的面板复用。
- **新模块 `pijiang.factory.presets`**：`ProviderPreset` + `PROVIDER_PRESETS` 集中管理 preset 目录，便于后续扩展。

### 改进

- **Solution Factory 编排复用**：`tools.solution_factory` 不再维护 prompt / preflight / opencode 解析等重复副本，改为复用 `pijiang.factory.runtime_support`，降低 `cpj run` 与 `python -m tools.solution_factory run` 两条真实议会入口的语义漂移风险。
- **Truth audit 的 fusion 边界修正**：`fusion` 现在按融合工件链审计，不再参与普通 seat 完整率分母，也不会因缺少普通 lane `variant_result.json` 被误判为 `timeout_partial_only`。
- **Watcher ledger 精度提升**：`watcher-ledger.json` 新增 `dedupe_key` 与 `merged_count`，同一触发源的重复 alert/action 会合并；缺失工件标签统一归一化，减少大小写与路径形式导致的噪音。
- **HTTP provider 自动重试**：`OpenAICompatibleAdapter` 与 `OllamaAdapter` 现在通过共用的 `_http_post_with_retry` 处理瞬态错误。对 `408 / 429 / 500 / 502 / 503 / 504` 与 `URLError` 做最多 2 次指数退避重试（默认 1s、3s），并解析 `Retry-After`（封顶 30s）。非重试状态码（如 400/401）直接抛错，不浪费调用。
- **HTTP provider 错误可观测性**：partial read、connection reset、timeout、remote disconnect 归入瞬时网络错误并可重试；空响应与非法 JSON 会转成明确的 `ProviderExecutionError`。
- **`_extract_json_block` 鲁棒性提升**：优先选择最后一个 ```json\n...\n``` 代码块；当 prose 夹杂多个 JSON 时，按从最宽到最短扫描平衡花括号 / 方括号直到找到可解析的块，支持流行 LLM 输出风格（前缀寒暄 / 多段候选 / 尾部总结）。
- **`cpj run` 配置回写最小化**：只在首次成功时写回 `onboarding.first_run_acknowledged`。避免在每次成功运行都触达磁盘（对只读模板 / CI mount 配置友好）；写失败降级为 warning，不影响 run 结果。
- **配置迁移层收敛**：`load_config` 兼容旧 `providers` / `topology` / `obsidian` payload 与 `relay_url`，`save_config` 只输出当前 v0.4 结构，避免 legacy 字段继续扩散。
- **Provider preset 扩展**：在原 7 个 preset 基础上补充 SiliconFlow 与 DeepSeek；新增 preset 仍默认 `needs_setup`，不改变默认 provider profile。
- **README 命令面板与"最短接入路径"同步更新**。

### 工程

- **CI**：GitHub Actions workflow 新增 `lint` 与 `type check` 阶段（ruff + mypy）；`pyproject.toml` 补齐 `[tool.ruff]` / `[tool.mypy]` 严格但务实的规则集与 `dev` extra。
- **测试**：新增 `tests/test_v04_enhancements.py`（35 个测试），覆盖 JSON 提取、HTTP 重试（含真实 HTTP 服务器注入 503/400/partial read 场景）、run_inspect 的清单与前缀匹配、`--fix` 的边界条件、preset 目录、legacy config、watcher 去重与 fusion audit 边界。
- **版本号**：`pijiang.__version__` bump 到 `0.4.0`。

### 破坏性变更

无。所有改动向后兼容。

---

## [0.3.0] 及更早

此 CHANGELOG 从 v0.4 开始维护；更早版本的变更请参考 git 历史与各版本 release notes。
