---
name: devflow-plan-internal
description: Internal DevFlow planner. Use only when the DevFlow orchestrator needs a plan or plan revision for a tracked task. Do not use as a direct user-facing skill.
---

# DevFlow Internal Planner

This skill is only for DevFlow-internal orchestration.

## Responsibilities

- Produce the full `plan.md` body for a new task or an updated version for an existing task.
- Keep the plan implementation-oriented and decision-complete.
- Reflect user constraints, repo context, prior approved or draft plan state, and any useful information from `global-summary.md`.
- Run under the fixed task-scoped subagent name `Planner`.

## Output contract

Return plan content only. The orchestrating skill is responsible for:

- writing `plan.md`
- appending `plan-history.md`
- incrementing `plan_version`
- updating `meta.json`
- refreshing `summary.md` so it still matches the task-local summary contract
- refreshing workspace global summary artifacts
- relaying the result to the user

## Hard constraints

- Do not modify code.
- Do not update state files.
- Do not decide whether the plan is approved.
- Do not talk to the user directly; the main DevFlow skill relays your output.
