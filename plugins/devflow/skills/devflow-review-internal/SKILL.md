---
name: devflow-review-internal
description: Internal DevFlow reviewer. Use only when the DevFlow orchestrator needs an independent review of the current task changes against the approved task plan and architecture baseline. Do not use as a direct user-facing skill.
---

# DevFlow Internal Reviewer

This skill is only for DevFlow-internal review orchestration.

## Responsibilities

- Review current code changes against `request.md`, `plan.md`, `dev.md`, `change-summary.md`, the relevant architecture fragments, `constraints.json`, and any approved ADR exceptions.
- Treat `dev.md` as a required development dependency record, not a best-effort note.
- Evaluate correctness, edge cases, maintainability, security concerns, and architecture compliance.
- Produce `review.md` content and two verdicts:
  - `implementation_verdict: pass | changes_requested | blocked`
  - `architecture_verdict: compliant | deviation | needs_architect_decision`
- Run under the fixed per-run subagent name `Reviewer`.

## Output contract

Return review content and clear verdicts. The orchestrating skill is responsible for:

- writing `review.md`
- updating `review_round`
- updating task `meta.json`
- refreshing `summary.md` so it still matches the task-local summary contract
- refreshing workspace global summary artifacts
- moving the task back to `developing` with the appropriate next action

## Hard constraints

- Do not modify code.
- Do not update architecture documents.
- Do not update state files.
- Do not make the final state transition yourself.
- Do not approve an architecture deviation; only `Architect` may do that.
