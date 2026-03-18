from __future__ import annotations

from pathlib import Path


TEMPLATE_FILES: dict[str, str] = {
    "00-Start-Here.md": """# 皮匠 Obsidian 面板

这个 Vault 是皮匠的官方可视化模板。

- 这里展示的是多模型议会的真实运行结果。
- 不是单模型在扮演多个角色。
- 而是多个真实模型位分别承担不同分析职责，最后做发散、对抗、整合与收敛。

建议先看：

1. `10-Dashboards/当前议题总览.md`
2. `10-Dashboards/10席议会拓扑.md`
3. `10-Dashboards/运行历史.md`
""",
    "10-Dashboards/当前议题总览.md": """# 当前议题总览

这里会按运行目录查看最新一次议会产物：

- `00-brief.md`
- `01-run-overview.md`
- `30-idea-map.md`
- `40-debate-round-1.md`
- `41-debate-round-2.md`
- `50-fusion-decisions.md`
- `90-final-solution-draft.md`
""",
    "10-Dashboards/10席议会拓扑.md": """# 10 席议会拓扑

标准完整议会固定为：

1. 主控
2. 规划者
3. 外部搜索者 1
4. 外部搜索者 2
5. 裨将 1
6. 裨将 2
7. 裨将 3
8. 混沌者
9. 质疑者
10. 融合者

这些都是分析职责，不是角色扮演人格。
""",
    "10-Dashboards/运行历史.md": """# 运行历史

每次运行都会在对应输出根下生成独立 run 目录。

重点看：

- 当前 run 的阶段
- 每席状态
- 失败数
- 已生成产物
""",
    "10-Dashboards/执行进度.md": """# 当前执行进度

等待过程中应关注：

- 当前阶段
- 已完成席位数 / 总席位数
- 外部搜索者进度
- 裨将层进度
- 下一个融合步骤
""",
    "20-Runs/.keep": "",
}


def install_obsidian_template(vault_path: Path) -> list[Path]:
    resolved = vault_path.expanduser().resolve()
    created: list[Path] = []
    for relative, content in TEMPLATE_FILES.items():
        path = resolved / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        created.append(path)
    return created
