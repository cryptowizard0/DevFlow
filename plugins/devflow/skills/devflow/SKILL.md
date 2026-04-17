---
name: devflow
description: Use when the user wants to manage a complex development task through an architecture-first workflow with project-scoped architecture documents, task-scoped plans, persisted state, and markdown artifacts. This is the only public entrypoint for the DevFlow plugin.
---

# DevFlow

DevFlow is the public entrypoint for an architecture-first staged development workflow.

## Supported actions

Use explicit action words:

- `start-project`: create `PROJECT-001`, scaffold the architecture document set, set project status to `architecting`, set it as the active project, and invoke the internal `Architect`
- `update-arch`: revise the architecture baseline, append `architecture-history.md`, refresh `constraints.json`, rescan impacted tasks, and refresh project/task/global summaries. On an already approved project, a semantic architecture change must be grounded in a task `architecture-change-request.md`.
- `approve-arch`: only after the user explicitly approves the architecture baseline; move the project to `architecture_approved`
- `start-plan`: create a new tracked task under the approved architecture baseline, bind it to `project_id`, `architecture_version`, `module_scope`, and `constraint_refs`, create the task worktree, set status to `planning`, and invoke the internal `Planner`
- `update-plan`: revise the current task plan, append `plan-history.md`, increment `plan_version`, reset task approval, and refresh summaries
- `approve-plan`: only after the user explicitly approves the task plan; move the task to `plan_approved`
- `dev`: execute the next bounded implementation slice in the target task's own worktree and append to `dev.md`
- `review`: generate `change-summary.md` from the target worktree, invoke the `Reviewer` subagent, write `review.md`, and move back to `developing` with `next_action=dev` or `next_action=done`
- `done`: only after a passing implementation review and compliant architecture verdict; refresh `summary.md`, mark the task complete, and remove it from `active-tasks.json`
- `resume`: read the active project, focus task, and parallel active-task index and return the current state summary

All task actions may target an explicit task. If no task is specified, use the current focus task. When an explicit task is targeted, it becomes the new focus task.

## Workflow rules

- Never skip `start-project` for a new workspace.
- Never create a task plan before `approve-arch`.
- Never start `dev` before `approve-plan`.
- Never treat architecture documents as optional reference material.
- Never modify code during architecture planning, task planning, or review.
- Never modify project architecture documents from `Planner`, `Developer`, or `Reviewer`.
- Never mark review as passed without both an implementation verdict and an architecture verdict.
- Never end a task automatically after review; only the explicit `done` action completes the task.
- Always update `meta.json` and the relevant markdown artifact for each phase.
- `status` only represents stage state. Do not overload it with runtime agent state.
- `architect_agent_status`, `planner_agent_status`, and `reviewer_agent_status` only represent runtime/session state.
- `is_blocked` and `block_reason` only represent blocking state; they do not replace the stage status.

## Workspace

All runtime files live under `DevFlowWorkspace/` in the target repository:

```text
DevFlowWorkspace/
  active-project.json
  active-task.json
  active-tasks.json
  global-summary.json
  global-summary.md
  projects/
    PROJECT-001/
      meta.json
      request.md
      architecture.md
      module-map.md
      standards.md
      roadmap.md
      constraints.json
      architecture-history.md
      summary.md
      adr/
  tasks/
    TASK-xxx/
      meta.json
      request.md
      plan.md
      plan-history.md
      dev.md
      change-summary.md
      review.md
      architecture-change-request.md
      summary.md
```

`active-project.json` is the active project projection for the current workspace.
`active-tasks.json` is the multi-task source of truth for unfinished task indexing and the focus task.
`active-task.json` is only a compatibility projection for the current focus task.

`projects/PROJECT-001/summary.md` is the project-level architecture recovery summary.
`tasks/TASK-xxx/summary.md` is the task-local summary for one task only.
`global-summary.md` and `global-summary.json` are the workspace-level shared summaries across the project and all tasks.

Before planning or development:

- read `projects/PROJECT-001/summary.md`
- read `projects/PROJECT-001/constraints.json`
- read `DevFlowWorkspace/global-summary.md`

## Document contracts

The `Architect` owns and updates only these project-scoped documents:

- `architecture.md`: overall system architecture design. It should cover the system description, tech stack, overall architecture, runtime flow and data flow, module split, cross-module constraints and relationships, schema and data structure design, project directory layout, and key design decisions.
- `module-map.md`: detailed module design, module responsibilities, boundaries, dependency direction, and module IDs. This is the key implementation document for task delivery and should be implementation-ready. It may stay as an index and split into multiple module-specific markdown files when needed.
- `standards.md`: code standards, test requirements, error handling, logging, and interface contracts.
- `roadmap.md`: complete development plan, including module implementation order and recommended task breakdown.
- `constraints.json`: machine-readable subset of approved architecture constraints for gates, checks, and prompt slicing.
- `adr/`: architecture decisions and approved exceptions

Task planning and delivery must treat these as constraints:

- `Planner` must read `architecture_version`, `module_scope`, `constraint_refs`, related ADRs, and roadmap entries
- `plan.md` must contain `Architecture Context`, `Modules In Scope`, `Constraints Checklist`, `Required Exceptions`, and `Implementation Order`
- `Developer` must only receive the sliced architecture fragments relevant to the current `module_scope`
- `Developer` must explicitly declare which `constraint_refs` are being followed in `dev.md`, which architecture docs were referenced, and which exceptions were used
- `review` must not proceed until `dev.md` contains a complete compliance declaration that matches the task binding
- `Reviewer` must return both `implementation_verdict` and `architecture_verdict`

## Script helpers

Use these deterministic helpers for file and state operations:

- `plugins/devflow/scripts/init_project.py`
- `plugins/devflow/scripts/update_project_meta.py`
- `plugins/devflow/scripts/generate_project_summary.py`
- `plugins/devflow/scripts/append_architecture_history.py`
- `plugins/devflow/scripts/migrate_legacy_workspace.py`
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

This console is a bundled static asset, not a first-class plugin app. Use it as a manual companion view when the user wants to inspect one or more `DevFlowWorkspace` directories in the browser.

## Internal delegation

- Architecture planning must be delegated to the internal `devflow-architect-internal` skill through a fixed-name project-scoped subagent called `Architect`.
- `Architect` is project-scoped and should be reused across architecture iterations when the live session is available.
- Planning must be delegated to the internal `devflow-plan-internal` skill through a fixed-name task-scoped subagent called `Planner`.
- `Planner` is task-scoped and should be reused across plan iterations when the live session is available.
- Review must be delegated to the internal `devflow-review-internal` skill through a fixed-name per-run subagent called `Reviewer`.
- Development is executed by the main agent, optionally guided by `devflow-dev-internal`.
- If a required subagent cannot be started or fails, mark the project or task blocked in metadata and stop instead of silently degrading.
- Do not use `update_meta.py` or `update_project_meta.py` to override file-backed architecture, review, or constraint state through `--set/--clear`.
