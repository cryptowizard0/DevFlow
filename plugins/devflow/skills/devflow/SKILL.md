---
name: devflow
description: Use when the user wants to manage a complex development task through an explicit plan -> dev -> review workflow with persisted task state and markdown artifacts. This is the only public entrypoint for the DevFlow plugin.
---

# DevFlow

DevFlow is the public entrypoint for a staged development workflow.

## Supported actions

Use explicit action words:

- `start`: create a new tracked task, write `request.md`, set status to `planning`, create the task-scoped `Planner` subagent, and invoke the internal planning skill
- `update-plan`: revise the current plan, append `plan-history.md`, increment `plan_version`, reset approval, and reuse the task-scoped `Planner` when possible
- `approve-plan`: only after the user explicitly approves the plan; move to `plan_approved`
- `dev`: execute the next bounded implementation slice and append to `dev.md`
- `review`: generate `change-summary.md`, invoke the `Reviewer` subagent, write `review.md`, and move back to `developing` with `next_action=dev` or `next_action=done`
- `done`: only after a passing review; write `summary.md`, mark the task complete, and clear `active-task.json`
- `resume`: read `active-task.json` and `meta.json` and return the current state summary

## Workflow rules

- Never skip `plan`.
- Never start `dev` before `approve-plan`.
- Never modify code during plan generation.
- Never modify code during review.
- Never mark review as passed without the internal review skill's verdict.
- Never end a task automatically after review; only the explicit `done` action completes the task.
- Always update `meta.json` and the relevant markdown artifact for each phase.

## Workspace

All runtime files live under `DevFlowWorkspace/` in the target repository:

```text
DevFlowWorkspace/
  active-task.json
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

## Script helpers

Use these deterministic helpers for file and state operations:

- `plugins/devflow/scripts/init_task.py`
- `plugins/devflow/scripts/check_gate.py`
- `plugins/devflow/scripts/update_meta.py`
- `plugins/devflow/scripts/append_plan_history.py`
- `plugins/devflow/scripts/render_resume.py`
- `plugins/devflow/scripts/generate_change_summary.py`
- `plugins/devflow/scripts/generate_summary.py`
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
