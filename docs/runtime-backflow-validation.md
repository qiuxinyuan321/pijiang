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
- authority contract / baseline admission gate
  - `run_manifest.json` 现在显式写出：
    - `run_role`
    - `run_grade`
    - `allow_degraded`
    - `guardian_layer`
    - `namespace_boundary`
    - `admission_path`
  - 每轮 formal run 现在会落：
    - `03-seat-registry.json`
    - `04-provider-preflight-snapshot.json`
    - `02-topology-report.md`
    - `75-baseline-admission.md`
  - `Baseline Admission Gate` 不再靠口头解释，而是会显式裁决 `admitted / candidate-denied / not-eligible`
- 搜索位硬化
  - `search-1 / search-2` 不再只是名义搜索位
  - 搜索 seat 若没有证据，不应被视作正常成功
- 并行幽灵隔离
  - `ExecutionPolicy.parallel_policy` 已接通
  - 当前支持：
    - `strict_all`
    - `ghost_isolation`
  - 完整议会主线默认采用 `ghost_isolation`
  - 达到 `standard11-quorum6` 后，少数慢 seat 不再阻塞 fusion
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
    - `watcher/watcher-ledger.json`
    - `06-juezhe-watch.md`
  - 当前默认负责：
    - 卡顿/静默告警
    - 上次中断 run 的失败收尾修复
    - 受控降级与运行异常建议
  - 当前 precision hardening 已新增：
    - 多源 heartbeat 判定
    - guardian ledger
    - `alert -> no_action` 结构化解释链

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

## 当前验证基线

当前与 `standard11` 切换最相关的真实证据固定看四条：

- 四裨将显式回归与 11 席公开议会定向会
  - run: `sf-20260320-194846-73268`
  - mode: `standard10`
  - 结果：`audit_status = success`
  - 含义：这场会冻结了 `standard11`、四个显式 `opencode-*` 裨将、`fusion` 第 11 席、`standard10-legacy`、治理文件与失效策略
- P0a 后首条 formal rerun
  - run: `sf-20260321-165524-26436`
  - mode: `standard11`
  - 结果：`audit_status = degraded`
  - 原因：truth audit 仍把 `fusion` seat 当普通 lane，误压成 `timeout_partial_only`
  - 含义：这条 run 的价值是暴露 authority gate 前最后一条审计语义缺口
- 当前 admitted baseline
  - run: `sf-20260321-173637-34080`
  - mode: `standard11`
  - 结果：`audit_status = success`
  - 结果：`baseline_admitted = true`
  - 含义：`standard11` 现在已经拿到新的真实 formal success baseline，而不是只停留在纸面 canonical
- watcher precision verification run
  - run: `sf-20260321-200827-26632`
  - mode: `standard11`
  - 结果：`audit_status = success`
  - 结果：`watcher_alert_count = 0`
  - 含义：admitted 后第一轮 guardian precision verification 已把上一轮 `9` 条误报压到 `0`
- 历史 `standard10` 成功 baseline
  - run: `sf-20260320-154315-30532`
  - mode: `standard10`
  - 结果：`audit_status = success`
  - 含义：保留为历史参考，不再承担当前 canonical baseline 角色

## benchmark gate 摘要

当前 benchmark taxonomy 已经升级成：

- `single`
- `reduced6`
- `standard11`

但这三档现在要分开理解：

- `single`
  - 已有历史真实样本
  - 继续作为 formal benchmark 档位
- `reduced6`
  - 继续保留为 experimental evaluation profile
  - 在 seat list 与对外口径冻结前，不作为正式主结论
- `standard11`
  - 已成为唯一公开 canonical/default profile
  - 当前 admitted formal baseline：`sf-20260321-173637-34080`

结论不是“11 席在所有任务上都彻底稳定”，而是：

- benchmark taxonomy、seat/profile 合同、authority contract 与 admission gate 都已经落地
- 真实失败与退化仍然会被留痕，而不是被成功表象掩盖
- `sf-20260321-165524-26436` 证明了 formal rerun 仍会继续产出真实 regression 输入
- `sf-20260321-173637-34080` 证明新的 standard11 authority baseline 已经能被真实 gate 放行
- `sf-20260321-200827-26632` 证明 watcher precision hardening 已经开始收口 guardian credibility

基于这四条真实样本，本轮只回流以下能力：

- progress snapshot 增强
- run 后 truth audit
- regression cases/index
- authority contract / baseline admission gate
- watcher precision hardening / guardian ledger
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
