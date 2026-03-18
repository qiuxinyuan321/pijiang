# Security Policy

## 支持边界

`皮匠` 当前是本地优先的多模型议会能力层。

这意味着：

- provider API key 由用户自己提供和保管
- 运行结果主要落在本地目录与本地可视化层
- relay / command bridge / host integration 都会扩大攻击面

因此安全边界的第一原则是：

不要把“兼容”误读成“零风险”。

## 当前重点风险面

### 1. API Key 与 provider 凭据

- 不要把 API key 提交到仓库
- 不要把 API key 写进 issue、日志或 Obsidian run 产物
- relay / 中转站 场景下，先确认第三方是否可信

### 2. 本地文件读写

`皮匠` 会生成：

- 配置文件
- run 目录
- Obsidian 模板与运行产物

请在你清楚的本地路径下运行，不要把敏感目录误设为 Vault、cache 或 run 输出目录。

### 3. 宿主集成与命令桥接

社区宿主适配、`command_bridge`、外部 wrapper 都可能引入：

- 额外命令执行面
- 参数注入风险
- 凭据泄露风险

如果你开启这些能力，请先确认来源可信，并最小化授权。

### 4. Support Bundle 与日志

调试时请默认把日志视为可能包含：

- 本地路径
- provider model 名称
- 运行参数
- 失败上下文

分享前先做脱敏，不要直接公开未检查的支持包。

## 漏洞报告

如果你发现安全问题：

1. 不要公开贴出可复用的攻击细节、密钥或敏感配置。
2. 优先使用 GitHub 的私密安全报告渠道。
3. 如果仓库当下没有开启私密安全报告，再开 issue 时请只写影响范围与复现摘要，不要贴 secrets。

## 我们当前不承诺的内容

当前仓库还不承诺：

- 企业级 secret management
- 任意 relay 的安全审计
- 所有社区宿主适配器的深度安全验证
- 所有第三方 provider 的统一安全特性

## 用户侧最低建议

- 使用单独的测试 key 或低权限 key
- 先走 [docs/first-success-path.md](docs/first-success-path.md)
- 优先停留在 [docs/support-matrix.md](docs/support-matrix.md) 的 `official` 或 `tested` 路径
- 分享日志或截图前先做脱敏
