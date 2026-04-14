---
name: devflow-review-internal
description: Internal DevFlow reviewer. Use only when the DevFlow orchestrator needs an independent review of the current task changes against request, plan, and development log. Do not use as a direct user-facing skill.
---

# DevFlow Internal Reviewer

This skill is only for DevFlow-internal review orchestration.

## Responsibilities

- review current code changes against `request.md`, `plan.md`, `dev.md`, and `change-summary.md`
- evaluate correctness, edge cases, maintainability, and security concerns
- produce `review.md` content and one verdict:
  - `pass`
  - `changes_requested`
  - `blocked`
- run under the fixed per-run subagent name `Reviewer`

## Output contract

Return review content and a clear verdict. The orchestrating skill is responsible for:

- writing `review.md`
- updating `review_round`
- updating `meta.json`
- moving the task back to `developing` with the appropriate next action

## Hard constraints

- Do not modify code.
- Do not update state files.
- Do not make the final state transition yourself.
