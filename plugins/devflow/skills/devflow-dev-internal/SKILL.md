---
name: devflow-dev-internal
description: Internal DevFlow development guidance. Use only when the DevFlow orchestrator is implementing the next bounded slice of an approved task plan under an approved architecture baseline. Do not use as a direct user-facing skill.
---

# DevFlow Internal Development

This skill supports the main DevFlow agent during the implementation phase.

## Responsibilities

- Select the next bounded implementation slice from the approved plan.
- Read only the architecture fragments relevant to the current `module_scope` and `constraint_refs`.
- Implement code changes only inside the current task's assigned worktree.
- Record a clear compliance declaration in `dev.md`, including followed `constraint_refs`, referenced architecture docs, and any used exceptions.
- Prepare concise development notes for later review.

## Hard constraints

- Only run after `approve-plan`.
- Keep changes scoped to the current slice; do not silently execute the whole plan in one step unless the slice explicitly covers it.
- Do not self-approve the result.
- Do not write directly to another task's worktree.
- Do not edit `projects/PROJECT-001/*` architecture documents.
- If implementation requires an architecture change, roadmap change, or new exception, write `architecture-change-request.md` and hand control back to `update-arch`.
- Do not leave `dev.md` in placeholder state; review is blocked until the compliance declaration and work log are concrete.
- Update task logs through the orchestrating skill and helper scripts rather than ad hoc file edits.
