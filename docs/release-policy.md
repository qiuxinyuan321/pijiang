# Release Policy

这份文档描述的是 `皮匠` 该怎样发布，而不是它未来想支持多少渠道。

返回总导航见 [index.md](index.md)。

## 发布原则

- 先稳主路径，再放大发布面。
- 一次只维护一条官方主安装路径。
- release 是放大器，不是修复器。
- 支持边界、README、ROADMAP、support matrix 必须同步。

## 当前策略

在 `Phase A+` 内，发布策略按“最小可验证基线”执行：

- 优先确保 `install -> init -> doctor -> demo -> run` 能稳定走通
- 优先提供可验证的 wheel / sdist 构建产物
- 在官方主路径尚未稳定前，不同时铺太多安装渠道

## 版本语义

当前仓库处于 `0.x` 阶段：

- `0.x.y` 期间允许更快演进
- 但任何会破坏默认路径、配置语义或公开命令面的改动，都必须写清楚
- `cpj init / doctor / demo / run` 这组主命令面的破坏性变化必须进 release note

## 发布前门禁

每次 release 前至少应通过：

1. 仓库测试
2. 打包测试
3. clean-room 安装测试
4. 新手最短旅程验证

最小检查建议包括：

```powershell
pytest -q
python -m build
python -m pip install .
python -m pip install dist\*.whl
cpj init --yes
cpj doctor
cpj demo
```

如果某个 release 连 demo-first 路径都不稳定，就不应放大发布。

## 发布资产

每次正式 release 至少应包含：

- release note
- 版本号
- `wheel`
- `sdist`
- 本轮支持矩阵摘要
- 已知限制 / breaking change 说明

如果当前采用 GitHub Releases 作为官方主路径，则 release 页面就是权威入口。

## Breaking Change 规则

以下变化必须明确标记：

- 公开命令面变化
- 默认配置结构变化
- provider profile 字段变化
- readiness 级别或 gate 语义变化
- support matrix 层级变化

对用户有影响的 breaking change，不应只写在 commit 里，必须进入 release note 和 README/ROADMAP 对应入口。

## 渠道策略

当前建议的渠道优先级：

1. GitHub Release 或等价官方单一路径
2. 仓库内源码 / wheel 安装
3. 其他包管理器渠道

在 `official` 主路径未稳定前，不要把“可尝试的渠道”写成“推荐默认渠道”。

## 升级策略

升级时应至少说明：

- 是否需要重新运行 `cpj init`
- 是否需要迁移配置文件
- 是否有新的 readiness gate
- 是否调整了 support matrix

## 相关文档

- [support-matrix.md](support-matrix.md)
- [first-success-path.md](first-success-path.md)
- [ROADMAP.md](ROADMAP.md)
