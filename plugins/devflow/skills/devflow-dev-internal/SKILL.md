---
name: devflow-dev-internal
description: Internal DevFlow development guidance. Use only when the DevFlow orchestrator is implementing the next bounded slice of an approved plan. Do not use as a direct user-facing skill.
---

# DevFlow Internal Development

This skill supports the main DevFlow agent during the implementation phase.

## Responsibilities

- Select the next bounded implementation slice from the approved plan.
- Read `global-summary.md` before coding so the task can reuse shared decisions and avoid known pitfalls.
- Implement code changes only inside the current task's assigned worktree.
- Collect concise development notes for `dev.md`.
- Prepare a succinct change summary input for later review.

## Hard constraints

- Only run after `approve-plan`.
- Keep changes scoped to the current slice; do not silently execute the whole plan in one step unless the slice explicitly covers it.
- Do not self-approve the result.
- Do not write directly to another task's worktree.
- Update task logs through the orchestrating skill and helper scripts rather than ad hoc file edits.
