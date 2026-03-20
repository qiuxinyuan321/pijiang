# Runtime Backflow Validation

这份文档只记录已经从本地议会回流到 `皮匠`，并且已经在 `pijiang/factory` 主运行链内接通的能力。

返回总导航见 [index.md](index.md)。

如果你只想先看当前这一轮最新真实 baseline 与 `觉者` 守护层快照，请先读 [current-baseline-and-watcher.md](current-baseline-and-watcher.md)。

## 本轮已回流能力

- 运行中状态快照增强
  - `status.json` 现在会持续写出 `running_seat_ids`、`current_seat_id`、`updated_at`
  - 运行中会持续刷新 `current_message`
- run 后 truth audit
  - 每次 run 完成后自动写出 `70-run-truth-audit.json`
  - summary 会回填 `truth_audit_path`、`fake_success_flag_count`、`regression_case_count`
  - `truth audit` 现在会显式给出 `audit_status` 与 `reason_codes`
- regression cases
  - 失败或退化 seat 会写入 `regression-cases/`
  - 同步生成 `80-regression-cases-index.md`
- seat 质量门
  - seat 正文在落成最终 Markdown 前，会经过 canonical headings、section completeness、污染标记与搜索证据检查
  - 当前只接通 `ExecutionPolicy.max_attempts_per_seat` 与 `retry_backoff_seconds`
- provider preflight 语义
  - `cpj doctor` 与 `cpj run` 现在共享同一套 preflight gate
  - `cpj run` 会明确拒绝带 blocker 的真实 provider 调用
- 搜索位硬化
  - `search-1 / search-2` 不再只是名义搜索位
  - 搜索 seat 若没有证据，不应被视作正常成功
- 并行幽灵隔离
  - `ExecutionPolicy.parallel_policy` 已接通
  - 当前支持：
    - `strict_all`
    - `ghost_isolation`
  - 完整议会主线默认采用 `ghost_isolation`
  - 达到 `standard10-quorum6` 后，少数慢 seat 不再阻塞 fusion
  - cutover 后会显式记录：
    - `ghosted_lane_ids`
    - `late_lane_ids`
    - `fusion_cutover_ms`
- `觉者` 守护层
  - 当前 `cpj run` 与 `tools.solution_factory run` 可启用 `watcher`
  - `watcher` 代表用户身份盯整条任务执行链的稳定性，而不是加入主议会投票
  - 当前会显式留痕：
    - `watcher/watcher-events.jsonl`
    - `watcher/watcher-alerts.json`
    - `watcher/watcher-actions.json`
    - `06-juezhe-watch.md`
  - 当前默认负责：
    - 卡顿/静默告警
    - 上次中断 run 的失败收尾修复
    - 受控降级与运行异常建议

## 当前不宣称完成的能力

下面这些能力仍然保留为类型或未来治理方向，但这轮不会对外宣称已经正式生效：

- `soft_budget`
- `hard_budget`
- `circuit_breaker_threshold`
- `quality_retry_threshold`
- fallback replacement
- 本地议会的字节级 subprocess streaming
- 动态 seat 重排
- 流式预融合

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
- 本地议会当前同议题重跑
  - run: `sf-20260319-104416-60156`
  - 结果：已能完整产出 `50-fusion-decisions.md`、`70-run-truth-audit.json`、`80-regression-cases-index.md`、`90-final-solution-draft.md`
  - 状态：`audit_status = degraded`
  - 说明：这次证明了本地议会已恢复“完整收敛链路”，但 seat 级稳定性仍未收敛到 `success`
- 本地失败样本回审
  - run: `sf-20260319-090954-84856`
  - 结果：现在可被识别为 `fusion_parse_failure`
  - 说明：旧失败不再只是历史事故，而是正式 regression case

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
- `standard10` 当前只是 `display default`，不是默认最优结论
- `reduced6` 当前只是 `evaluation profile`，不是官方推荐配置

基于这三条真实样本，本轮只回流以下能力：

- progress snapshot 增强
- run 后 truth audit
- regression cases/index
- seat 质量门
- 搜索位证据约束
- 幽灵堵车隔离并行

下面这些方向仍明确不回流：

- budget / circuit breaker / fallback replacement
- 本地议会的字节级 subprocess streaming
- 任何未经过 benchmark gate 的前沿试验能力
- 觉者对内容层正文的直接改写权

## 幽灵堵车隔离语义

这轮正式把“少数幽灵堵车拖死三车道”的问题翻译成运行器语义：

- `strict_all`
  - 旧语义
  - 所有 seat 都结束后才允许进入 fusion
- `ghost_isolation`
  - 新语义
  - 对完整议会主线，当达到法定人数后，剩余慢 seat 会被隔离，不再阻塞 cutover

当前 `皮匠` 的法定人数条件固定为：

- 总成功席位至少 `6`
- 且必须包含：
  - `controller`
  - 至少 1 个 `planning`
  - 至少 1 个 `search`
  - 至少 1 个 `marshal`
  - 至少 1 个对抗席位：`chaos` 或 `skeptic`

这意味着：

- 少数慢 seat 不再自动等同于整场会议卡死
- 关键席位缺失时仍然拒绝 cutover
- 迟到结果会留痕，但不会回写当前 fusion 决策

## 本地议会正在继续推进、但尚未完整回流的方向

当前本地议会已经进入“自省强化 + seat schema-first”阶段，但这部分仍然优先留在本地实验场：

- 本地自省 cycle
  - 最新 cycle:
    - `iter-20260319-130615`
  - 说明：
    - 已固定产出 `00-meta-brief.md / 60-delta-report.md / 70-run-truth-audit.json / 90-next-iteration-brief.md`
    - 这套机制目前仍属于本地议会内部能力，不作为 `cpj` 的公开主命令
- seat schema-first
  - 本地议会已经开始把 variant 输出往 `SeatResult JSON -> Markdown` 迁移
  - 当前真实验证结果：
    - `sf-20260319-130615-30340` / `failed_lane_count = 9`
    - `sf-20260319-151806-111592` / `failed_lane_count = 7`
  - 结论：
    - 真实 10 路 seat 稳定性有改善，但主 reason code 仍集中在 `schema_failure`
    - 因此这一层还不应整体回流到 `皮匠` 运行器，只同步稳定契约字段

当前已经同步到 `皮匠` 的，只是这部分实验的稳定表达层：

- `RunTruthAudit.audit_status`
- `RunTruthAudit.reason_codes`
- `QualityAssessment.reason_codes`
- 文档中的 `display default / evaluation profile / recommended config` 口径纪律
