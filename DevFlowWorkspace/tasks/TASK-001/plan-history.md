# Plan History

## Snapshot 2026-04-21T10:10:01+00:00

- Reason: Clarify from first principles that dev should not default to a dedicated agent, while dev and orchestrator must be separated as execution-plane vs control-plane.

```md
# Plan

## Decision

结论：这个工程值得补一个真正的 orchestrator，但第一阶段应收敛为“任务工作流 orchestrator”，而不是一次性实现完整的通用多 agent 平台。

理由：

- 现有仓库已经把文件协议、工作树隔离、gate 校验、summary 生成、auto-dev 持久化这些可恢复的确定性底座搭好了，缺的主要是把这些底座串成闭环的执行控制层。
- `README.md` 和 `AGENTS.md` 已明确把主要缺口定义为“把 `Planner` / `Reviewer` 接到真实 `spawn_agent` / `resume_agent` 上”，说明问题不是协议缺失，而是缺真实编排。
- 现有 `auto_dev.py` 只负责持久化 `execution_mode` / `auto_loop_state`，`render_resume.py` 只负责展示恢复信息；它们都不是闭环 orchestrator，这进一步证明仓库还停留在“半编排”状态。
- `plugin.json` 的对外能力描述已经承诺了 `plan`、`auto-dev`、`review`、`done` 这类行为。如果不补 orchestrator，DevFlow 更像“有协议的提示词包 + 脚手架”，不能稳定兑现产品承诺。
- 当前阶段不值得做“大而全 orchestrator”。最合理的做法是先把 `devflow-task` 跑通，再把同一模式扩展到 `devflow-architect`。

## Recommendation

建议实现一个最小可行 orchestrator，职责边界如下：

- 负责动作分发：`plan`、`update-plan`、`approve-plan`、`dev`、`auto-dev`、`review`、`done`、`resume`
- 负责 gate 校验与状态流转，但不替代现有 `meta.json` 协议
- 负责调用现有确定性脚本完成文件与状态更新
- 负责启动或恢复固定角色 agent：`Planner`、`Reviewer`
- 负责在 `auto-dev` 模式下根据持久化状态决定下一步该跑 `dev` 还是 `review`
- 负责失败后的可恢复性，不负责把失败“自动掩盖”掉
- 不负责重新定义工作区协议
- 不负责把所有业务逻辑塞进 agent prompt
- 不负责第一阶段实现 `devflow-architect` 的完整闭环

## MVP Scope

第一阶段只做 `devflow-task` orchestrator，避免范围失控。

MVP 必须覆盖：

- `plan` 能真正初始化任务并调用 `Planner` 产出 `plan.md`
- `update-plan` 能复用同一任务上下文重新产出 plan，并维护 `plan-history.md`
- `approve-plan` 只做显式状态批准，不混入 agent 行为
- `dev` 能在任务 worktree 执行一次受控开发切片，并追加 `dev.md`
- `review` 能先生成 `change-summary.md`，再调用 `Reviewer` 产出 `review.md`
- `resume` 能根据 `meta.json` 恢复中断中的规划、评审或 auto-dev
- `auto-dev` 能在 `dev -> review` 闭环里持续推进，直到 `pass` 或 `blocked`

明确延后：

- `devflow-architect` 的 first-class orchestrator
- 多任务并发执行调度器
- 脱离当前文件协议的全新 runtime
- UI 驱动的复杂交互式控制台逻辑

## Architecture

推荐采用“两层编排”：

1. 确定性 orchestration kernel

负责状态机、gate、文件产物、恢复判断、下一步决策。实现上应尽量纯函数化，复用现有 `devflow_lib.py`、`check_gate.py`、`auto_dev.py`、`generate_*` 系列脚本。

2. runtime adapter layer

负责把 `Planner` / `Reviewer` 接到真实 Codex runtime 的 agent 能力上。这里不应散落在多个技能文本里，而应抽象成统一接口，避免未来替换 runtime 时重写整个流程。

建议新增的核心实现文件：

- `plugins/devflow/scripts/orchestrate_task.py`
- `plugins/devflow/scripts/orchestrator_lib.py`
- `plugins/devflow/scripts/agent_runtime.py`

其中：

- `orchestrate_task.py` 是动作入口与串联器
- `orchestrator_lib.py` 负责动作前后状态转换、恢复判定、结果归档
- `agent_runtime.py` 定义 `spawn` / `resume` / `collect_result` 抽象，先做最小实现，后续再接真实 runtime

## State Flow

继续以现有 `status` 为唯一阶段状态，不新造第二套 stage enum。

核心流转保持：

- `planning` -> `planning`
  用于 `plan` / `update-plan`，完成后仍停留在规划阶段，`next_action=approve-plan` 或 `update-plan`
- `planning` -> `plan_approved`
  只由显式 `approve-plan` 触发
- `plan_approved` -> `developing`
  `dev` 开始后进入开发阶段
- `developing` -> `reviewing`
  当本轮开发切片完成且 `next_action=review`
- `reviewing` -> `developing`
  review 返回 `changes_requested`，`next_action=dev`
- `reviewing` -> `developing`
  review 返回 `pass`，`next_action=done`
- `developing` -> `done`
  仅由显式 `done` 触发
- 任意阶段 -> 保持原阶段但 `is_blocked=true`
  用于 agent 启动失败、恢复失败、产物缺失、脚本异常等情况

`execution_mode` 和 `auto_loop_state` 继续只表达编排运行态，不替代 `status`。

## Agent Integration

推荐的 agent 接入方式：

- `Planner` 固定为任务级可复用 agent
- `Reviewer` 固定为每轮 review 新建 agent
- `dev` 仍由主 agent 执行，必要时用 `devflow-dev-internal` 作为内部指导，而不是再引入第三类长期存活子 agent

runtime adapter 最小接口建议：

- `spawn_planner(task_context) -> agent_id`
- `resume_planner(agent_id, task_context) -> result`
- `spawn_reviewer(task_context) -> agent_id`
- `resume_reviewer(agent_id, task_context) -> result`

结果要求统一为结构化输出：

- `status`: `completed` / `failed` / `blocked`
- `artifact_body`: plan 或 review 的正文
- `error`: 失败原因
- `agent_id`
- `session_resumable`: 是否可恢复

关键原则：

- agent 只负责生成内容与判断，不直接改 `meta.json`
- 所有状态写入都由 orchestrator 完成
- planning / review 路径禁止改代码，必须由 orchestrator 在动作边界上保证

## Failure Recovery

失败恢复应建立在“先持久化运行意图，再调用外部 agent”上。

每个外部动作都遵守：

- 调用前先记录动作开始事件，并写明 `current_step`
- 若拿到 `agent_id`，立即写回 `meta.json`
- agent 运行中把 `planner_agent_status` 或 `reviewer_agent_status` 维护为活跃状态
- agent 返回后，先校验产物，再更新阶段状态与 summary
- 若进程中断，`resume` 依据 `agent_id`、agent status、`status`、`next_action`、`auto_loop_state` 判断恢复路径
- 若 agent 已不可恢复，则显式标记 `blocked`，不 silent fallback

建议在任务目录新增一个可选审计文件：

- `DevFlowWorkspace/tasks/TASK-xxx/orchestrator-events.jsonl`

用途：

- 记录动作开始、agent 启动、agent 恢复、产物落盘、状态提交、阻塞原因
- 提升恢复与排障能力
- 保持 append-only，不作为状态源，只作为审计日志

## Implementation Path

Phase 1：补 task orchestrator 内核

- 新增 `orchestrate_task.py` 作为统一入口
- 把 `plan`、`update-plan`、`approve-plan`、`review`、`done`、`resume` 统一收口到这个入口
- 复用现有 `check_gate.py`、`update_meta.py`、`generate_summary.py`、`generate_global_summary.py`
- 为 `Planner` / `Reviewer` 接入 runtime adapter 占位实现
- 更新 README、`devflow-task`、`devflow-plan-internal`、`devflow-review-internal`

Phase 2：跑通真实 `Planner` / `Reviewer` 编排

- 接入真实 `spawn_agent` / `resume_agent`
- `plan` 不再依赖人工复制 plan 内容，直接写入 `plan.md`
- `review` 不再只靠人工说明，直接持久化 reviewer 结论
- `resume` 能恢复中断中的 plan/review 子流程

Phase 3：闭环 auto-dev

- 让 `auto-dev` 真正通过 orchestrator 驱动 `dev -> review`
- `review pass` 时写 `next_action=done` 与 `auto_loop_state=awaiting_done`
- `review blocked` 时停止循环并保留恢复上下文
- 确保重启 Codex 后 `resume` 能继续 auto-dev

Phase 4：扩展到 `devflow-architect`

- 复用相同的 runtime adapter、恢复逻辑、事件日志模式
- 单独实现 architecture workflow orchestrator
- 不与 task orchestrator 混成一个泛化过度的大控制器

## Acceptance Criteria

- 用户执行 `plan` 后，任务不仅被初始化，还能自动得到完整 `plan.md`
- 用户执行 `review` 后，能自动得到 `change-summary.md` 与 `review.md`
- `resume` 能正确恢复中断中的 plan、review、auto-dev
- `auto-dev` 能在不破坏现有阶段模型的前提下持续推进并安全停止
- 任何 planning/review 路径都不会修改代码
- 任何阶段失败都能在 `meta.json` 与 summary 中留下明确恢复信息
- README、skills、scripts 三者行为描述保持一致

## Risks And Decisions

需要现在就定下来的实现决策：

- 决定一：真实 orchestrator 先只覆盖 `devflow-task`
- 决定二：状态机继续以现有 `meta.json` 为单一真相，不另起炉灶
- 决定三：agent 调用与状态写入分层，禁止 agent 直接改状态文件
- 决定四：先做可恢复闭环，再做更高级的自动化能力
- 决定五：如果真实 runtime adapter 当前不可稳定获得，就先实现带占位 adapter 的 orchestrator 内核，但不要把它伪装成“已闭环”

## Suggested First Slice

首个实现切片建议是：

- 新增 `orchestrate_task.py`
- 先完整打通 `plan -> approve-plan -> review -> resume` 的确定性编排框架
- 在 `plan` 和 `review` 上接入 `Planner` / `Reviewer` adapter
- 暂时保留 `dev` 为主 agent 手动执行切片
- 待 plan/review 子流程稳定后，再把 `auto-dev` 接进闭环

这样做的原因是：

- `plan` 和 `review` 最依赖固定角色 agent，最能体现 orchestrator 的真实价值
- `dev` 的不确定性最高，留到第二步更稳妥
- 现有仓库的脚本与协议已经足够支撑这个切片，不需要推翻重来
```

