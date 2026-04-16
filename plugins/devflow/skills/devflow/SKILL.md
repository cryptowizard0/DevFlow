---
name: devflow
description: Use when the user wants to manage a complex development task through an explicit plan -> dev -> review workflow with persisted task state and markdown artifacts. This is the only public entrypoint for the DevFlow plugin.
---

# DevFlow

DevFlow is the public entrypoint for a staged development workflow.

## Supported actions

Use explicit action words:

- `start`: create a new tracked task, write `request.md`, create the task worktree, set status to `planning`, set the new task as the focus task, and invoke the internal planning skill
- `update-plan`: revise the current plan, append `plan-history.md`, increment `plan_version`, reset approval, and refresh both `summary.md` and the workspace global summary
- `approve-plan`: only after the user explicitly approves the plan; move the target task to `plan_approved`
- `dev`: execute the next bounded implementation slice in the target task's own worktree and append to `dev.md`
- `review`: generate `change-summary.md` from the target worktree, invoke the `Reviewer` subagent, write `review.md`, and move back to `developing` with `next_action=dev` or `next_action=done`
- `done`: only after a passing review; refresh `summary.md`, mark the task complete, and remove it from `active-tasks.json`
- `resume`: read the focus task plus the parallel active-task index and return the current state summary

All actions may target an explicit task. If no task is specified, use the current focus task. When an explicit task is targeted, it becomes the new focus task.

## Workflow rules

- Never skip `plan`.
- Never start `dev` before `approve-plan`.
- Never modify code during plan generation.
- Never modify code during review.
- Never mark review as passed without the internal review skill's verdict.
- Never end a task automatically after review; only the explicit `done` action completes the task.
- Always update `meta.json` and the relevant markdown artifact for each phase.
- `status` only represents the stage status. Do not overload it with runtime agent state.
- `planner_agent_status` and `reviewer_agent_status` only represent runtime/session state.
- `is_blocked` and `block_reason` only represent blocking state; they do not replace the stage status.

## Workspace

All runtime files live under `DevFlowWorkspace/` in the target repository:

```text
DevFlowWorkspace/
  active-task.json
  active-tasks.json
  global-summary.json
  global-summary.md
  tasks/
    TASK-xxx/
      meta.json
      request.md
      plan.md
      plan-history.md
      dev.md
      change-summary.md
      review.md
      summary.md
```

`active-tasks.json` is the multi-task source of truth for unfinished tasks and the focus task. `active-task.json` is only a compatibility projection for the current focus task.

`tasks/TASK-xxx/summary.md` is the task-local summary for a single task: use it for task handoff, recovery, and the latest task-specific structures/config/pitfalls.
`global-summary.md` and `global-summary.json` are the workspace-level shared summaries across tasks.

`summary.md` should always capture the latest task-local snapshot with this shape:

- task identity and stage snapshot: `task_id`, `title`, `status`, `next_action`
- blocking state: `is_blocked`, `block_reason`
- worktree assignment: `worktree_path`, `worktree_branch`, `worktree_base_ref`
- a short `Work Overview`
- `Key Structures / Interfaces / File Contracts`
- `Key Config / Environment`
- `Pitfalls / Bugs / Mistakes`
- `Cross-Task Notes`

Use `summary.md` to understand one specific task. Do not treat it as the shared workspace summary.

Each task owns an isolated worktree:

- default root resolution:
  - `DEVFLOW_WORKTREE_ROOT/<repo-name>/<task-id>/` when explicitly set
  - `CODEX_HOME/worktrees/devflow/<repo-name>/<task-id>/` when `CODEX_HOME` is set
  - `~/.codex/worktrees/devflow/<repo-name>/<task-id>/` when `~/.codex` already exists
  - otherwise `~/.local/share/devflow/worktrees/<repo-name>/<task-id>/`
- branch: `codex/devflow/<task-id>`
- base ref: current branch name when available, otherwise `HEAD`

Before planning or development, read `global-summary.md` or `global-summary.json` to reuse prior conclusions, key structures, config notes, and known pitfalls from other tasks.

## Script helpers

Use these deterministic helpers for file and state operations:

- `plugins/devflow/scripts/init_task.py`
- `plugins/devflow/scripts/check_gate.py`
- `plugins/devflow/scripts/update_meta.py`
- `plugins/devflow/scripts/append_plan_history.py`
- `plugins/devflow/scripts/render_resume.py`
- `plugins/devflow/scripts/generate_change_summary.py`
- `plugins/devflow/scripts/generate_summary.py`
- `plugins/devflow/scripts/generate_global_summary.py`
- `plugins/devflow/scripts/open_console.py`

## Bundled console

DevFlow also ships a lightweight static workspace console for manual inspection:

- HTML entry: `plugins/devflow/assets/console/index.html`
- Resolver / launcher: `plugins/devflow/scripts/open_console.py`

This console is a bundled static asset, not a first-class plugin app. Use it as a manual companion view when the user wants to inspect multiple `DevFlowWorkspace` directories in the browser.

## Internal delegation

- Planning must be delegated to the internal `devflow-plan-internal` skill through a fixed-name subagent called `Planner`.
- `Planner` is task-scoped and should be reused across plan iterations when the live session is available.
- Review must be delegated to the internal `devflow-review-internal` skill through a fixed-name subagent called `Reviewer`.
- Development is executed by the main agent, optionally guided by `devflow-dev-internal`.
- If a required subagent cannot be started or fails, mark the task blocked in `meta.json` and stop instead of silently degrading.
