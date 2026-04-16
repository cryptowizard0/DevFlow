# DevFlow Repository Guidelines

This file defines repository-specific rules for this project. Unless the user explicitly asks otherwise, future work in this repository should follow these guidelines.

## Project Purpose

This repository is used to build `DevFlow`, a Codex plugin for complex engineering tasks.

DevFlow is intended to run tasks through an explicit lifecycle:

```text
plan -> dev -> review -> done
```

and persist state, planning decisions, development notes, review results, and cross-task knowledge in `DevFlowWorkspace/`.

## Repository Layout

This repository uses the following structure:

```text
.
├── AGENTS.md
├── README.md
├── DevFlowWorkspace/
└── plugins/
    └── devflow/
        ├── .codex-plugin/plugin.json
        ├── assets/
        ├── scripts/
        └── skills/
```

### Important exception

General repository defaults may place repo-local plugins under `.agents/plugins/`, but this repository intentionally follows the official Codex plugin layout:

- plugin source lives in `plugins/devflow/`
- do not move the DevFlow plugin back into `.agents/plugins/devflow/`

This is an established repository convention and should be preserved.

## Source Of Truth

- `DevFlowWorkspace/tasks/TASK-xxx/meta.json` is the single source of truth for task stage state
- `DevFlowWorkspace/active-tasks.json` is the source of truth for unfinished task indexing and focus-task selection
- `DevFlowWorkspace/active-task.json` is a compatibility projection for the current focus task; it is not the primary source of truth
- `DevFlowWorkspace/global-summary.json` is the source of truth for shared cross-task summary data
- `DevFlowWorkspace/tasks/TASK-xxx/summary.md` is the task-local handoff and recovery summary for one task
- markdown files are audit logs, recovery context, stage artifacts, and human-readable views; they do not override state
- plugin behavior and documentation should stay aligned across:
  - `plugins/devflow/.codex-plugin/plugin.json`
  - `plugins/devflow/skills/`
  - `plugins/devflow/scripts/`
  - `README.md`

## DevFlow Workspace Rules

`DevFlowWorkspace/` is a repository asset, not a disposable temp directory. Unless the user explicitly asks for it, do not delete it, reset it, or ignore it.

Each workspace now follows this contract:

```text
DevFlowWorkspace/
├── active-task.json
├── active-tasks.json
├── global-summary.json
├── global-summary.md
└── tasks/
    └── TASK-xxx/
        ├── meta.json
        ├── request.md
        ├── plan.md
        ├── plan-history.md
        ├── dev.md
        ├── change-summary.md
        ├── review.md
        └── summary.md
```

Each task also owns an isolated git worktree, recorded in `meta.json`:

- default root resolution:
  - `DEVFLOW_WORKTREE_ROOT/<repo-name>/<task-id>/` when explicitly set
  - `CODEX_HOME/worktrees/devflow/<repo-name>/<task-id>/` when `CODEX_HOME` is set
  - `~/.codex/worktrees/devflow/<repo-name>/<task-id>/` when `~/.codex` already exists
  - otherwise `~/.local/share/devflow/worktrees/<repo-name>/<task-id>/`
- default branch: `codex/devflow/<task-id>`

### Status machine

Allowed core stage states:

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

- `status` only represents the workflow stage
- `planner_agent_status` and `reviewer_agent_status` only represent runtime/session state
- `current_step` is descriptive free text; it is not a stage enum
- `next_action` controls what may happen next
- `is_blocked` and `block_reason` represent blocking state without changing the stage enum
- `dev` must not run before `approve-plan`
- `review` must not modify code
- `review pass` means the task is ready to complete, not completed
- only explicit `done` finishes a task and removes it from `active-tasks.json`
- when a focused task is completed, the focus should move to another unfinished task if one exists; otherwise it should clear

### Agent naming

- the planning subagent is always named `Planner`
- the review subagent is always named `Reviewer`
- `Planner` is task-scoped and may be reused across plan iterations
- `Reviewer` is created per review round and does not need to be reused

### Cross-task knowledge

- every stage-ending update should refresh both the task `summary.md` and workspace `global-summary.json` / `global-summary.md`
- new planning or development work should read `global-summary.md` first
- `summary.md` under a task directory is local to that task; it is not the shared workspace summary
- shared summary data should emphasize:
  - task overview
  - stage status and next action
  - key data structures / interfaces / file contracts
  - key config / environment requirements
  - pitfalls, bugs, and mistakes to avoid
  - notes that matter to other tasks

## Editing Rules

- When changing plugin behavior, update these together when relevant:
  - `plugins/devflow/scripts/`
  - `plugins/devflow/skills/`
  - `README.md`
  - `AGENTS.md` if repository rules change
- Do not change scripts without updating user-facing documentation, and do not change documentation without updating scripts, unless the user explicitly asks for only one side
- Do not introduce task file names or state names that conflict with the existing protocol
- Do not place runtime logic inside `.codex-plugin/`; that directory is for `plugin.json` only
- `assets/console/` is a static browser UI; keep it zero-dependency and directly runnable when edited

## Scripts

The main scripts currently live in `plugins/devflow/scripts/`.

Important scripts include:

- `init_task.py`
- `check_gate.py`
- `update_meta.py`
- `append_plan_history.py`
- `generate_change_summary.py`
- `generate_summary.py`
- `generate_global_summary.py`
- `render_resume.py`
- `open_console.py`

When modifying these scripts:

- keep the CLI interface as stable as possible
- when adding an action or transition, update both `README.md` and the related skill text
- treat state updates for a single task as serialized operations; avoid concurrent writes to the same `meta.json`
- do not let one task inspect or mutate another task's worktree by accident

## Marketplace / Installation

- plugin source is stored in this repository
- the personal marketplace file lives at `~/.agents/plugins/marketplace.json`
- DevFlow is currently exposed to Codex through that personal marketplace entry

Do not treat the home-directory marketplace file as a repository file or commit target unless the user explicitly asks for it.

## Current Boundary

This repository already implements:

- the plugin manifest
- skill definitions
- the multi-task workspace file protocol
- per-task worktree assignment helpers
- state machine helper scripts
- workspace and global summary generators
- the static console page

This repository does not yet fully implement:

- the main orchestrator that connects `Planner` / `Reviewer` to real `spawn_agent` and `resume_agent` calls
- end-to-end automated execution of the full `plan / dev / review / done` lifecycle inside Codex

Future work should build the orchestrator on top of the existing protocol rather than replacing the current file layout.
