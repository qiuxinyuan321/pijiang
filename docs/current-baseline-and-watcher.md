# 当前真实 Baseline 与觉者守护层

这页只说明当前已经验证成功的真实基线，以及 standard11 切换到公开 canonical 之后的当前状态，不承担路线图或历史总账功能。

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
| run id | `sf-20260320-154315-30532` |
| mode | `standard10` |
| requested profile | `standard10` |
| effective profile | `standard10` |
| audit_status | `success` |
| seat_integrity_score | `100` |
| evidence_integrity_score | `100` |
| fusion_integrity_score | `100` |
| watcher_enabled | `true` |

这条 run 的意义不是“所有场景已经彻底稳定”，而是：

- `standard10` 已恢复为真实可跑
- 这轮 baseline 不再是 `reduced6` 的临时降级样本
- `truth audit` 与 `觉者` 守护层都已经进入真实运行链

这也是当前仓库里最后一条已经完整通过 `audit_status = success` 的 baseline 快照。

## standard11 当前状态

`standard11` 已经成为当前公开 canonical/default profile，但它的“最新成功 baseline”还在收敛中。当前已确认的事实是：

| 项目 | 当前值 |
| --- | --- |
| 成功定向会 | `sf-20260320-194846-73268` |
| 定向会角色 | standard11 合同与迁移规则的权威来源 |
| 定向会状态 | `audit_status = success` |
| 最新 public baseline 重跑 | `sf-20260320-211359-7232` |
| 重跑状态 | `audit_status = fail` |
| 已定位原因 | `claude-gpt` 外部 `503`，以及一条已在代码里修掉的 `topology_mismatch` 留痕缺口 |

这意味着：

- `standard11` 的 seat/profile 合同已经冻结并写进仓库
- 当前 latest successful baseline 仍然是 `sf-20260320-154315-30532`
- `sf-20260320-211359-7232` 是真实 regression 输入，不是可以拿来宣传成功的样本

## 你会拿到哪些产物

这条 baseline 当前会产出一整条结构化方案链，而不是只给一句最终答案：

| 工件 | 作用 |
| --- | --- |
| `00-brief.md` | 本轮议题与输入 |
| `30-idea-map.md` | 共识点、冲突点与可组合点 |
| `40-debate-round-1.md` | 第一轮议会对抗 |
| `41-debate-round-2.md` | 第二轮议会对抗 |
| `50-fusion-decisions.md` | 决策账本 |
| `70-run-truth-audit.json` | 本轮 truth audit 裁决 |
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

- `standard10` 已恢复为真实可跑
- `opencode` 已重新接回运行链
- `truth audit` 已接通并真实产出
- `觉者` 已接通并真实留痕
- 这轮结果已经不是 `reduced6` 的临时降级替身
- `standard11` 的 seat/profile 合同已经由成功定向会冻结
- 最新 `standard11` baseline 重跑把 `claude-gpt` 503 和状态留痕缺口压成了正式 regression 输入

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
