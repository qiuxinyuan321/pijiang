# 皮匠

<p align="center">
  <img src="docs/assets/pijiang-hero.svg" alt="皮匠：多模型、多职责、真实议会工作流" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/qiuxinyuan321/pijiang/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/qiuxinyuan321/pijiang/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB">
  <img alt="v0.3.0" src="https://img.shields.io/badge/version-0.3.0-blue">
  <img alt="Council" src="https://img.shields.io/badge/Council-11%20Seats-8B4A2C">
  <img alt="Demo first" src="https://img.shields.io/badge/Experience-demo--first-C97D42">
  <img alt="Obsidian recommended" src="https://img.shields.io/badge/Obsidian-Recommended-5A4B81">
</p>

> 三个臭裨将，顶个诸葛亮。

**皮匠**把真实多模型议会做成了一个可嵌入现有入口的能力层——不是让一个模型扮演多个角色，而是把多个真实模型组织成可执行的议会工作流：

```
发散 → 对抗 → 整合 → 收敛
```

安装包名 `pijiang`，主命令 `cpj`。当前公开主线为 **11 席公开议会**，另有可选守护层**觉者**（不参与 quorum，不改结论，只守运行稳定性）。

## 导航

| 你最关心什么 | 入口 |
| --- | --- |
| 先跑通一次 | [3 分钟上手](#3-分钟上手) |
| 完整文档导航 | [docs/index.md](docs/index.md) |
| 当前 baseline 与觉者能力 | [docs/current-baseline-and-watcher.md](docs/current-baseline-and-watcher.md) |
| 让别的对话调用真实议会 | [docs/invoke-real-council.md](docs/invoke-real-council.md) |
| standard11 合同与执行门禁 | [docs/contracts/60-execution-contract.md](docs/contracts/60-execution-contract.md) |
| 核心理念与演化 | [docs/project-philosophy.md](docs/project-philosophy.md) |
| 图解与议会结构 | [docs/demo-visuals.md](docs/demo-visuals.md) |
| 首次可信成功路径 | [docs/first-success-path.md](docs/first-success-path.md) |
| 支持边界 | [docs/support-matrix.md](docs/support-matrix.md) |
| 给 AI 代理看 | [docs/for-ai-agents.md](docs/for-ai-agents.md) |
| 参与贡献 | [CONTRIBUTING.md](CONTRIBUTING.md) |

## 核心理念

单次模型输出存在采样性与视角盲区。`皮匠` 不是多摇几次奖，而是把不同模型放进同一个议会制度：彼此对照、互相攻击、互相借鉴，再融合取舍。

**皮匠让你不再只能接受一次黑盒摇奖，而是拥有在多版方案对照中选择更优结果的能力。**

## 它是什么，不是什么

| 皮匠是 | 皮匠不是 |
| --- | --- |
| 面向复杂议题的多模型、多职责议会能力层 | 一个模型切换语气来"扮演 10 个人" |
| 可嵌入现有入口的高阶决策能力 | 强迫用户切换到全新重应用 |
| 结构化方案链，不只是单段回答 | 聊天窗口里吐一段看起来完整的答案 |
| 带 `demo → doctor → truth audit` 的真实工作流 | 带着半残配置直接硬跑的黑盒脚本 |

## 11 席议会总览

| 职责层 | 席位 | 作用 |
| --- | --- | --- |
| 主控 | `controller` | 总体调度、收敛策略、降级决策 |
| 规划 | `planning` | 结构化规划与 variant 补强 |
| 搜索 | `search-1` / `search-2` | 外部资料、案例与实现证据 |
| 四裨将 | `opencode-kimi` / `glm5` / `minimax` / `qwen` | 创意发散、契约治理、产品表达、多轮辩论 |
| 对抗 | `chaos` / `skeptic` | 打破局部最优、红队拆解与失败模式 |
| 融合 | `fusion` | 决策账本、最终合并与终版输出 |

> `觉者` 不是第 11 个投票席位，而是可选守护层——在卡顿、中断、假 running 时代表用户给出修复建议。

<details>
<summary>展开 11 席完整职责说明</summary>

| 席位 | 职责 |
| --- | --- |
| `controller` | 主控，负责总体调度与最终收敛 |
| `planning` | 规划者，优先由 coding plan provider 承担 |
| `search-1` | 外部搜索者，偏产品/网页/资料检索 |
| `search-2` | 外部搜索者，偏 GitHub/案例/实现检索 |
| `opencode-kimi` | 裨将 1，偏创意发散、跨方案组合与新颖性补强 |
| `opencode-glm5` | 裨将 2，偏契约设计、状态治理与日志可追溯 |
| `opencode-minimax` | 裨将 3，偏人读可读性、产品表达与呈现链路 |
| `opencode-qwen` | 裨将 4，偏多轮辩论、冲突收敛与终版成文 |
| `chaos` | 混沌者，负责打破局部最优 |
| `skeptic` | 质疑者，负责红队拆解与失败模式 |
| `fusion` | 融合者，负责最终合并、决策账本与终版输出 |

</details>

## 产物链

`cpj demo` 和 `cpj run` 不只给你一段最终文本，而是一条完整的方案链：

```
brief → 10 路 variants → fusion → idea-map → debate×2 → fusion-decisions → final-draft → Obsidian/CLI 输出
```

- 回看不同席位的思路来源
- 看到对抗和融合过程，而不是"答案突然出现"
- 输出是方案草案，不是一次性聊天记录

## 安装

| 场景 | 命令 |
| --- | --- |
| 从源码安装 | `pipx install .` 或 `uv tool install .` |
| 从 wheel 安装 | `python -m build && pip install dist/pijiang-0.3.0-py3-none-any.whl` |
| PyPI 直装（目标） | `pipx install pijiang` |

> Python 3.11+ · 当前版本 `0.3.0` · 依赖 `rich>=13.0` · PyPI 是否已发布以 release 页面为准

## 3 分钟上手

### 黄金路径

| 步骤 | 命令 | 作用 | 预期输出 |
| --- | --- | --- | --- |
| 1 | `cpj init --yes` | 生成标准配置与 Obsidian 模板 | 11 席拓扑、`demo-config.json` |
| 2 | `cpj doctor` | 体检 readiness | `ready / warning / blocker` |
| 3 | `cpj demo` | 零 API 验证系统价值 | 完整产物链与可视化结构 |
| 4 | `cpj run` | provider 准备好后真实运行 | 多模型议会输出、truth audit |

> **先看到价值，再接真实 provider；先过 doctor，再进 real run。**

### cpj doctor 会告诉你

- 标准/已启用/可运行席位数
- readiness 等级（`ready / warning / blocker`）
- 哪些 provider 仍是占位模板
- 每个 HTTP provider 命中了 `relay_url`、结构化 endpoint 还是 legacy `base_url`

### cpj demo 产物

零 API 调用即可生成完整 11 席产物链：`00-brief.md` → `01-run-overview.md` → `30-idea-map.md` → `40/41-debate.md` → `50-fusion-decisions.md` → `90-final-solution-draft.md`

### cpj run 语义

```powershell
cpj run --brief "examples\briefs\project-parliament.md" --topic "议会项目级能力化"
```

- 默认 `parallel_policy = ghost_isolation`：少数慢席位不再拖死整场
- 达到法定人数即隔离幽灵链路并进入融合
- 关键席位缺失则拒绝 cutover，不制造伪成功
- 首次运行会说明工作原理并要求确认

## 已验证信号

| 信号 | 状态 | 文档 |
| --- | --- | --- |
| `init / doctor / demo / run` 主链路 | ✅ 已固化 | [first-success-path](docs/first-success-path.md) |
| `standard11` seat/profile 合同 | ✅ 已落地 | [execution-contract](docs/contracts/60-execution-contract.md) |
| `single / reduced6 / standard11` benchmark | ✅ 已落地 | [runtime-backflow](docs/runtime-backflow-validation.md) |
| truth audit · regression cases · 幽灵隔离 | ✅ 已回流 | [runtime-backflow](docs/runtime-backflow-validation.md) |
| 觉者守护层 | ✅ 已回流 | [runtime-backflow](docs/runtime-backflow-validation.md) |
| provider preflight 与支持边界 | ✅ 已整理 | [support-matrix](docs/support-matrix.md) |

<details>
<summary>尚未在首页宣称完整生效的能力</summary>

`soft_budget` · `hard_budget` · `circuit_breaker_threshold` · `quality_retry_threshold` · fallback replacement · 本地议会字节级 subprocess streaming

</details>

## 兼容面

**官方首发兼容：** OpenAI-compatible · Ollama · Alibaba Coding Plan · Volcengine Coding Plan

**可选社区适配：** Codex CLI · Claude Code CLI · OpenCode CLI

> `controller` 独立于 `planning`；`coding plan` 是官方一等公民 Planning Provider。详见 [support-matrix](docs/support-matrix.md)。

<details>
<summary>第三方中转站与自定义端口配置</summary>

provider endpoint 支持三种写法，优先级：`relay_url` > `host+port+path_prefix` > `base_url`

```json
// relay_url 直连
{ "relay_url": "https://your-relay.example.com/openai" }

// 结构化
{ "scheme": "http", "host": "127.0.0.1", "port": 8000, "path_prefix": "/v1" }

// legacy
{ "base_url": "https://api.openai.com/v1" }
```

在 `cpj init` 生成的 `config.json` 里编辑 provider endpoint 即可。

</details>

## Obsidian 可视化

Obsidian 不是硬阻断依赖，但它是当前最完整的可视化面板——Mermaid 讲关系流程，Vault 承接产物，demo 让新用户零 API 看到系统价值。

<details>
<summary>展开 Vault 结构</summary>

```text
obsidian-vault/
├─ 00-Start-Here.md
├─ 10-Dashboards/
│  ├─ 当前议题总览.md
│  ├─ 11席议会拓扑.md
│  ├─ 运行历史.md
│  └─ 执行进度.md
└─ 皮匠/
   └─ <topic>/
      └─ 方案工厂/
         └─ <run-id>/
            ├─ 00-brief.md … 20-fusion.md
            ├─ 30-idea-map.md
            ├─ 40/41-debate.md
            ├─ 50-fusion-decisions.md
            ├─ 70-run-truth-audit.json
            ├─ 80-regression-cases-index.md
            ├─ 90-final-solution-draft.md
            └─ 99-index.md
```

</details>

## 进化引擎

皮匠的进化不靠单模型自言自语，而是一整套制度化机制：真实会议 → truth audit → regression cases → next-iteration brief → benchmark → 用升级后的议会继续讨论议会自己。

<details>
<summary>展开项目演化样本</summary>

| 样本 | 阶段 | 说明 |
| --- | --- | --- |
| `皮匠-GitHub-首页美化升级-20260319` | 展示面收敛 | 首页叙事经过真实会议收敛后落地 |
| `iter-20260319-130615` | 自举协议固化 | `meta-brief → truth audit → delta-report → next-iteration-brief` 循环 |
| `sf-20260319-151806-111592` | 自省二次验证 | 升级后的议会讨论议会自身 |
| `sf-20260319-192359-41528` | 并行语义议题化 | "幽灵堵车"正式翻译成并行执行语义 |

</details>

## 路线图

- **Phase A+**（当前）：首次可信成功路径 `init → doctor → demo → run`
- **Phase B**：Obsidian 单宿主闭环
- **Phase C**：通用宿主 contract 与能力化抽象

当前明确不做：多宿主深集成提前、未稳定前铺发布渠道、支持矩阵未冻结前深度 provider 承诺、demo/run 两套契约、退回单模型角色扮演叙事。

## 仓库结构

```
pijiang/          正式发布主包
tests/            CLI、provider、路径与回归测试
docs/             公开文档
examples/
  briefs/         示例 brief（quick-start / tech-architecture / product-strategy）
  configs/        示例配置（minimal-3-seat / local-ollama）
tools/            真实议会入口与本地 baseline runner
```

## 命令面

| 命令 | 作用 |
| --- | --- |
| `cpj --version` | 查看版本 |
| `cpj init` | 初始化配置与模板 |
| `cpj doctor` | 体检 readiness（Rich 彩色输出） |
| `cpj status` | 查看当前配置概览 |
| `cpj demo` | 零 API 演示（实时进度表） |
| `cpj integrate <host>` | 宿主集成 |
| `cpj run` | 真实议会运行（实时进度表） |

> 所有命令支持 `--no-color` 禁用彩色输出（CI 场景），`--json` 输出机器可读格式。

## 文档入口

[文档导航](docs/index.md) · [核心理念](docs/project-philosophy.md) · [路线图](docs/ROADMAP.md) · [支持矩阵](docs/support-matrix.md) · [发布策略](docs/release-policy.md) · [图解](docs/demo-visuals.md) · [首次成功路径](docs/first-success-path.md) · [运行回流验证](docs/runtime-backflow-validation.md) · [贡献指南](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [给 AI 代理](docs/for-ai-agents.md)

## License

[MIT](LICENSE)
