# 如何正确调用真实议会

这页只解决一个问题：

> 为什么有些对话会把“开会”误解成通用多角色评审，而不是 `皮匠` 的真实议会？

## 先说结论

在 `皮匠` 里，真正的“议会”不是一个抽象比喻，也不是通用 skill 名。

它的真实入口是：

- `python -m tools.solution_factory run`
- `cpj run`

如果别的对话没有命中这两个入口，而是跑了什么 `builder / critic / operator / economist` 一类角色审议，那就不是 `皮匠` 的真实议会。

## 什么叫命中正确

命中正确时，你看到的应该是这套语义：

- `standard11`
- 四个显式 `opencode-*` 裨将
- `fusion`
- `truth audit`
- `baseline admission`
- `觉者`

而不是泛化的：

- `Council Mode`
- `War Room`
- 通用多代理角色评审

## 推荐说法

如果你想让别的对话最稳地调用真实议会，直接这样说：

```text
请在 F:\github\皮匠 仓库里调用真实本地议会，不要使用通用多角色 skill。
入口用 python -m tools.solution_factory run 或 cpj run。
```

如果你还想再加一道保险，可以直接补这一句：

```text
我要的是皮匠的真实 11 席议会，不是 agent-orchestrator 的泛化 council mode。
```

## 最短命令

### 真实本地议会

```powershell
python -m tools.solution_factory run --brief <brief.md> --project-path <topic-path> --lanes standard11 --watcher auto
```

### 公开命令面

```powershell
cpj doctor
cpj run --brief <brief.md> --topic <topic> --watcher auto
```

## 如何判断是不是跑偏了

如果你看到这些现象，基本就是跑偏了：

- 它说“本地没有叫议会的显式工具”
- 它把请求转成某个通用 `council / war room` skill
- 它开始列 `builder / critic / operator / economist` 之类泛化角色
- 它没有提到 `standard11 / opencode-kimi / truth audit / baseline admission`

这时应该明确纠正：

```text
不要调用通用 council mode，请调用皮匠仓库里的真实议会入口。
```

## 这页和其他文档的关系

- [README.md](../README.md) 负责首页叙事
- [runtime-backflow-validation.md](runtime-backflow-validation.md) 负责已验证能力总账
- 这页只负责“如何别跑偏”
