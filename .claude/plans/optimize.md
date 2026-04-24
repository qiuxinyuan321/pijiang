# 皮匠项目优化计划

## 概述
基于代码审查，执行 P0/P1 级优化，消除代码重复、改善可维护性，并推送到 GitHub。

---

## 第一步：消除 tools/solution_factory/core.py 与 pijiang/factory/ 的代码重复

**问题**：`core.py` 中大量函数与 `runtime_support.py` 完全重复（~620 行）

**操作**：
1. 删除 `core.py` 中重复的常量和函数，改为从 `pijiang.factory.runtime_support` 导入：
   - `CANONICAL_SECTIONS`, `SECTION_ALIASES`, `SECTION_ALIAS_MAP`
   - `FINAL_DECISIONS_SCHEMA`, `FINAL_DRAFT_SCHEMA`
   - `utc_now_iso()`, `ensure_directory()`, `write_text()`, `write_json()`
   - `normalize_heading()`, `stage_marker_block()`, `frontmatter_block()`
   - `LaneSpec`, `LaneResult` (数据类)
   - `parse_variant_sections()`, `normalize_variant_markdown()`
   - `render_brief_markdown()`, `render_stage_markdown()`, `render_decisions_markdown()`
   - `render_final_draft_markdown()`, `render_index_markdown()`
   - `build_variant_prompt()`, `build_idea_map_prompt()`, `build_debate_round_prompt()`
   - `build_final_decisions_prompt()`, `build_final_draft_prompt()`

2. 保留 `core.py` 中 **独有** 的逻辑（遗留版特有）：
   - `SolutionFactory` 类、`SolutionFactoryConfig`
   - `PreparedCommand`, `RunTracker`, `_HeartbeatLoop`（遗留版实现）
   - `build_lane_command()`, `build_codex_fusion_command()`, `build_claude_fusion_command()`
   - `resolve_command_prefix()`, `parse_opencode_event_stream()`
   - `ensure_claude_runtime_ready()`, lane presets/aliases
   - `render_failed_variant_markdown()`, `render_preflight_markdown()`
   - `build_retry_variant_prompt()`, `append_jsonl()`

3. 注意两版本有微小差异的函数（如 `build_variant_prompt` 中 opencode hardening vs search hardening、`render_decisions_markdown` 中 lane 写死 `codex-gpt` vs `fusion`），需保留遗留版差异部分，方式为：
   - 遗留版特有的 prompt 函数（含不同 lane_id/hardening）保留在 core.py，用不同名字或包装

## 第二步：提取测试辅助函数到共享模块

**问题**：`write_fake_cli()` 在 3 个测试文件中重复（~300 行）

**操作**：
1. 创建 `tests/conftest.py`，提取公共的 `write_fake_cli()` 函数
2. 通过参数控制差异（如 `PIJIANG_FAKE_BAD_LANE`、`PIJIANG_FAKE_SLOW_LANES` 支持）
3. 三个测试文件改为从 conftest 导入

## 第三步：拆分 CouncilEngine.run() 为子方法

**问题**：`run()` ~400 行，承担全部职责

**操作**：
将 `council.py` 的 `run()` 拆为：
- `_run_preflight()` — readiness check + manifest
- `_run_bootstrap()` — brief/overview/authority artifacts
- `_run_variants()` — 并行变体生成 + quorum 逻辑
- `_run_fusion_pipeline()` — idea-map → debate → decisions → draft
- `_run_finalize()` — audit + admission + watcher + summary

`run()` 变为高层编排，调用这 5 个子方法。

## 第四步：引入 logging 模块

**操作**：
1. 在 `pijiang/factory/__init__.py` 中设置包级 logger
2. 在 `council.py`、`providers.py`、`watcher.py` 中用 `logger.info/debug/warning/error` 替代关键 print/隐式输出
3. 保持轻量，不大改现有行为

## 第五步：修复小问题

1. `watcher.py:74` — `__import__("datetime")` 改为标准导入
2. `pyproject.toml` — 确认 dev 依赖已声明（已有 pytest>=8.0，无需改）
3. 版本号 bump 到 `0.2.0`

## 第六步：运行测试 + 推送 GitHub

1. `pytest tests/` 验证全部通过
2. git commit + push 到 origin
