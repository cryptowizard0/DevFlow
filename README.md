# DevFlow

DevFlow is a Codex plugin for architecture-first engineering work. It manages a project-scoped architecture baseline above the existing task-scoped `plan -> dev -> review -> done` lifecycle and persists both layers in `DevFlowWorkspace/`.

This repository is intended to be agent-friendly: the public interface is the `devflow` skill, and agents should use that entrypoint rather than operating helper scripts directly.

## What DevFlow Is For

Use DevFlow when the work benefits from:

- a project-scoped architecture baseline before any task starts
- explicit module boundaries, engineering standards, and implementation order
- tracked task planning, development, and independent review
- multiple unfinished tasks progressing in parallel under one architecture version
- resumable project and task state backed by repository files
- shared summaries so new work can reuse existing architecture and avoid known pitfalls

## Public Actions

The public `devflow` entrypoint supports these actions:

- `start-project`
- `update-arch`
- `approve-arch`
- `start-plan`
- `update-plan`
- `approve-plan`
- `dev`
- `review`
- `done`
- `resume`

Normal flow:

1. `start-project`
2. `update-arch` as needed
3. `approve-arch`
4. `start-plan`
5. `update-plan` as needed
6. `approve-plan`
7. `dev`
8. `review`
9. `dev` or `done`, depending on review output

There is no task without an approved architecture baseline. There is no development without referenced constraints.

## Core Model

DevFlow separates project architecture from task delivery:

- `Architect`: project-scoped role. Owns architecture baseline, module map, standards, roadmap, constraints, and approved exceptions.
- `Planner`: task-scoped role. Can only plan under an approved architecture baseline.
- `Developer`: implements a task slice. Cannot modify architecture documents or invent new rules.
- `Reviewer`: checks correctness and architecture compliance. Cannot approve an architecture deviation.

Task stage state remains:

```text
draft
-> planning
-> plan_approved
-> developing
-> reviewing
-> developing
-> done
```

Project stage state is separate:

```text
architecting
<-> architecture_approved
```

## Workspace Contract

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

Workspace-level source of truth:

- `active-project.json`: active project projection
- `active-tasks.json`: unfinished task index and focus-task selection
- `active-task.json`: compatibility projection for the focus task
- `global-summary.json`: structured workspace summary for the project and all tasks
- `global-summary.md`: human-readable view of the same shared summary

Project source of truth:

- `projects/PROJECT-001/meta.json`: project state and architecture version
- architecture markdown files: approved baseline and audit trail
- `constraints.json`: machine-readable subset of approved architecture constraints used by gate, check, and prompt slicing logic
- `adr/`: architecture decisions and approved exceptions

Task source of truth:

- `tasks/TASK-xxx/meta.json`: task state, architecture binding, and compliance state
- task markdown files: recovery context, stage artifacts, and review output

## Document Contracts

`Architect` owns these project-scoped documents:

- `architecture.md`: overall system architecture design. It should cover the system description, tech stack, overall architecture, runtime flow and data flow, module split, cross-module relationships and constraints, schema and data structure design, project directory layout, and key design decisions.
- `module-map.md`: detailed module design, module responsibilities, boundaries, dependency direction, and module IDs. This is the implementation-critical document for task execution and should be detailed enough to implement directly. It may stay as a top-level index and split detailed module specs into separate markdown files when one file becomes too large.
- `standards.md`: code standards, testing requirements, error handling, logging, and interface contracts.
- `roadmap.md`: complete development plan, including module implementation order and recommended task breakdown.
- `constraints.json`: machine-readable subset of the approved architecture constraints for gates, checks, and prompt injection.
- `adr/`: explicit architecture decisions and approved exceptions

Downstream roles must treat those files as constraints:

- `Planner` reads `architecture_version`, `module_scope`, `constraint_refs`, relevant ADRs, and roadmap entries
- `plan.md` must contain:
  - `Architecture Context`
  - `Modules In Scope`
  - `Constraints Checklist`
  - `Required Exceptions`
  - `Implementation Order`
- `Developer` receives only the sliced architecture fragments relevant to the current `module_scope`
- `Developer` must declare followed `constraint_refs`, referenced architecture docs, and used exceptions in `dev.md`
- `review` only proceeds when `dev.md` contains a complete compliance declaration that matches the task architecture binding
- `Reviewer` must return both:
  - `implementation_verdict: pass | changes_requested | blocked`
  - `architecture_verdict: compliant | deviation | needs_architect_decision`

## Metadata Contracts

Project `meta.json` fields:

- `project_id`
- `title`
- `status`
- `architecture_version`
- `current_step`
- `next_action`
- `approved_at`
- `approved_by`
- `architect_agent_name`
- `architect_agent_id`
- `architect_agent_status`
- `changed_modules`
- `changed_constraint_refs`
- `updated_at`

Task `meta.json` fields extend the existing protocol with:

- `project_id`
- `architecture_version`
- `module_scope`
- `constraint_refs`
- `exception_ids`
- `architecture_compliance_status`

`architecture_compliance_status` is one of:

- `pending`
- `compliant`
- `deviation`
- `needs_architect_decision`
- `approved_exception`

## Enforcement Rules

- `start-project` is only allowed when the workspace does not yet have a project.
- `approve-arch` requires a complete project document set plus a valid `constraints.json`.
- `approve-arch` also requires a concrete `architecture-history.md` entry and at least one concrete ADR file under `adr/`.
- `start-plan` is only allowed when the active project is `architecture_approved`.
- `start-plan` requires a valid `module_scope` and `constraint_refs` that resolve against `constraints.json`.
- `approve-plan` fails if any required plan section is missing or the architecture binding is incomplete.
- `dev` fails if the task has no valid `constraint_refs`, or if architecture drift marked it as needing an architect decision.
- `review` is read-only and must check architecture compliance in addition to correctness.
- `review` fails if `dev.md` does not record a valid compliance declaration or references missing architecture docs.
- `done` only succeeds after `last_review_verdict=pass` and `architecture_compliance_status` is `compliant` or `approved_exception`.
- `update-arch` is the only architecture mutation entrypoint. Architecture change requests, roadmap changes, module boundary changes, and exception approvals all funnel through it.
- semantic `update-arch` on an already approved project must be grounded in a task `architecture-change-request.md`.
- When `update-arch` changes modules or constraints, impacted unfinished tasks are automatically blocked and marked `needs_architect_decision`.
- `update_meta.py` and `update_project_meta.py` do not allow `--set/--clear` to overwrite file-backed stage, constraint, review, or architecture state.

## Worktrees

Each task owns an isolated git worktree:

- `DEVFLOW_WORKTREE_ROOT/<repo-name>/<task-id>/` when explicitly set
- `CODEX_HOME/worktrees/devflow/<repo-name>/<task-id>/` when `CODEX_HOME` is set
- `~/.codex/worktrees/devflow/<repo-name>/<task-id>/` when `~/.codex` already exists
- otherwise `~/.local/share/devflow/worktrees/<repo-name>/<task-id>/`

Branch naming remains `codex/devflow/<task-id>`.

## Script Helpers

Implementation helpers live under `plugins/devflow/scripts/`:

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

These scripts are implementation details for DevFlow itself, not the preferred user-facing workflow.

## Skills

Public entrypoint:

- `devflow`

Internal orchestration skills:

- `devflow-architect-internal`
- `devflow-plan-internal`
- `devflow-dev-internal`
- `devflow-review-internal`

Fixed subagent names:

- `Architect`: project-scoped and reusable across architecture iterations
- `Planner`: task-scoped and reusable across plan iterations
- `Reviewer`: per-review-run

## Console

DevFlow ships a zero-dependency static browser console for manual workspace inspection.

The console can:

- import a local `DevFlowWorkspace/`
- show active project status and architecture version
- show focus task and parallel active tasks
- display task architecture bindings and compliance state
- render `global-summary.json` alongside task artifacts

Open it directly from [plugins/devflow/assets/console/index.html](plugins/devflow/assets/console/index.html) or via `plugins/devflow/scripts/open_console.py`.

## Migration

Legacy workspaces without a project baseline are no longer valid for new task creation or development. Use `plugins/devflow/scripts/migrate_legacy_workspace.py` to scaffold `PROJECT-001`, then complete the architecture baseline and approve it before continuing work.

## Current Boundary

This repository now implements:

- project-scoped architecture file protocol
- task-scoped architecture inheritance fields
- gate checks for architecture-first workflow actions
- project and task summary generation
- architecture drift blocking
- static console updates for project/task state inspection
- skill and manifest contracts for `Architect`, `Planner`, `Developer`, and `Reviewer`

This repository still does not implement a standalone Codex runtime orchestrator beyond the persisted protocol, skills, and helper scripts in this repo. The public workflow remains skill-driven.
