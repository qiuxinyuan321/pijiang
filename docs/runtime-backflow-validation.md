# Runtime Backflow Validation

这份文档只记录已经从本地议会回流到 `皮匠`，并且已经在 `pijiang/factory` 主运行链内接通的能力。

## 本轮已回流能力

- 运行中状态快照增强
  - `status.json` 现在会持续写出 `running_seat_ids`、`current_seat_id`、`updated_at`
  - 运行中会持续刷新 `current_message`
- run 后 truth audit
  - 每次 run 完成后自动写出 `70-run-truth-audit.json`
  - summary 会回填 `truth_audit_path`、`fake_success_flag_count`、`regression_case_count`
- regression cases
  - 失败或退化 seat 会写入 `regression-cases/`
  - 同步生成 `80-regression-cases-index.md`
- seat 质量门
  - seat 正文在落成最终 Markdown 前，会经过 canonical headings、section completeness、污染标记与搜索证据检查
  - 当前只接通 `ExecutionPolicy.max_attempts_per_seat` 与 `retry_backoff_seconds`
- 搜索位硬化
  - `search-1 / search-2` 不再只是名义搜索位
  - 搜索 seat 若没有证据，不应被视作正常成功

## 当前不宣称完成的能力

下面这些能力仍然保留为类型或未来治理方向，但这轮不会对外宣称已经正式生效：

- `soft_budget`
- `hard_budget`
- `circuit_breaker_threshold`
- `quality_retry_threshold`
- fallback replacement
- 本地议会的字节级 subprocess streaming

## 验证基线

当前已经确认的真实验证基线包括：

- 本地议会 `standard10` current-review
  - run: `sf-20260318-232515-84632`
  - 结果：`fake_success = 0`，`evidence_integrity = 100`，`fusion_integrity = 100`
  - 已暴露真实未解项：`opencode-glm5` schema failure，以及多条成功 seat 仍存在 `missing_sections`
- 本地议会 `single`
  - run: `sf-20260318-235633-84632`
  - 结果：`fake_success = 0`
  - 说明：因为没有搜索 seat，`evidence_coverage` 不能和 `reduced6 / standard10` 直接横比
- 本地议会 `reduced6`
  - run: `sf-20260319-003734-84632`
  - 结果：`fake_success = 0`，`evidence_integrity = 100`
  - 说明：少席位模式更稳，但结构完整度仍低于理想值

## benchmark gate 摘要

本轮 `single / reduced6 / standard10` 已全部收齐，内部 benchmark 摘要如下：

- `single`
  - `provider_calls = 7`
  - `estimated_cost = 7.0`
  - `failed_rate = 0`
  - `fake_success_rate = 0`
- `reduced6`
  - `provider_calls = 12`
  - `estimated_cost = 16.8`
  - `failed_rate = 0`
  - `fake_success_rate = 0`
  - 已知退化项：`codex-chaos`、`codex-github-cases`、`codex-gpt`、`codex-web-research`
- `standard10`
  - `provider_calls = 16`
  - `estimated_cost = 28.8`
  - `failed_rate = 0.1`
  - `fake_success_rate = 0`
  - 已知退化项：`codex-chaos`、`codex-github-cases`、`codex-web-research`、`opencode-glm5`、`opencode-kimi`

结论不是“10 席已经完美”，而是：

- benchmark gate 已经证明这轮回流能力没有制造伪成功
- 真实失败与退化已经被留痕，而不是被成功表象掩盖
- 因此只回流已经被验证有效的 runtime/审计/质量门能力，不把 budget/circuit breaker 一起带进来

基于这三条真实样本，本轮只回流以下能力：

- progress snapshot 增强
- run 后 truth audit
- regression cases/index
- seat 质量门
- 搜索位证据约束

下面这些方向仍明确不回流：

- budget / circuit breaker / fallback replacement
- 本地议会的字节级 subprocess streaming
- 任何未经过 benchmark gate 的前沿试验能力
