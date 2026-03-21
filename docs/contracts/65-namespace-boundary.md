# Namespace Boundary

这页只冻结一件事：`seat / phase / guardian` 三类名字不能再互相借壳。

## 固定边界

- `fusion` 只表示 seat。
- `final-synthesis` 只表示 phase。
- `watcher / 觉者` 只表示 guardian layer。

## 明确禁止

- 不允许把 `fusion` 继续当作“会后阶段”的模糊统称。
- 不允许把 `final-synthesis` 反向写成 seat 名。
- 不允许把 `watcher` 放进投票席位、seat roster、quorum 或 benchmark 主 seat 统计。

## 审计要求

- `run_manifest.json` 必须显式写出 guardian layer 与 namespace boundary。
- `topology report` 必须能证明四裨将、`fusion` seat 与 `watcher` guardian 没有混名。
- Baseline Admission Gate 会把命名边界当成 authority 前置条件，而不是文档建议。
