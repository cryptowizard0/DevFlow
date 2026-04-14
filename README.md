# DevFlow

DevFlow is a Codex plugin for complex engineering tasks. It runs work through an explicit `plan -> dev -> review -> done` lifecycle and persists state, plans, development notes, and review output in `DevFlowWorkspace/`.

This repository is intended to be agent-friendly: the public interface is the `devflow` skill, and agents should use that entrypoint rather than operating the underlying scripts directly.

## What DevFlow Is For

Use DevFlow when the task is large enough that it benefits from:

- an explicit planning phase before code changes
- tracked development progress across multiple iterations
- an independent review phase before completion
- resumable task state backed by repository files

DevFlow persists the task lifecycle into:

- `request.md`
- `plan.md`
- `plan-history.md`
- `dev.md`
- `change-summary.md`
- `review.md`
- `summary.md`
- `meta.json`

## Public Usage For Agents

### Installation

If the `devflow` plugin is not available yet, the agent should install it from the personal marketplace entry rather than asking the user to run low-level scripts.

The current install model is:

- personal marketplace file: `~/.agents/plugins/marketplace.json`
- plugin source path in that file: `plugins/devflow`

The plugin source stays in this repository, while Codex discovers it through the personal marketplace.

### Public Entry Point

The only public interface is:

- `devflow`

Agents should:

- use `devflow` as the front door
- avoid invoking internal skills directly
- avoid telling the user to run helper scripts for normal workflow usage

Internal skills exist only for DevFlow orchestration:

- `devflow-plan-internal`
- `devflow-dev-internal`
- `devflow-review-internal`

### Supported User Intents

DevFlow is designed around explicit actions:

- `start`
- `update-plan`
- `approve-plan`
- `dev`
- `review`
- `done`
- `resume`

Example user requests an agent should translate into DevFlow usage:

- "Use DevFlow to start a task for this refactor."
- "Use DevFlow to update the current plan with these changes."
- "Approve the current DevFlow plan."
- "Use DevFlow to continue development."
- "Use DevFlow to review the current task."
- "Use DevFlow to finish the task."
- "Resume the active DevFlow task."

### Agent Behavior Expectations

When using DevFlow, an agent should:

- start with `devflow`, not with internal helper files
- keep the user in the workflow instead of bypassing it
- require explicit `approve-plan` before `dev`
- require explicit `done` before considering the task complete
- treat `review pass` as "ready to finish", not "already finished"
- use `resume` when task context needs to be restored

## Workflow Model

The target DevFlow state machine is:

```text
draft
-> planning
-> plan_approved
-> developing
-> reviewing
-> developing
-> done
```

Key rules:

- `dev` is not allowed before `approve-plan`
- `review` does not modify code
- `review pass` means the task is ready to complete, not completed
- only explicit `done` clears `active-task.json` and finishes the task
- the planning subagent is always named `Planner`
- the review subagent is always named `Reviewer`

## Repository Layout

```text
.
├── AGENTS.md
├── README.md
├── DevFlowWorkspace/
│   ├── active-task.json
│   └── tasks/
└── plugins/
    └── devflow/
        ├── .codex-plugin/plugin.json
        ├── assets/console/
        ├── scripts/
        └── skills/
```

### Important Paths

- [plugins/devflow/.codex-plugin/plugin.json](plugins/devflow/.codex-plugin/plugin.json)
  plugin manifest
- [plugins/devflow/skills/devflow/SKILL.md](plugins/devflow/skills/devflow/SKILL.md)
  public DevFlow entrypoint
- [plugins/devflow/skills/devflow-plan-internal/SKILL.md](plugins/devflow/skills/devflow-plan-internal/SKILL.md)
  internal Planner skill
- [plugins/devflow/skills/devflow-review-internal/SKILL.md](plugins/devflow/skills/devflow-review-internal/SKILL.md)
  internal Reviewer skill
- [plugins/devflow/assets/console/index.html](plugins/devflow/assets/console/index.html)
  static workspace console

## Workspace Contract

Each task directory follows this structure:

```text
DevFlowWorkspace/tasks/TASK-xxx/
├── meta.json
├── request.md
├── plan.md
├── plan-history.md
├── dev.md
├── change-summary.md
├── review.md
└── summary.md
```

- `meta.json` is the single source of truth for task state
- the Markdown files are recovery context and stage artifacts

## Engineering Notes

DevFlow includes helper scripts under `plugins/devflow/scripts/`, but those scripts are implementation details, not the preferred user-facing workflow.

Use the scripts when:

- developing or debugging DevFlow itself
- validating the file protocol
- testing state transitions and workspace generation

Do not use the scripts as the primary usage instructions for end users or agents. The intended public path is still `devflow`.

## Current Boundary

Already implemented:

- plugin manifest
- skill definitions and role constraints
- workspace file protocol
- state machine helper scripts
- static console page

Not fully implemented yet:

- the main orchestrator that wires `Planner` / `Reviewer` to real `spawn_agent` and `resume_agent` calls
- end-to-end automated execution of the full `plan / dev / review / done` lifecycle inside Codex
- runtime management for reusing a live task-scoped `Planner` session across multiple plan iterations

At this stage, the repository is an engineering skeleton and runtime file protocol for DevFlow, not a complete orchestrator.
