---
name: devflow-review-internal
description: Internal DevFlow reviewer. Use only when the DevFlow orchestrator needs an independent review of the current task changes against request, plan, and development log. Do not use as a direct user-facing skill.
---

# DevFlow Internal Reviewer

This skill is only for DevFlow-internal review orchestration.

## Responsibilities

- Review current code changes against `request.md`, `plan.md`, `dev.md`, `change-summary.md`, and any relevant shared notes from `global-summary.md`.
- Evaluate correctness, edge cases, maintainability, and security concerns.
- Produce `review.md` content and one verdict:
  - `pass`
  - `changes_requested`
  - `blocked`
- Run under the fixed per-run subagent name `Reviewer`.

## Output contract

Return review content and a clear verdict. The orchestrating skill is responsible for:

- writing `review.md`
- updating `review_round`
- updating `meta.json`
- refreshing `summary.md` so it still matches the task-local summary contract
- refreshing workspace global summary artifacts
- moving the task back to `developing` with the appropriate next action

## Hard constraints

- Do not modify code.
- Do not update state files.
- Do not make the final state transition yourself.
