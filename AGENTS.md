# DevFlow Repository Guidelines

This file defines repository-specific rules for this project. Unless the user explicitly asks otherwise, future work in this repository should follow these guidelines.

## Project Purpose

This repository is used to build `DevFlow`, a Codex plugin for architecture-first engineering tasks.

DevFlow now operates on two layers:

- project layer: `Architect` maintains the architecture baseline
- task layer: `plan -> dev -> review -> done`

The system is document-first: without an approved architecture baseline there is no task, and without referenced constraint documents there is no development.

## Repository Layout

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

- `DevFlowWorkspace/projects/PROJECT-001/meta.json` is the single source of truth for project architecture state
- `DevFlowWorkspace/tasks/TASK-xxx/meta.json` is the single source of truth for task stage state
- `DevFlowWorkspace/active-project.json` is the active project projection
- `DevFlowWorkspace/active-tasks.json` is the source of truth for unfinished task indexing and focus-task selection
- `DevFlowWorkspace/active-task.json` is a compatibility projection for the current focus task
- `DevFlowWorkspace/global-summary.json` is the source of truth for shared project/task summary data
- `DevFlowWorkspace/projects/PROJECT-001/summary.md` is the project-local handoff and recovery summary
- `DevFlowWorkspace/tasks/TASK-xxx/summary.md` is the task-local handoff and recovery summary
- markdown files are audit logs, recovery context, stage artifacts, and human-readable views; they do not override state
- plugin behavior and documentation should stay aligned across:
  - `plugins/devflow/.codex-plugin/plugin.json`
  - `plugins/devflow/skills/`
  - `plugins/devflow/scripts/`
  - `README.md`

## DevFlow Workspace Rules

`DevFlowWorkspace/` is a repository asset, not a disposable temp directory. Unless the user explicitly asks for it, do not delete it, reset it, or ignore it.

Each workspace follows this contract:

```text
DevFlowWorkspace/
├── active-project.json
├── active-task.json
├── active-tasks.json
├── global-summary.json
├── global-summary.md
├── projects/
│   └── PROJECT-001/
│       ├── meta.json
│       ├── request.md
│       ├── architecture.md
│       ├── module-map.md
│       ├── standards.md
│       ├── roadmap.md
│       ├── constraints.json
│       ├── architecture-history.md
│       ├── summary.md
│       └── adr/
└── tasks/
    └── TASK-xxx/
        ├── meta.json
        ├── request.md
        ├── plan.md
        ├── plan-history.md
        ├── dev.md
        ├── change-summary.md
        ├── review.md
        ├── architecture-change-request.md
        └── summary.md
```

Each task owns an isolated git worktree, recorded in `meta.json`:

- `DEVFLOW_WORKTREE_ROOT/<repo-name>/<task-id>/` when explicitly set
- `CODEX_HOME/worktrees/devflow/<repo-name>/<task-id>/` when `CODEX_HOME` is set
- `~/.codex/worktrees/devflow/<repo-name>/<task-id>/` when `~/.codex` already exists
- otherwise `~/.local/share/devflow/worktrees/<repo-name>/<task-id>/`

Default branch remains `codex/devflow/<task-id>`.

## State Machines

Task stage states:

```text
draft
-> planning
-> plan_approved
-> developing
-> reviewing
-> developing
-> done
```

Project stage states:

```text
architecting
<-> architecture_approved
```

Key rules:

- `status` only represents stage state
- `architect_agent_status`, `planner_agent_status`, and `reviewer_agent_status` only represent runtime/session state
- `current_step` is descriptive free text; it is not a stage enum
- `next_action` controls what may happen next
- `is_blocked` and `block_reason` represent blocking state without changing the stage enum
- `dev` must not run before `approve-plan`
- `start-plan` must not run before `approve-arch`
- `review` must not modify code
- `review pass` means the task is ready to complete, not completed
- only explicit `done` finishes a task and removes it from `active-tasks.json`
- when a focused task is completed, the focus should move to another unfinished task if one exists; otherwise it should clear

## Role Boundaries

- `Architect` is project-scoped. Owns architecture baseline, module split, standards, roadmap, `constraints.json`, ADRs, and approved exceptions.
- `Planner` is task-scoped. Can only plan under an approved architecture baseline.
- `Developer` implements a bounded task slice. Cannot edit project architecture documents or invent new constraints.
- `Reviewer` checks correctness and architecture compliance. Cannot approve architecture deviations.

Hard boundaries:

- `Architect` does not write business code
- `Architect` does not directly approve task completion
- `Planner` does not change project architecture
- `Developer` does not change project architecture documents
- `Reviewer` does not approve architecture exceptions

## Document Constraints

The most important project documents are:

- `architecture.md`: overall system architecture design. It should cover system description, tech stack, overall architecture, runtime flow and data flow, module split, cross-module constraints and relationships, schema / data structures, project directory layout, and key design decisions.
- `module-map.md`: detailed module design, responsibilities, boundaries, dependency direction, and module IDs. This is the key implementation document for individual task delivery and should be implementation-ready. It may remain a top-level index and point to multiple module-specific markdown files when needed.
- `standards.md`: code standards, testing requirements, error handling, logging, and interface contracts.
- `roadmap.md`: complete development plan, including module implementation order and recommended task breakdown.
- `constraints.json`: machine-readable subset of approved architecture constraints used by gate and check logic.
- `adr/`

They are constraint inputs, not optional reference notes.

Planner requirements:

- read `architecture_version`, `module_scope`, `constraint_refs`, related ADRs, and roadmap entries
- `plan.md` must include:
  - `Architecture Context`
  - `Modules In Scope`
  - `Constraints Checklist`
  - `Required Exceptions`
  - `Implementation Order`

Developer requirements:

- only inject architecture fragments relevant to the current `module_scope`
- explicitly declare followed `constraint_refs`, referenced architecture docs, and used exceptions in `dev.md`
- do not advance to review unless the `dev.md` compliance declaration is complete and matches the task architecture binding
- if implementation needs an architecture change, write `architecture-change-request.md` and route through `update-arch`

Reviewer requirements:

- review both correctness and architecture compliance
- produce:
  - `implementation_verdict: pass | changes_requested | blocked`
  - `architecture_verdict: compliant | deviation | needs_architect_decision`
- only `pass + compliant` or `pass + approved_exception` may lead to `done`
- semantic `update-arch` on an approved project must be backed by a concrete task `architecture-change-request.md`
- helper scripts must not use `--set/--clear` to override file-backed architecture, review, or constraint state

## Cross-task knowledge

- every stage-ending update should refresh the relevant `summary.md` and workspace `global-summary.json` / `global-summary.md`
- new architecture, planning, or development work should read `global-summary.md` first
- `projects/PROJECT-001/summary.md` is project-local; it is not the shared workspace summary
- `tasks/TASK-xxx/summary.md` is task-local; it is not the shared workspace summary
- shared summary data should emphasize:
  - active project state and architecture version
  - task overview
  - stage status and next action
  - architecture bindings
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
- Do not introduce file names or state names that conflict with the existing protocol
- Do not place runtime logic inside `.codex-plugin/`; that directory is for `plugin.json` only
- `assets/console/` is a static browser UI; keep it zero-dependency and directly runnable when edited
- `constraints.json` is the only machine-readable source for architecture gating; markdown explains semantics but does not replace it

## Scripts

The main scripts live in `plugins/devflow/scripts/`.

Important scripts include:

- `init_project.py`
- `update_project_meta.py`
- `generate_project_summary.py`
- `append_architecture_history.py`
- `migrate_legacy_workspace.py`
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
- treat state updates for a single project or task as serialized operations
- avoid concurrent writes to the same `meta.json`
- do not let one task inspect or mutate another task's worktree by accident
- do not let task-side roles mutate `projects/PROJECT-001/*`

## Marketplace / Installation

- plugin source is stored in this repository
- the personal marketplace file lives at `~/.agents/plugins/marketplace.json`
- DevFlow is currently exposed to Codex through that personal marketplace entry

Do not treat the home-directory marketplace file as a repository file or commit target unless the user explicitly asks for it.

## Current Boundary

This repository now implements:

- plugin manifest
- skill definitions and role constraints
- project + task workspace file protocol
- per-task worktree assignment helpers
- state machine helper scripts
- project, task, and global summary generators
- architecture drift blocking
- the static console page

This repository still does not ship a standalone orchestrator binary beyond the persisted protocol, skills, and helper scripts in this repo.
