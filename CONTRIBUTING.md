# Contributing to 皮匠

感谢你愿意参与 `皮匠`。

这不是一个“单模型多角色扮演”项目，而是一个多模型、多职责的议会能力层。所以贡献时请优先保持三条主线清晰：

- 新用户先看到价值，再接真实 provider
- `controller` 独立于 `planning`
- 结构化产物链比“多说一点话”更重要

## 开始之前

先看这几个入口：

- [README.md](README.md)
- [docs/demo-visuals.md](docs/demo-visuals.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)

如果你是第一次本地跑仓库，推荐顺序是：

1. `cpj init`
2. `cpj doctor`
3. `cpj demo`
4. 再进入真实 provider 配置和 `cpj run`

## 本地开发

推荐 Python 版本：

- `3.11`
- `3.12`

安装开发依赖：

```powershell
python -m pip install -e .[dev]
```

## 提交前最少验证

至少跑这几条：

```powershell
pytest -q
python -m build
python -m pijiang --help
```

如果你改了打包、入口或命令面，再额外确认：

```powershell
cpj --help
```

## 适合贡献的方向

- provider 兼容层
- readiness / doctor 可解释性
- `cpj demo` 体验
- Obsidian 可视化
- 文档、图解、安装链路
- 宿主集成能力

## 提 issue 之前

请优先说明这些信息：

- 你运行的是哪条命令
- 你期望看到什么
- 实际发生了什么
- 你是否已经运行过 `cpj doctor`
- 你是否在用真实 provider、relay，还是 `demo`

## 提 PR 时请保持

- 改动范围尽量单一
- 文案不要把核心机制写成“单模型角色扮演”
- 如果改了用户路径，README 或 docs 至少同步一处
- 如果改了行为，测试要覆盖

## 当前默认判断标准

一个改动是否值得进主线，优先看：

- 是否降低新手踩坑率
- 是否提升 demo-first 的价值展示
- 是否让 provider / readiness / 产物链更稳定
- 是否保持向后兼容
