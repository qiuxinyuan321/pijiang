# 皮匠文档导航

如果 README 负责回答“这是什么、为什么值得看、先做什么”，这份文档就负责回答：

> **不同阶段的用户，下一步应该读哪一页。**

## 如果你是第一次来

按这个顺序读最快：

1. [README.md](../README.md)
2. [project-philosophy.md](project-philosophy.md)
3. [first-success-path.md](first-success-path.md)
4. [support-matrix.md](support-matrix.md)
5. [demo-visuals.md](demo-visuals.md)

这条路径适合：

- 还没安装
- 刚下载仓库
- 想先知道 `cpj init -> cpj doctor -> cpj demo -> cpj run` 到底是怎么回事

## 如果你准备真正跑一次

先看这三份：

| 你要解决什么问题 | 先看哪里 |
| --- | --- |
| 我只想按官方最稳路径跑通一次 | [first-success-path.md](first-success-path.md) |
| 我想知道自己现在是不是走在官方支持路径上 | [support-matrix.md](support-matrix.md) |
| 我想知道 release / 安装 / breaking change 的边界 | [release-policy.md](release-policy.md) |

## 如果你想先理解产品形态

这几份更适合建立整体认知：

| 主题 | 文档 | 作用 |
| --- | --- | --- |
| 当前基线与觉者 | [current-baseline-and-watcher.md](current-baseline-and-watcher.md) | 先看当前这轮最新真实 baseline 与守护层能力 |
| 核心理念与演化 | [project-philosophy.md](project-philosophy.md) | 看懂项目为什么存在、为什么会继续进化 |
| AI 代理视角 | [for-ai-agents.md](for-ai-agents.md) | 从 AI 第一人称视角理解这套制度的优点 |
| 首页图解 | [demo-visuals.md](demo-visuals.md) | 看懂 11 席议会、黄金路径、demo 产物链 |
| 运行时回流验证 | [runtime-backflow-validation.md](runtime-backflow-validation.md) | 看清哪些能力已经回流、哪些还没宣称完成 |
| standard11 合同 | [contracts/60-execution-contract.md](contracts/60-execution-contract.md) | 看 seat、profile、legacy 和发布门禁怎么冻结 |
| 路线图 | [ROADMAP.md](ROADMAP.md) | 看当前阶段、Phase A+ / B / C 的边界 |

## 如果你准备贡献

按这个顺序更合适：

1. [CONTRIBUTING.md](../CONTRIBUTING.md)
2. [support-matrix.md](support-matrix.md)
3. [ROADMAP.md](ROADMAP.md)
4. [release-policy.md](release-policy.md)
5. [SECURITY.md](../SECURITY.md)

原因很简单：

- 先知道仓库怎么协作
- 再知道官方支持边界
- 再确认当前主线与不抢优先级的方向

## 文档地图

| 文档 | 解决什么问题 | 适合谁先看 |
| --- | --- | --- |
| [README.md](../README.md) | 项目首页、价值认知、快速入口 | 所有人 |
| [current-baseline-and-watcher.md](current-baseline-and-watcher.md) | 当前最新真实 baseline 与觉者守护层快照 | 想先看本轮可信结论的人 |
| [project-philosophy.md](project-philosophy.md) | 核心理念、起源实验、项目演化样本 | 想先理解项目为什么存在的人 |
| [for-ai-agents.md](for-ai-agents.md) | 从 AI 代理视角看这个项目的优点 | AI 代理、维护者 |
| [first-success-path.md](first-success-path.md) | 新用户第一次怎样最稳地跑通 | 新用户 |
| [support-matrix.md](support-matrix.md) | 当前官方 / tested / community / experimental 边界 | 新用户、贡献者 |
| [demo-visuals.md](demo-visuals.md) | 11 席议会、demo 产物链、图解说明 | 想先理解产品的人 |
| [runtime-backflow-validation.md](runtime-backflow-validation.md) | 已回流能力、benchmark gate、truth audit 状态 | 维护者、进阶用户 |
| [contracts/20-decision-matrix.json](contracts/20-decision-matrix.json) | standard11 机器可读治理真相 | 维护者 |
| [contracts/60-execution-contract.md](contracts/60-execution-contract.md) | standard11 人类可执行门禁与迁移规则 | 维护者 |
| [ROADMAP.md](ROADMAP.md) | 当前主线与阶段目标 | 维护者、贡献者 |
| [release-policy.md](release-policy.md) | 发布基线、门禁和 breaking change 规则 | 维护者、贡献者 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 贡献方式与仓库协作规范 | 贡献者 |
| [SECURITY.md](../SECURITY.md) | 安全边界与披露方式 | 贡献者、使用者 |

## 当前官方阅读主线

如果你只想按“最短不踩坑路径”理解整个项目，推荐固定读这 7 页：

1. [README.md](../README.md)
2. [current-baseline-and-watcher.md](current-baseline-and-watcher.md)
3. [project-philosophy.md](project-philosophy.md)
4. [first-success-path.md](first-success-path.md)
5. [support-matrix.md](support-matrix.md)
6. [runtime-backflow-validation.md](runtime-backflow-validation.md)
7. [ROADMAP.md](ROADMAP.md)

这 5 页分别负责：

- 项目定位
- 当前最新基线快照
- 核心理念与演化方式
- 首次成功路径
- 支持边界
- 已验证能力
- 下一阶段主线

## 当前不建议怎么读

下面这些方式容易把自己读乱：

- 只看 README 就直接 `cpj run`
- 只看图解，不看 `support-matrix`
- 只看路线图，不看 `first-success-path`
- 把 `community` 或 `experimental` 当成 `official`

## 相关入口

- [GitHub Issues](https://github.com/qiuxinyuan321/pijiang/issues)
- [GitHub Pull Requests](https://github.com/qiuxinyuan321/pijiang/pulls)
