# 皮匠路线图

本文档只写主线，不写愿望清单。

返回总导航见 [index.md](index.md)。

## 当前阶段

当前仓库处于 `v0.x`，优先级是：

- 让新用户能顺利完成 `init -> doctor -> demo -> run`
- 让开源首页、安装链路和 Obsidian 模板能快速展示价值
- 让 provider 兼容面在不破坏旧配置的前提下持续扩展

## Phase A+ 当前焦点

`Phase A+` 不是替代 `Phase A`，而是对当前主线的收敛闸门。

只有下面这些事项基本收敛后，才允许继续放大发布面、宿主面和能力抽象：

- 官方祝福 profile 与单一 canonical config
- `cpj doctor` 从播报器升级为修复导向入口
- `cpj run` 前的 provider preflight
- 可信 demo fixture、golden outputs、replay 或 trace
- repo-facts pack 与 repo-grounded lint
- Run Manifest、状态目录、结构化日志、partial artifact、support bundle
- run 后 truth audit、regression cases、benchmark gate
- 支持矩阵、smoke matrix、triage 边界
- 单一路径发布基线

这部分与 [docs/first-success-path.md](first-success-path.md)、[docs/support-matrix.md](support-matrix.md)、[docs/release-policy.md](release-policy.md) 必须口径一致。

## Phase A: 开源首发稳固化

目标：把“能跑”收敛成“别人下载下来就不容易踩坑”。

- 稳定 `cpj init`
- 稳定 `cpj doctor`
- 稳定 `cpj demo`
- 巩固 readiness gate
- 巩固 HTTP endpoint 兼容层
- 增加基础 CI
- 收敛 README、安装说明与示例路径

验收标准：

- 陌生用户能先看到 demo 成果
- 默认配置不会直接把用户带进 provider 报错
- `doctor` 能解释标准拓扑与实际可运行拓扑的区别
- 首次可信成功路径有明确的 support matrix 与 release policy
- demo 与真实 run 共用同一套输入/输出/产物契约

## Phase B: 宿主与可视化增强

目标：让皮匠更像“能力层”，而不是孤立命令。

- 强化 `cpj integrate <host>`
- 深挖 Obsidian 单宿主闭环
- 增强 Codex/OpenClaw/Claude Code/OpenCode 侧集成产物
- 补强 Obsidian 面板与 run history
- 提升阶段进度、席位进度和产物增长的可见性
- 增加更多真实 provider 冒烟验证

验收标准：

- 用户不必切换主入口，也能调用皮匠能力
- 长耗时运行时不再是黑盒等待
- run 结果可复盘、可导航、可对比

## Phase C: 项目级议会系统

目标：把“多模型议会”推向更完整的项目工作流能力。

- 更强的决策账本
- 更强的模板系统
- 更强的历史 run 对照与蒸馏
- 面向长期任务的议会演化机制
- 更清晰的 host capability contract

验收标准：

- 议会不仅能给答案，还能给出结构化、可复盘、可持续演进的方案链
- 运行结果可以沉淀为长期资产，而不是一次性聊天输出

## 暂不进入的方向

这些方向不是否定，只是当前不抢优先级：

- 重桌面应用优先化
- 任意自定义鉴权头模板
- 超大而全的 provider 品牌适配表
- 把所有宿主私有协议直接写死进内核

## 设计原则

- 先把主路径打磨稳，再加功能
- 向后兼容优先，不轻易打碎已有配置
- 对实现者可以麻烦一点，对用户必须尽量简单
- 不是单模型扮演角色，而是多模型、多职责的思路整合
- Phase A+ 先收敛“首次可信成功路径”，再放大分发与宿主覆盖
