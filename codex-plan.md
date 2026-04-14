# DevFlow V1 插件实施计划（按官方 Plugin 文档修正）

## Summary

- DevFlow 做成 **个人可安装插件**，但源码保存在当前仓库 `plugins/devflow/` 下，便于版本管理。
- 个人安装入口使用 `~/.agents/plugins/marketplace.json`；其 `source.path` 指向 `./work/src/DevFlow/plugins/devflow`。这是符合官方文档的，因为 personal marketplace 的路径相对 `~` 解析，且插件路径只要求在该 root 内、用 `./` 前缀。
- `DevFlowWorkspace/` 继续放在目标仓库根目录并提交到 Git，作为任务沉淀区；它不是插件源码的一部分。
- V1 仍采用 **Skill 插件 + helper scripts**，不做 MCP/App 集成；主入口 `devflow`，内部拆 `devflow-plan-internal`、`devflow-dev-internal`、`devflow-review-internal`。
- 约束保持不变：单 active task、用户显式 approve plan、review 显式触发、plan/review 强依赖 subagent。

## Plugin Structure

- 插件源码目录改为：
  - `plugins/devflow/.codex-plugin/plugin.json`
  - `plugins/devflow/skills/devflow/`
  - `plugins/devflow/skills/devflow-plan-internal/`
  - `plugins/devflow/skills/devflow-dev-internal/`
  - `plugins/devflow/skills/devflow-review-internal/`
  - `plugins/devflow/scripts/`
  - `plugins/devflow/assets/`（如后续补图标）
- `.codex-plugin/` 中只保留 `plugin.json`，不要把 `skills/`、`scripts/`、`.app.json`、`.mcp.json` 放进去。
- `plugin.json` 首版只声明：
  - `name`
  - `version`
  - `description`
  - `skills: "./skills/"`
  - `interface`
- 不在 V1 声明 `apps`、`mcpServers`，除非后续确实引入 `.app.json` 或 `.mcp.json`。

## Marketplace And Install Model

- 采用 **personal marketplace**：
  - `~/.agents/plugins/marketplace.json`
- 增加 DevFlow entry：
  - `name: "devflow"`
  - `source.source: "local"`
  - `source.path: "./work/src/DevFlow/plugins/devflow"`
  - `policy.installation: "AVAILABLE"`
  - `policy.authentication: "ON_INSTALL"`
  - `category: "Coding"`
- 插件开发源码继续留在仓库；Codex 实际安装后会拷贝到 `~/.codex/plugins/cache/.../local/` 的缓存副本运行。
- 后续如果要团队共享，再补 repo marketplace；V1 不同时维护两套 marketplace。

## Workflow Design

- `devflow` 是唯一对外 skill，负责动作词路由：
  - `start`
  - `update-plan`
  - `approve-plan`
  - `dev`
  - `review`
  - `resume`
- `devflow` 负责：
  - 读取 `DevFlowWorkspace/active-task.json` 和 task `meta.json`
  - 执行 gate
  - 调用 plan/review subagent
  - 统一写入所有 task 文档和 `meta.json`
- `devflow-plan-internal`：
  - 只生成 `plan.md` 内容或更新后的 plan 内容
  - 不改代码，不改 `meta.json`
- `devflow-dev-internal`：
  - 供 main agent 在开发阶段使用
  - 负责执行单个有界实现切片，并产出 `dev.md` 记录素材
- `devflow-review-internal`：
  - 只生成 `review.md` 与 verdict：`pass` / `changes_requested` / `blocked`
  - 不改代码，不改 `meta.json`

## Workspace And State

- 目标仓库根目录创建并跟踪：
  - `DevFlowWorkspace/active-task.json`
  - `DevFlowWorkspace/tasks/TASK-xxx/`
- 每个 task 固定文件：
  - `meta.json`
  - `request.md`
  - `plan.md`
  - `plan-history.md`
  - `dev.md`
  - `change-summary.md`
  - `review.md`
  - `summary.md`
- `meta.json` 作为唯一状态真源，至少包含：
  - `task_id`
  - `title`
  - `status`
  - `created_at`
  - `updated_at`
  - `plan_version`
  - `review_round`
  - `current_step`
  - `last_completed_step`
  - `next_action`
  - `is_blocked`
  - `block_reason`
  - `approved_at`
  - `approved_by`
  - `last_review_verdict`
  - `last_reviewed_at`
- 状态机保持：
  - `draft -> planning -> plan_approved -> developing -> reviewing -> done`
  - `reviewing -> developing` on `changes_requested`

## Helper Scripts

- `plugins/devflow/scripts/init_task.py`
- `plugins/devflow/scripts/check_gate.py`
- `plugins/devflow/scripts/update_meta.py`
- `plugins/devflow/scripts/append_plan_history.py`
- `plugins/devflow/scripts/render_resume.py`
- `plugins/devflow/scripts/generate_change_summary.py`
- 这些脚本只做确定性文件操作与状态校验；阶段性推理仍由 skill / subagent 完成。

## Test Plan

- 结构与安装：
  - `plugins/devflow/.codex-plugin/plugin.json` 可被 marketplace 正确发现
  - `~/.agents/plugins/marketplace.json` 的 `source.path` 能解析到当前仓库源码
- 状态机：
  - 未 approve 时 `dev` 被阻止
  - `update-plan` 会清除批准并退回 `planning`
  - `review(pass)` 进入 `done`
  - `review(changes_requested)` 回退到 `developing`
  - subagent 不可用时进入 blocked
- 端到端：
  - `start -> approve-plan -> dev -> review(pass)`
  - `start -> approve-plan -> dev -> review(changes_requested) -> dev -> review(pass)`
  - `resume` 可从 `active-task.json + meta.json` 恢复

## Assumptions

- 官方 plugin 文档优先于仓库默认布局建议，因此插件源码目录改用 `plugins/devflow/`。
- `scripts/` 作为插件根目录下的普通辅助资源保留；这是基于官方文档“只有 `plugin.json` 属于 `.codex-plugin/`”做出的实现推断。
- V1 只支持个人 marketplace 安装，不同时维护 repo marketplace。
- `DevFlowWorkspace/` 仍属于业务运行态和任务沉淀区，不并入插件目录。
