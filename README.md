# DevFlow

DevFlow is a Codex plugin for complex engineering tasks. It supports both architecture discovery and the explicit `plan -> dev -> review -> done` implementation lifecycle, and persists task state, architecture packages, worktree assignment, summaries, and review output in `DevFlowWorkspace/`.

This repository is intended to be agent-friendly: the public interfaces are the `devflow` and `devflow-architect` skills, and agents should use those entrypoints rather than operating the underlying scripts directly.

## What DevFlow Is For

Use DevFlow when the task is large enough that it benefits from:

- an explicit planning phase before code changes
- tracked development progress across multiple iterations
- an independent review phase before completion
- multiple unfinished tasks progressing in parallel
- resumable task state backed by repository files
- shared cross-task knowledge so new tasks can avoid rediscovering the same structures and bugs

DevFlow persists task lifecycle and collaboration context into:

- `active-task.json`
- `active-tasks.json`
- `global-summary.json`
- `global-summary.md`
- `request.md`
- `plan.md`
- `plan-history.md`
- `dev.md`
- `change-summary.md`
- `review.md`
- `summary.md`
- `meta.json`

Each task also owns an isolated git worktree.
Architecture packages live alongside tasks under `DevFlowWorkspace/architectures/`.

## Public Usage For Agents

### Installation

If `devflow` is not available yet, the agent should install the plugin from the local marketplace entry instead of asking the user to work with implementation files.

The current install model is:

- personal marketplace file: `~/.agents/plugins/marketplace.json`
- plugin source path in that file: `plugins/devflow`

The plugin source stays in this repository, while Codex discovers it through the personal marketplace.

### Public Entry Point

The public entrypoints are:

- `devflow`
- `devflow-architect`

Agents should:

- use `devflow` as the front door
- use explicit workflow actions through `devflow`
- avoid invoking internal skills directly
- avoid telling the user to run helper scripts for normal workflow usage

Internal skills exist only for DevFlow orchestration:

- `devflow-plan-internal`
- `devflow-dev-internal`
- `devflow-review-internal`

### Recommended Usage Pattern

Agents should translate the user request into a DevFlow action and stay inside the workflow until the task is explicitly finished.

The normal lifecycle is:

1. `start`
2. `update-plan` as needed
3. `approve-plan`
4. `dev`
5. `review`
6. `dev` or `done`, depending on the review result

Use `resume` whenever the focus task or the parallel task set needs to be restored from workspace state.

Use `devflow-architect` when the user should first turn a fuzzy request into executable architecture documents before starting one or more implementation tasks.

### Supported User Intents

DevFlow is designed around explicit actions:

- `start`
- `update-plan`
- `approve-plan`
- `dev`
- `review`
- `done`
- `resume`

Architecture work is handled separately through `devflow-architect`, which creates architecture packages under `DevFlowWorkspace/architectures/ARCH-xxx/`.

Every action may target a specific task. If the task is omitted, DevFlow uses the current focus task.

Example user requests an agent should translate into DevFlow usage:

- "Use DevFlow to start a task for this refactor."
- "Use DevFlow Architect to design the system before we implement it."
- "Use DevFlow to update the current plan with these changes."
- "Approve the current DevFlow plan."
- "Use DevFlow to continue development on TASK-014."
- "Use DevFlow to review the current task."
- "Use DevFlow to finish TASK-008."
- "Resume the active DevFlow task."

### What The Agent Should Say

Good public usage stays at the plugin level. Typical phrasing should look like:

- "Use DevFlow to start a tracked task for this feature."
- "Use DevFlow to update the current plan."
- "Use DevFlow to continue the active task."
- "Use DevFlow to review the current implementation."
- "Use DevFlow to complete the task."

Avoid exposing internal file operations or script commands in normal usage guidance.

### Agent Behavior Expectations

When using DevFlow, an agent should:

- start with `devflow`, not with internal helper files
- keep the user in the workflow instead of bypassing it
- require explicit `approve-plan` before `dev`
- require explicit `done` before considering the task complete
- treat `review pass` as "ready to finish", not "already finished"
- use `resume` when task context needs to be restored
- treat `DevFlowWorkspace/` and `meta.json` as implementation details unless the user is asking about internals
- read `global-summary.md` before planning or development work on a new task

## Workflow Model

The DevFlow stage state machine remains:

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

- `status` is stage status only
- `planner_agent_status` and `reviewer_agent_status` are runtime/session state only
- `current_step` is descriptive text, not a stage enum
- `next_action` defines what may happen next
- `is_blocked` / `block_reason` express blocking state without changing the stage enum
- `dev` is not allowed before `approve-plan`
- `review` does not modify code
- `review pass` means the task is ready to complete, not completed
- only explicit `done` removes a task from `active-tasks.json`
- the planning subagent is always named `Planner`
- the review subagent is always named `Reviewer`

## Repository Layout

```text
.
├── AGENTS.md
├── README.md
├── DevFlowWorkspace/
│   ├── active-task.json
│   ├── active-tasks.json
│   ├── global-summary.json
│   ├── global-summary.md
│   ├── architectures/
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
- [plugins/devflow/skills/devflow-architect/SKILL.md](plugins/devflow/skills/devflow-architect/SKILL.md)
  public architecture entrypoint
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

Each architecture directory follows this structure:

```text
DevFlowWorkspace/architectures/ARCH-xxx/
├── meta.json
├── request.md
├── outline.md
├── architecture.md
├── data-structures.md
├── constraints.md
├── development-plan.md
├── summary.md
└── modules/
    └── <module-id>.md
```

Workspace-level files:

- `active-tasks.json` is the source of truth for unfinished task indexing and focus-task selection
- `active-task.json` is a compatibility projection for the focus task
- `global-summary.json` is the structured cross-task summary source
- `global-summary.md` is the human-readable view of the same shared summary
- `meta.json` is the single source of truth for an individual task's stage state
- `summary.md` is the task-local handoff and recovery snapshot for one task only
- `architectures/ARCH-xxx/summary.md` is the architecture-local handoff snapshot for one architecture package
- `global-summary.md` is the cross-task shared summary for the whole workspace
- markdown files are recovery context, stage artifacts, and shareable knowledge

In practice:

- read `tasks/TASK-xxx/summary.md` when you need the latest state and lessons for that specific task
- read `DevFlowWorkspace/global-summary.md` when you need shared context from other tasks

Each task `meta.json` now also records:

- `worktree_path`
- `worktree_branch`
- `worktree_base_ref`
- `global_summary_updated_at`
- `architecture_id`
- `module_id`
- `architecture_path`

Architecture `meta.json` records:

- `architecture_id`
- `title`
- `status`
- `outline_version`
- `module_ids`
- `linked_task_ids`

Each task gets an isolated worktree by default:

- root resolution:
  - `DEVFLOW_WORKTREE_ROOT/<repo-name>/<task-id>/` when explicitly set
  - `CODEX_HOME/worktrees/devflow/<repo-name>/<task-id>/` when `CODEX_HOME` is set
  - `~/.codex/worktrees/devflow/<repo-name>/<task-id>/` when `~/.codex` already exists
  - otherwise `~/.local/share/devflow/worktrees/<repo-name>/<task-id>/`
- branch: `codex/devflow/<task-id>`
- base ref: current branch name when available, otherwise `HEAD`

## Engineering Notes

DevFlow includes helper scripts under `plugins/devflow/scripts/`, but those scripts are implementation details, not the preferred user-facing workflow.

Use the scripts when:

- developing or debugging DevFlow itself
- validating the file protocol
- testing state transitions, worktree generation, and workspace summaries

Do not use the scripts as the primary usage instructions for end users or agents. The intended public paths are still `devflow` and `devflow-architect`.

### Important scripts

- `init_task.py`
- `init_architecture.py`
- `check_gate.py`
- `update_meta.py`
- `update_architecture_meta.py`
- `append_plan_history.py`
- `generate_change_summary.py`
- `generate_summary.py`
- `generate_architecture_summary.py`
- `generate_global_summary.py`
- `render_resume.py`
- `open_console.py`

## Bundled Console

DevFlow ships a zero-dependency static browser console for manual inspection of one or more workspaces.

The console can:

- import a local `DevFlowWorkspace/`
- read `active-tasks.json` and fall back to `active-task.json`
- show the focus task and other parallel active tasks
- display worktree path and branch data per task
- render `global-summary.json` alongside task artifacts

Open it directly from [plugins/devflow/assets/console/index.html](plugins/devflow/assets/console/index.html) or resolve it via `plugins/devflow/scripts/open_console.py`.

## Current Boundary

Already implemented:

- plugin manifest
- skill definitions and role constraints
- multi-task workspace file protocol
- isolated per-task worktree assignment helpers
- state machine helper scripts
- task summary and global summary generators
- static console page

Not fully implemented yet:

- the main orchestrator that wires `Planner` / `Reviewer` to real `spawn_agent` and `resume_agent` calls
- end-to-end automated execution of the full `plan / dev / review / done` lifecycle inside Codex
- runtime management for reusing a live task-scoped `Planner` session across multiple plan iterations

At this stage, the repository is an engineering skeleton and runtime file protocol for DevFlow, not a complete orchestrator.
