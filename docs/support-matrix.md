# Support Matrix

这份文档的目的不是把“兼容”写得更大，而是把“我们真正承诺什么”写得更清楚。

返回总导航见 [index.md](index.md)。

## 支持层级定义

| 层级 | 含义 | 期望 |
| --- | --- | --- |
| `official` | 官方主线，文档、doctor、demo、回归都会围绕它打磨 | 优先保证首次成功路径 |
| `tested` | 有冒烟验证，但不是当前唯一主线 | 可以用，但不承诺所有边角场景 |
| `community` | 社区可用路径，欢迎反馈与 PR | 兼容优先，深度承诺有限 |
| `experimental` | 还在探索，接口与体验可能变化 | 不适合作为稳定基线 |

## 当前官方主线

当前官方主线固定为：

- Windows-first
- `cpj init -> cpj doctor -> cpj demo -> cpj run`
- Obsidian 作为强推荐默认可视化层
- 单一路径发布基线优先

如果某项能力不服务这条主线，它就不会抢 `Phase A+` 优先级。

## Provider Matrix

| 能力面 | 当前层级 | 备注 |
| --- | --- | --- |
| `cpj demo` 内置 demo/mock 路径 | `official` | 零 API 首次价值验证路径 |
| `OpenAI-compatible` | `official` | 当前默认 HTTP 兼容主线 |
| `Alibaba Coding Plan` | `official` | 官方一等公民 planning provider |
| `Volcengine Coding Plan` | `official` | 官方一等公民 planning provider |
| `Ollama` | `tested` | 支持接入，但 schema/质量要看模型能力 |
| 其他 OpenAI-compatible relay | `community` | 通过 `relay_url` / `host+port+path_prefix` 接入 |
| 自定义 `command_bridge` | `experimental` | 更适合调试或特殊桥接，不作为官方主线 |

说明：

- `official` 不等于“唯一能用”，而是“官方当前优先深测与修复的路径”。
- 未来官方祝福 profile 会进一步冻结到 1 到 2 套推荐组合。

## Host Matrix

| 宿主 | 当前层级 | 备注 |
| --- | --- | --- |
| CLI 直跑 `cpj` | `official` | 当前最短、最稳入口 |
| Obsidian 可视化闭环 | `official` | 当前主推产品化展示面 |
| `cpj integrate <host>` 生成的轻量集成产物 | `tested` | 可用，但深度因宿主而异 |
| Codex/OpenClaw/Claude Code/OpenCode 社区适配 | `community` | 重要，但不决定内核协议 |
| 通用 host contract / registry / 能力包市场 | `experimental` | 进入 `Phase C` 再深化 |

## OS Matrix

| 平台 | 当前层级 | 备注 |
| --- | --- | --- |
| Windows | `official` | 主开发与主验收平台 |
| macOS | `community` | 欢迎反馈与贡献 |
| Linux | `community` | 欢迎反馈与贡献 |

## Install Path Matrix

| 安装路径 | 当前层级 | 备注 |
| --- | --- | --- |
| `pipx install .` | `official` | 当前仓库内最稳安装方式 |
| `uv tool install .` | `official` | 当前仓库内最稳安装方式 |
| `python -m pip install dist/*.whl` | `tested` | 适合构建后安装验证 |
| `python -m pip install .` | `tested` | 适合本地源码体验 |
| PyPI 直装 `pipx install pijiang` | `experimental` | 以实际 release 状态为准，未发布前不当作默认路径 |

## 这份矩阵如何使用

如果你是新用户：

1. 先走 `official` 路径。
2. 先跑 `cpj demo`，再接真实 provider。
3. 遇到问题时，先确认自己是否在 `official` 或 `tested` 路径上。

如果你是贡献者：

1. 新增兼容面前，先说明它属于哪一层。
2. 不要把 `community` 或 `experimental` 直接写成“官方支持”。
3. 变更支持边界时，同时更新 README、ROADMAP 和本文件。

## 相关文档

- [first-success-path.md](first-success-path.md)
- [release-policy.md](release-policy.md)
- [ROADMAP.md](ROADMAP.md)
