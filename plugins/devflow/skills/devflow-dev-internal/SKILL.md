---
name: devflow-dev-internal
description: Internal DevFlow development guidance. Use only when the DevFlow orchestrator is implementing the next bounded slice of an approved plan. Do not use as a direct user-facing skill.
---

# DevFlow Internal Development

This skill supports the DevFlow orchestrator during the implementation phase.

It always runs inside a fresh `Dev` subagent created by `devflow-task`.

## Responsibilities

- Read the task-scoped handoff files under `subagent-runs/DEV-xxx/` instead of relying on orchestrator chat context.
- Select the next bounded implementation slice from the approved plan and the handoff focus.
- Read `global-summary.md` before coding so the task can reuse shared decisions and avoid known pitfalls.
- When the task is bound to `architecture_id + module_id`, read the linked architecture package in this order before coding:
  - `architecture.md`
  - `data-structures.md`
  - `development-plan.md`
  - `constraints.md`
  - `modules/<module-id>.md`
- Implement code changes only inside the current task's assigned worktree.
- Write the primary result markdown to the declared `result.md`.
- Write machine-readable completion data to the declared `result.json`.
- Treat `dev` as the execution plane. Do not absorb orchestrator state-machine decisions into the implementation slice.
- When the repo uses `plugins/devflow/scripts/dev_executor.py`, keep development logging and execution-result shaping aligned with that boundary.

## Hard constraints

- Only run after `approve-plan`.
- Keep changes scoped to the current slice; do not silently execute the whole plan in one step unless the slice explicitly covers it.
- Do not self-approve the result.
- Do not write directly to another task's worktree.
- Do not write `meta.json`, `dev.md`, `review.md`, or other DevFlow state files directly.
- Report completion only through the declared handoff result files.
