# 皮匠

> 三个臭裨将，顶个诸葛亮。

皮匠是一个面向复杂议题的多模型议会能力层。

它不是让一个模型“扮演多个角色”，而是引入多个真实模型位，分别承担主控、规划、外部搜索、裨将、混沌、质疑、融合等分析职责，最后做：

`发散 -> 对抗 -> 整合 -> 收敛`

对外主命令固定为 `cpj`，安装包名保持 `pijiang`。

## 当前安装方式

当前仓库还处于本地打磨阶段，请区分三种安装方式：

### 1. 从源码目录安装

```powershell
pipx install .
```

或：

```powershell
uv tool install .
```

### 2. 从 wheel 安装

先构建：

```powershell
python -m build
```

再安装：

```powershell
python -m pip install dist\pijiang-0.1.0-py3-none-any.whl
```

### 3. 从 PyPI 安装

下面这个命令是发布后的目标形态，不代表当前仓库此刻已经发布到 PyPI：

```powershell
pipx install pijiang
```

## 新用户推荐路径

不要一上来就直接 `cpj run`。

推荐顺序固定为：

1. `cpj init`
2. `cpj doctor`
3. `cpj demo`
4. 配置真实 providers
5. `cpj run`

这样可以先验证安装、模板、可视化和命令面本身没问题，再接真实 API。

## 快速开始

### 1. 初始化标准配置与 Obsidian 模板

```powershell
cpj init --yes
```

这会生成：

- 一份默认标准配置
- 一份 `demo-config.json`
- 官方 `10` 席议会拓扑
- 官方 Obsidian Vault 模板

### 2. 体检当前配置

```powershell
cpj doctor
```

如果你要拿去做自动化判断：

```powershell
cpj doctor --json
```

`doctor` 会明确告诉你：

- 标准拓扑有多少席
- 当前已启用多少席
- 当前可真实运行多少席
- readiness 是 `ready / warning / blocker`
- 哪些 provider 仍然只是占位模板
- 每个 HTTP provider 当前是走 `relay_url`、结构化 `host/port/path_prefix`，还是 legacy `base_url`

### 3. 先跑零 API 演示

```powershell
cpj demo
```

`cpj demo` 不调用真实外部 API，它会：

- 生成一条完整的示例 run
- 写入 Obsidian 模板目录
- 产出 `01-run-overview.md`
- 产出 `30-idea-map.md`
- 产出 `50-fusion-decisions.md`
- 产出 `90-final-solution-draft.md`

这样你不需要先搞真实密钥，也能看到皮匠到底长什么样。

### 4. 配置真实 provider 后再运行

```powershell
cpj run --brief "examples\briefs\project-parliament.md" --topic "议会项目级能力化"
```

首次真实运行前，`cpj run` 会固定做三件事：

1. 说明工作原理
2. 提醒多模型决策会明显更慢
3. 要求你确认后才真正开始调用

如果 `doctor` 发现 blocker，`cpj run` 会直接拒绝执行，避免你在默认配置下撞到 provider 缺失、环境变量缺失或 command bridge 未配置的问题。

## 第三方中转站与自定义端口

这层能力只是在扩展 HTTP 接入兼容面，不会改变皮匠的议会机制。

- 它支持的是 provider endpoint 的兼容升级
- 不是把多模型议会退化成单模型角色扮演
- `cpj run` 仍然要先通过 readiness gate

你可以在 `cpj init` 生成的 `config.json` 里，直接编辑 provider 的 endpoint 字段。

### 1. 旧写法：直接使用 `base_url`

```json
{
  "id": "controller-primary",
  "adapter_type": "openai_compatible",
  "base_url": "https://api.openai.com/v1"
}
```

### 2. 结构化写法：`host + port + path_prefix`

```json
{
  "id": "controller-primary",
  "adapter_type": "openai_compatible",
  "scheme": "http",
  "host": "127.0.0.1",
  "port": 8000,
  "path_prefix": "/v1"
}
```

### 3. 中转站直连：`relay_url`

```json
{
  "id": "controller-primary",
  "adapter_type": "openai_compatible",
  "relay_url": "https://your-relay.example.com/openai"
}
```

优先级固定为：

1. `relay_url`
2. `host + port + path_prefix`
3. `base_url`

`cpj doctor --json` 会输出每个 HTTP provider 的：

- `endpoint_source`
- `effective_base_url`
- `normalized`

这样你可以直接看出当前到底命中了哪种接入方式，以及路径有没有被标准化。

## 默认议会拓扑

官方标准配置固定为 `10` 席完整议会：

1. `controller`：主控
2. `planning`：规划者
3. `search-1`：外部搜索者 1
4. `search-2`：外部搜索者 2
5. `marshal-1`：裨将 1
6. `marshal-2`：裨将 2
7. `marshal-3`：裨将 3
8. `chaos`：混沌者
9. `skeptic`：质疑者
10. `fusion`：融合者

关键约束：

- 默认标准就是 `10` 席
- 正常模式至少支持 `6` 个以上模型位
- 少于 `10` 席会进入 `reduced_council_mode`
- 少于 `6` 个可真实运行 profile 只能视为 `minimal_mode`

## 官方兼容层

官方首发兼容面：

- `OpenAI-compatible`
- `Ollama`
- `Alibaba Coding Plan`
- `Volcengine Coding Plan`

可选社区适配器：

- `Codex CLI`
- `Claude Code CLI`
- `OpenCode CLI`

其中：

- `controller` 独立于 `planning`
- `coding plan` 是官方一等公民 Planning Provider
- 系统只建议用户给 controller 选强模型，例如 `Opus 4.6`、`GPT-5.4`、`Gemini 3.1 Pro` 或高质量 coding plan，但不强制

## Obsidian 可视化

Obsidian 是首发强推荐默认体验，但不是硬阻断依赖。

启用后会生成一套官方模板，至少包含：

- 当前议题总览
- `10` 席议会拓扑
- 外部搜索位视图
- 裨将层视图
- 混沌者与质疑者视图
- idea map 视图
- fusion decisions 视图
- final draft 视图
- run history
- 当前执行进度

如果不启用 Obsidian，系统仍可运行，但会明确提示这是 `visualization_degraded` 的降级体验。

## 当前命令面

- `cpj init`
- `cpj doctor`
- `cpj demo`
- `cpj integrate <host>`
- `cpj run`

## 开发说明

仓内仍保留 `tools/solution_factory` 作为历史兼容与内部参考，但正式发布包只应围绕 `pijiang/*` 演进。

## License

本项目采用 `MIT` License。
