# Plan

## Decision

结论：这个工程值得实现真正的 orchestrator，但这个判断应从第一性原理出发，而不是仅因为仓库已经有一套文件协议和脚本。

从第一性原理看，任何想稳定支持 `plan -> dev -> review -> done` 的系统，都需要一个独立的控制面来回答这些问题：

- 现在处于哪个阶段
- 下一步允许做什么
- 谁负责产出哪个工件
- 失败后如何恢复
- 自动循环何时继续、何时停止
- 哪些行为绝对不能跨越边界，例如 planning/review 改代码、未经 review 直接完成任务

这组问题本质上属于 orchestrator，而不属于 `dev` 本身。`dev` 的职责是执行某个已批准切片；orchestrator 的职责是决定何时执行、执行前后如何持久化状态、如何进入 review、如何在失败后恢复。因此，这个工程需要 orchestrator，不是因为现有 repo 缺一段胶水代码，而是因为没有控制面就没有可靠工作流。

同时，需要明确以下架构判断：

- `dev` 不应默认设计成一个长期驻留、专用的 worker agent
- `dev` 与 orchestrator 应在职责上明确分离，前者属于执行面，后者属于控制面
- 这种分离首先是逻辑/架构分离，而不要求 v1 就做成物理上独立的运行时
- v1 完全可以由同一个主 agent 同时承担 orchestrator 决策与 `dev` 执行，但代码结构和状态边界必须清晰分层
- 专用 `dev` worker agent 只应作为后续优化，用于边界清晰、上下文可控的开发切片，而不是默认架构

## Recommendation

建议实现一个最小可行 orchestrator，并以“控制面 / 执行面”分层作为设计前提。

推荐原则：

- orchestrator 负责阶段控制、gate 校验、状态持久化、恢复决策、agent 生命周期协调
- `dev` 负责执行当前批准计划中的一个开发切片，不负责推进整体工作流
- `review` 负责对当前切片做独立判断，不负责写状态机
- v1 可以由同一个主 agent 顺序执行 orchestrator 逻辑和 `dev` 工作，但实现上必须拆出独立模块，不能把编排规则混进 `dev` 实现
- 不要把“是否需要独立 dev agent”作为 v1 的前置条件
- 默认路径应是“main agent 作为 orchestrator + main agent 执行 dev slice + 独立 Planner/Reviewer 子流程”
- 只有当开发切片已经足够 bounded、上下文成本明显受益时，才引入专用 `dev` worker agent

## MVP Scope

第一阶段只做 `devflow-task` orchestrator，避免范围失控。

MVP 必须覆盖：

- `plan` 能真正初始化任务并调用 `Planner` 产出 `plan.md`
- `update-plan` 能复用同一任务上下文重新产出 plan，并维护 `plan-history.md`
- `approve-plan` 只做显式状态批准，不混入 agent 行为
- `dev` 能在任务 worktree 执行一次受控开发切片，并追加 `dev.md`
- `review` 能先生成 `change-summary.md`，再调用 `Reviewer` 产出 `review.md`
- `resume` 能根据 `meta.json` 恢复中断中的计划、评审或 auto-dev
- `auto-dev` 能在 `dev -> review` 闭环里持续推进，直到 `pass` 或 `blocked`

明确延后：

- `devflow-architect` 的 first-class orchestrator
- 多任务并发执行调度器
- 默认的专用长期驻留 `dev` worker agent
- 脱离当前文件协议的全新 runtime
- UI 驱动的复杂交互式控制台逻辑

## Architecture

推荐采用“三层视角、两层落地”的设计。

三层视角：

- 控制面：决定动作是否合法、当前阶段是什么、下一步该做什么、失败后如何恢复
- 执行面：真正执行 `dev` 切片，修改 worktree，产出开发结果
- 评审面：独立生成 plan/review 类判断性工件，不直接操纵状态机

两层落地：

1. 确定性 orchestration kernel

放在 `plugins/devflow/scripts/`，负责状态机、gate、文件产物、恢复判定、下一步决策。这里应尽量纯函数化，复用现有 `devflow_lib.py`、`check_gate.py`、`auto_dev.py`、`generate_*` 系列脚本。

2. runtime coordination layer

负责把 `Planner` / `Reviewer` 接到真实 Codex runtime 的 agent 能力上，并驱动 `dev` 执行。v1 里它可以仍由同一个主 agent 承担，但代码组织上必须把 orchestrator 判断逻辑与 `dev` 执行逻辑分开。

关键判断：

- orchestrator 与 `dev` 的分离首先是逻辑边界，不是进程边界
- v1 不要求把 orchestrator 和 `dev` 运行在不同 agent、不同进程或不同 session
- 只要控制流、状态写入、恢复逻辑、执行逻辑在实现上是清晰分层的，就满足 v1 架构要求
- 如果未来要引入独立 `dev` worker agent，应该是在这个分层上替换执行面实现，而不是重写 orchestrator

建议新增的核心实现文件：

- `plugins/devflow/scripts/orchestrate_task.py`
- `plugins/devflow/scripts/orchestrator_lib.py`
- `plugins/devflow/scripts/agent_runtime.py`
- `plugins/devflow/scripts/dev_executor.py`

其中：

- `orchestrate_task.py` 是动作入口与串联器
- `orchestrator_lib.py` 负责动作前后状态转换、恢复判定、结果归档
- `agent_runtime.py` 定义 `Planner` / `Reviewer` 的 runtime adapter
- `dev_executor.py` 封装 `dev` 执行面，v1 可由主 agent 调用，后续可替换为专用 worker agent 实现

## State Flow

推荐继续以现有 `status` 为唯一阶段状态，不新造第二套 stage enum。

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
  review 返回 `needs_changes`，`next_action=dev`
- `reviewing` -> `developing`
  review 返回 `pass`，`next_action=done`
- `developing` -> `done`
  仅由显式 `done` 触发
- 任意阶段 -> 保持原阶段但 `is_blocked=true`
  用于 agent 启动失败、恢复失败、产物缺失、脚本异常等情况

`execution_mode` 和 `auto_loop_state` 继续只表达编排运行态，不替代 `status`。

## Agent Integration

推荐的 agent 接入方式如下：

- `Planner` 固定为任务级可复用 agent
- `Reviewer` 固定为每轮 review 新建 agent
- `dev` 默认不使用专用长期驻留 agent
- v1 中 `dev` 的默认执行者就是主 agent，但必须通过明确的 execution interface 调用，而不是把开发逻辑直接散落进 orchestrator 分支里
- 专用 `dev` worker agent 仅作为后续可选优化，用于边界清晰、目标单一、上下文可裁剪的开发切片

runtime adapter 最小接口建议：

- `spawn_planner(task_context) -> agent_id`
- `resume_planner(agent_id, task_context) -> result`
- `spawn_reviewer(task_context) -> agent_id`
- `resume_reviewer(agent_id, task_context) -> result`
- `run_dev_slice(task_context) -> execution_result`

其中 `run_dev_slice` 在 v1 可以由主 agent 实现，在后续版本可以替换为独立 worker agent，而无需改动 orchestrator 状态机。

结果要求统一为结构化输出：

- `status`: `completed` / `failed` / `blocked`
- `artifact_body`: plan 或 review 的正文，或 `dev` 的结果摘要
- `error`: 失败原因
- `agent_id`
- `session_resumable`: 是否可恢复

关键原则：

- agent 只负责生成内容或执行切片，不直接改 `meta.json`
- 所有状态写入都由 orchestrator 完成
- planning / review 路径禁止改代码，必须由 orchestrator 在动作边界上保证
- `dev` 即使由主 agent 执行，也必须被当成执行面调用，而不是控制面本身

## Failure Recovery

失败恢复应建立在“先持久化运行意图，再调用外部执行单元”上。

每个外部动作都遵守：

- 调用前先把对应运行状态写入 `meta.json`
- 若拿到 `agent_id`，立即写回 `meta.json`
- 外部执行返回后，先校验产物，再更新阶段状态与 summary
- 若进程中断，`resume` 依据 `agent_id`、agent status、`status`、`next_action`、`auto_loop_state` 判断恢复路径
- 若外部执行已不可恢复，则显式标记 `blocked`，不 silent fallback

这里的“外部执行单元”包括：

- `Planner`
- `Reviewer`
- `dev` 执行面

即使 v1 的 `dev` 执行面仍是主 agent，也应遵守同一恢复契约，避免未来替换执行实现时破坏恢复逻辑。

建议在任务目录新增一个可选审计文件：

- `DevFlowWorkspace/tasks/TASK-xxx/orchestrator-events.jsonl`

用途：

- 记录动作开始、agent 启动、agent 恢复、产物落盘、状态提交、阻塞原因
- 提升恢复与排障能力
- 保持 append-only，不作为状态源，只作为审计日志

## Implementation Path

Phase 1：补 task orchestrator 内核

- 新增 `orchestrate_task.py` 作为统一入口
- 新增 `dev_executor.py`，把 `dev` 执行逻辑从 orchestrator 控制逻辑中分离出来
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
- `dev` 默认仍由主 agent 通过 `dev_executor` 执行
- `review pass` 时写 `next_action=done` 与 `auto_loop_state=awaiting_done`
- `review blocked` 时停止循环并保留恢复上下文
- 确保重启 Codex 后 `resume` 能继续 auto-dev

Phase 4：评估是否引入专用 `dev` worker agent

- 仅在 `dev` 切片可清晰边界化时评估引入
- 优先针对重复性高、上下文可裁剪、失败隔离收益明确的切片
- 通过替换 `dev_executor` 实现验证收益，而不是重写 orchestrator
- 若收益不明显，则保持主 agent 执行 `dev` 作为默认路径

Phase 5：扩展到 `devflow-architect`

- 复用相同的 runtime adapter、恢复逻辑、事件日志模式
- 单独实现 architecture workflow orchestrator
- 不与 task orchestrator 混成一个泛化过度的大控制器

## Acceptance Criteria

- 用户执行 `plan` 后，任务不仅被初始化，还能自动得到完整 `plan.md`
- 用户执行 `review` 后，能自动得到 `change-summary.md` 与 `review.md`
- `resume` 能正确恢复中断中的 plan、review、auto-dev
- `auto-dev` 能在不破坏现有阶段模型的前提下持续推进并安全停止
- `dev` 虽可由主 agent 执行，但在实现结构上已与 orchestrator 控制逻辑清晰分离
- 任何 planning/review 路径都不会修改代码
- 任何阶段失败都能在 `meta.json` 与 summary 中留下明确恢复信息
- README、skills、scripts 三者行为描述保持一致

## Risks And Decisions

需要现在就定下来的实现决策：

- 决定一：真实 orchestrator 先只覆盖 `devflow-task`
- 决定二：状态机继续以现有 `meta.json` 为单一真相，不另起炉灶
- 决定三：orchestrator 与 `dev` 必须做控制面 / 执行面分离
- 决定四：这种分离在 v1 先按逻辑分层实现，不强制物理隔离
- 决定五：v1 默认由主 agent 承担 `dev` 执行，不默认引入专用长期驻留 `dev` agent
- 决定六：专用 `dev` worker agent 仅作为后续优化，通过替换执行面实现接入
- 决定七：agent 调用与状态写入分层，禁止 agent 直接改状态文件
- 决定八：如果真实 runtime adapter 当前不可稳定获得，就先实现带占位 adapter 的 orchestrator 内核，但不要把它伪装成“已闭环”

主要风险：

- 若不显式分离 orchestrator 与 `dev`，v1 很容易演化成“一个大提示词分支”，后续无法替换执行实现
- 若过早引入独立 `dev` worker agent，会把问题从“工作流控制”错误转成“多 agent 调度”，导致范围膨胀
- 若 `dev` 执行结果没有统一结果接口，未来从主 agent 切换到 worker agent 时会重构成本过高

## Suggested First Slice

首个实现切片建议是：

- 新增 `orchestrate_task.py`
- 新增 `dev_executor.py`
- 先完整打通 `plan -> approve-plan -> review -> resume` 的确定性编排框架
- 在 `plan` 和 `review` 上接入 `Planner` / `Reviewer` adapter
- `dev` 暂时仍由主 agent 执行，但必须通过 `dev_executor` 边界接入
- 暂时不引入专用 `dev` worker agent
- 待 plan/review 子流程稳定后，再把 `auto-dev` 接进闭环
- 等 `auto-dev` 稳定后，再基于真实收益评估是否需要独立 `dev` worker agent

这样做的原因是：

- 先把控制面做对，比先把执行面 agent 化更重要
- `plan` 和 `review` 最依赖固定角色 agent，最能体现 orchestrator 的真实价值
- `dev` 的不确定性最高，但它并不要求 v1 默认独立 agent 化
- 通过先抽出 `dev_executor`，可以在不改变默认执行模型的前提下，把控制面 / 执行面边界立住
- 现有仓库的脚本与协议已经足够支撑这个切片，不需要推翻重来
