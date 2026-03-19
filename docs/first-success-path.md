# First Success Path

这份文档只回答一个问题：

新用户第一次接触 `皮匠`，怎样走最短路径，且不容易直接撞墙。

返回总导航见 [index.md](index.md)。

## 黄金路径

官方黄金路径固定为：

`install -> cpj init -> cpj doctor -> cpj demo -> 配置真实 providers -> cpj run`

不要跳步骤，尤其不要一上来就直接 `cpj run`。

## Step 1: 安装

当前最稳的仓库内安装方式：

```powershell
pipx install .
```

或：

```powershell
uv tool install .
```

安装后先确认命令可见：

```powershell
cpj --help
```

## Step 2: 初始化

```powershell
cpj init --yes
```

这一阶段的目标不是“立刻跑真实议会”，而是先生成：

- 标准配置骨架
- demo 配置
- Obsidian 模板
- 标准 10 席拓扑

## Step 3: 先做 readiness 检查

```powershell
cpj doctor
```

如果你要把结果给自动化系统消费：

```powershell
cpj doctor --json
```

这里要重点看三件事：

- 当前 readiness 是 `ready`、`warning` 还是 `blocker`
- 当前是“标准 10 席拓扑”，还是“当前实际可运行席位”
- 哪些 provider 还是 `needs_setup`

如果这里还有 `blocker`，不要继续 real run。

## Step 4: 先跑 demo

```powershell
cpj demo
```

demo 的目的不是“玩具演示”，而是先让你看到：

- 10 席议会长什么样
- 产物链长什么样
- Obsidian 视图里能看到什么

demo 跑完后，至少去看：

- `00-Start-Here.md`
- `01-run-overview.md`
- `30-idea-map.md`
- `50-fusion-decisions.md`
- `90-final-solution-draft.md`

## Step 5: 再接真实 provider

当且仅当下面条件基本满足时，再进入真实 run：

- `doctor` 没有 blocker
- 你已经跑过 `demo`
- 你知道当前用的是哪套 provider profile
- 你知道自己是否还在 `official` 或 `tested` 路径上

## Step 6: 第一次真实运行

示例：

```powershell
cpj run --brief "examples\\briefs\\project-parliament.md" --topic "首次真实运行"
```

第一次真实运行前，系统应先：

1. 解释工作原理
2. 提醒多模型决策会比较慢
3. 给出显式确认

如果 `doctor` 仍有 blocker，`cpj run` 应拒绝执行，而不是把错误拖到 provider 调用阶段。

## 失败时怎么处理

如果第一次真实运行失败，不要直接猜。

优先收集这些信息：

- `cpj doctor` 的输出
- 当前 run 目录下的 `status.json`
- 当前 run 目录下的 `events.jsonl`
- 对应 lane 的 stdout/stderr 或 partial artifact
- 当前 provider profile 配置

如果问题涉及支持边界，再回头对照 [support-matrix.md](support-matrix.md)。

## 什么算“首次成功”

至少满足下面这些条件，才算首次可信成功：

- 安装成功
- `cpj init` 成功
- `cpj doctor` 没有 blocker
- `cpj demo` 能产出完整结构化链路
- 第一次 `cpj run` 至少能进入真实运行，而不是直接死在配置缺失
- 失败时能拿到可读、可追溯的工件，而不是静默黑盒

## 相关文档

- [support-matrix.md](support-matrix.md)
- [release-policy.md](release-policy.md)
- [ROADMAP.md](ROADMAP.md)
