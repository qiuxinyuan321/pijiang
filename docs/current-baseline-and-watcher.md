# 当前真实 Baseline 与觉者守护层

这页只说明当前已经验证成功的真实基线，以及 `standard11` 成为公开 canonical/default profile 之后的当前状态，不承担路线图或历史总账功能。

## 这页回答什么

如果你只想快速知道四件事：

- 当前最新成功的真实 baseline 是什么
- 它已经验证到了什么程度
- standard11 当前进行到哪一步
- `觉者` 守护层到底是什么，不是什么

先看这页就够了。

更完整的历史回流账本仍然在 [runtime-backflow-validation.md](runtime-backflow-validation.md)。

## 当前成功 baseline

| 项目 | 当前值 |
| --- | --- |
| run id | `sf-20260321-200827-26632` |
| mode | `standard11` |
| requested profile | `standard11` |
| effective profile | `standard11` |
| run_role | `requalification` |
| run_grade | `formal` |
| audit_status | `success` |
| seat_integrity_score | `100` |
| evidence_integrity_score | `100` |
| fusion_integrity_score | `100` |
| watcher_enabled | `true` |
| watcher_alert_count | `0` |
| baseline_admitted | `true` |

这条 run 的意义不是“所有场景已经彻底稳定”，而是：

- `standard11` 已拿到新的真实 formal success baseline
- authority contract 与 Baseline Admission Gate 已进入真实运行链
- 四个显式 `opencode-*` 裨将都真实在位
- `truth audit` 与 `觉者` 守护层都已经进入真实运行链
- admitted 后第一轮 watcher precision verification 已把误报压到 `0`

这也是当前仓库里最新一条已经完整通过 `audit_status = success` 且 `baseline_admitted = true` 的 baseline 快照。

## standard11 当前状态

`standard11` 已经不是“纸面 canonical”，而是已经拿到新的 admitted baseline。当前已确认的关键事实是：

| 项目 | 当前值 |
| --- | --- |
| 成功定向会 | `sf-20260320-194846-73268` |
| 定向会角色 | standard11 合同与迁移规则的权威来源 |
| 定向会状态 | `audit_status = success` |
| P0a 后首条 formal rerun | `sf-20260321-165524-26436` |
| rerun 状态 | `audit_status = degraded` |
| 已定位原因 | truth audit 仍把 `fusion` seat 当普通 lane，误压成 `timeout_partial_only` |
| 当前 admitted baseline | `sf-20260321-200827-26632` |
| admitted 状态 | `audit_status = success` + `baseline_admitted = true` |
| guardian 精度信号 | `watcher_alert_count = 0` |

这意味着：

- `standard11` 的 seat/profile 合同与 authority contract 都已经冻结并写进仓库
- `sf-20260321-165524-26436` 的价值是暴露 `fusion` seat 审计误判，而不是被包装成失败叙事
- `sf-20260321-200827-26632` 现在是 current canonical baseline 的最新 admitted 样本

## 你会拿到哪些产物

这条 baseline 当前会产出一整条结构化方案链，而不是只给一句最终答案：

| 工件 | 作用 |
| --- | --- |
| `00-brief.md` | 本轮议题与输入 |
| `02-topology-report.md` | seat / phase / guardian 命名边界与显式拓扑 |
| `03-seat-registry.json` | 本轮 seat registry 快照 |
| `04-provider-preflight-snapshot.json` | 本轮 provider preflight 快照 |
| `watcher/watcher-ledger.json` | guardian judgment / no_action 留痕账本 |
| `30-idea-map.md` | 共识点、冲突点与可组合点 |
| `40-debate-round-1.md` | 第一轮议会对抗 |
| `41-debate-round-2.md` | 第二轮议会对抗 |
| `50-fusion-decisions.md` | 决策账本 |
| `70-run-truth-audit.json` | 本轮 truth audit 裁决 |
| `75-baseline-admission.md` | authority baseline 准入裁决 |
| `80-regression-cases-index.md` | 失败/退化样本入口 |
| `90-final-solution-draft.md` | 当前终版草案 |
| `06-juezhe-watch.md` | 觉者守护层的观察与建议留痕 |

## 觉者是什么

### 觉者是

- 用户化身守护层
- 整条任务执行链的稳定性与中断修复观察者
- 可选 sidecar
- 会显式留痕的运行守护能力

### 觉者不是

- 第 11 个投票席位
- quorum 成员
- fusion 决策者
- 内容正文改写器

一句话说清楚：`觉者` 代表用户身份盯运行稳定性，而不是加入主议会投票。

## 这轮验证了什么

当前已经被真实 run 证实的点包括：

- `standard11` 已恢复为真实可跑，并拿到 admitted baseline
- `opencode` 已重新接回运行链
- `truth audit` 已接通并真实产出
- `觉者` 已接通并真实留痕
- authority manifest 字段已经接通：
  - `run_role`
  - `run_grade`
  - `allow_degraded`
- Baseline Admission Gate 已接通并真实裁决
- `fusion` seat 与 `final-synthesis` phase 的边界已经进入真实审计链
- `guardian ledger` 已接通，`alert -> no_action` 不再是纯噪音日志

## 这轮没有宣称什么

下面这些能力这轮仍然不对外宣称已完成：

- budget / circuit breaker
- fallback replacement
- 内容层由 `觉者` 自动改写
- 流式预融合

## 如何复现

如果你想复现这条路径，先用最短命令走官方主线：

```powershell
cpj doctor
cpj run --watcher auto
python -m tools.solution_factory run --brief <brief.md> --project-path <topic-path> --lanes standard11 --watcher auto
```

这页不展开长教程；首次成功路径仍然看 [first-success-path.md](first-success-path.md)。

## 为什么这页存在

- `README` 负责首页叙事和快速入口
- [runtime-backflow-validation.md](runtime-backflow-validation.md) 负责能力回流历史和总账本
- 这页只负责把“当前最新真实 baseline”压成一眼能看懂的清晰快照
