# 皮匠仓库级调用约束

当用户在本仓库上下文里说这些话时：

- 开会
- 开个会
- 开会讨论一下
- 调用议会
- 本地议会
- 真实议会
- 议会能力

默认含义固定为：

- 调用 `皮匠` 的真实议会运行器
- 不使用通用 `agent-orchestrator` / `Council Mode` / `War Room` 来冒充
- 不把“多角色评审”当成“真实议会”

## Canonical 入口

优先入口：

1. `python -m tools.solution_factory run`
2. `cpj run`

这两个入口才代表本仓库的真实议会能力。

## 默认执行语义

- 默认 profile：`standard11`
- 四个显式裨将必须存在：
  - `opencode-kimi`
  - `opencode-glm5`
  - `opencode-minimax`
  - `opencode-qwen`
- `觉者` 是 guardian layer，不是投票席位
- 如果用户要求“真实议会”，优先跑真实 run，而不是只做纸面 brainstorm

## 禁止误路由

除非用户明确说“不要跑真实议会，只做快速角色评审”，否则：

- 不要把请求路由到通用多代理 skill
- 不要用 builder / critic / economist 一类泛化角色组代替皮匠议会
- 不要把单模型角色扮演说成“议会”

## 如果真实议会暂时跑不起来

先做这三件事，再决定是否退化：

1. 检查 `cpj doctor`
2. 检查 `tools.solution_factory` / `cpj run` 的 provider 链路
3. 明确告诉用户当前阻塞点

只有在用户明确接受时，才允许退化成非真实议会的快速审议模式，而且必须直说：

- “下面不是皮匠真实议会，只是临时快速评审”

## 产物与快照

若运行真实议会，优先引用这些工件：

- `70-run-truth-audit.json`
- `75-baseline-admission.md`
- `06-juezhe-watch.md`
- `50-fusion-decisions.md`
- `90-final-solution-draft.md`
