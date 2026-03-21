# standard11 执行合同

这页不是路线图，也不是宣传文案。它只负责把 `sf-20260320-194846-73268` 这场成功定向会冻结下来的执行规则写清楚。

## 1. Canonical Profile

- 唯一公开 canonical/default profile 是 `standard11`。
- `standard10` 不再是公开主名，只能作为输入兼容 token 进入 `standard10-legacy`。
- `standard10-legacy` 只用于历史读取、复盘和受控重放，不得静默冒充 `standard11`。

## 2. Canonical Roster

`standard11` 的公开 seat 顺序固定为：

1. `controller`
2. `planning`
3. `search-1`
4. `search-2`
5. `opencode-kimi`
6. `opencode-glm5`
7. `opencode-minimax`
8. `opencode-qwen`
9. `chaos`
10. `skeptic`
11. `fusion`

这组 seat id 和顺序都是公开接口的一部分。

## 3. Legacy Boundary

- `marshal-1 / marshal-2 / marshal-3` 退出 canonical。
- 它们只能存在于 legacy parser、迁移说明和历史产物解释里。
- 新 README、新图解、新 run output、新 benchmark 主表里不得继续出现 `marshal-*`。

## 4. Fusion Boundary

- `fusion` 保留为第 11 席正式 seat。
- 旧的流程阶段名不能继续和 seat 名混用；阶段语义应逐步收敛到 `final-synthesis`。
- `fusion` 不得被拿来掩盖缺席 seat，也不能作为“隐形会后处理”存在。

## 5. Manifest Contract

`run_manifest.json` 至少必须写出这些字段：

- `requested_profile`
- `effective_profile`
- `run_role`
- `run_grade`
- `allow_degraded`
- `seat_registry_version`
- `resolved_seats`
- `legacy_compat_applied`
- `degraded_state`
- `guardian_layer`
- `namespace_boundary`
- `admission_path`

如果 manifest 不能同时证明这些点，本轮 run 不得被叫作 canonical `standard11` 运行。

## 6. Failure Policy

- `standard11` 的默认策略是硬失败。
- 任一 canonical seat 不可用时，不得静默替补，也不得偷换 seat。
- 只有调用方显式启用 `allow_degraded`，才允许生成 `standard11-degraded`。
- `standard11-degraded` 不得计入正式 baseline，也不得进入正式 benchmark 主表。

## 7. Benchmark Taxonomy

- formal taxonomy：`single / standard11`
- experimental taxonomy：`reduced6`

当前 `reduced6` 仍然保留为实验位。它在精确 seat list、存在理由和对外口径同时冻结前，不与 `standard11` 并列承担公开主结论。

## 8. Guardian Layer

- `觉者` 固定属于 guardian layer。
- 它不是第 12 个投票席位。
- 它不进入 seat roster，不参与 quorum，不进入 benchmark seat 计数。
- 它的留痕应走独立 guardian metadata，而不是混入 council seats。

## 9. Authority Admission

- 默认真实 run 身份固定为：
  - `run_role = requalification`
  - `run_grade = formal`
- `demo` 与 `shadow` 都不能冒充 authority baseline run。
- Baseline Admission Gate 的 companion docs 固定为：
  - `docs/contracts/65-namespace-boundary.md`
  - `docs/contracts/70-baseline-admission-charter.md`
- 通过 gate 前，run 只能算 requalification evidence，不能事后补写成 authority baseline。

## 10. Release Gate

发布顺序固定为：

1. 冻结 decision matrix 和 execution contract。
2. 落单一 Seat/Profile Registry、Namespace Boundary 与 Baseline Admission Charter。
3. 在分支内完成本地 proof。
4. 同车切换 `tools.solution_factory`、`pijiang.factory`、README、图解、支持矩阵、首次成功路径和 benchmark 口径。

不允许对外长期双轨，也不允许“代码已经切了、文档稍后再补”。

## 11. Current Evidence

- 成功定向会：`sf-20260320-194846-73268`
- 当前最新 `standard11` baseline 重跑尝试：`sf-20260320-211359-7232`

第二条 run 的作用是提供真实 regression 输入，而不是让文档去假装它已经成功。当前这份合同只基于已经成功收敛的会议结论写入。
