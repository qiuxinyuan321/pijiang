# Baseline Admission Charter

这页只定义 `standard11` authority baseline 的最小准入门。

## 1. 运行身份

- 下一轮真实基线 run 必须在发车前预声明：
  - `run_role = requalification`
  - `run_grade = formal`
- 只有满足预声明门槛的 formal run，才有资格进入 baseline admission。
- `demo`、`shadow`、`degraded`、`legacy replay` 都不属于 authority baseline 候选。

## 2. allow_degraded

- 默认策略是 hard fail。
- `allow_degraded` 只能显式声明，不能事后补写。
- 未显式声明的 degraded run，直接失去 baseline 资格。
- 显式 `allow_degraded = true` 的 run 只允许进入证据池，不允许直接晋升 authority baseline。

## 3. 最低工件集

Baseline Admission Gate 至少要求这些工件存在且可追溯：

- `seat registry`
- `provider preflight snapshot`
- `run_manifest.json`
- `events.jsonl`
- `topology report`
- `final-decisions`
- `final-draft`
- `baseline admission report`

## 4. 最低准入检查

下一轮 `standard11` success baseline 至少同时满足：

- `audit_status = success`
- 无 `topology_mismatch`
- 四个显式裨将都真实在位：
  - `opencode-kimi`
  - `opencode-glm5`
  - `opencode-minimax`
  - `opencode-qwen`
- `watcher / 觉者` 没有污染 vote plane
- `fusion` seat 与 `final-synthesis` phase 都可追溯
- 没有未声明 degraded

## 5. Promotion 结果

- 通过全部检查：`admitted`
- 满足 formal requalification 但 admission gate 未过：`candidate-denied`
- 只是一条 requalification 证据，还没到 baseline：`requalification-only`
- 非 canonical 条件下的 run：`not-eligible`

## 6. 单一 Admission Path

当前 authority admission path 固定为：

1. `docs/contracts/20-decision-matrix.json`
2. `docs/contracts/60-execution-contract.md`
3. `docs/contracts/65-namespace-boundary.md`
4. `docs/contracts/70-baseline-admission-charter.md`

不允许再把 authority 语义散落成多份互相解释的旁注。
