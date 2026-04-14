# DevFlow Repository Guidelines

This file defines repository-specific rules for this project. Unless the user explicitly asks otherwise, future work in this repository should follow these guidelines.

## Project Purpose

This repository is used to build `DevFlow`, a Codex plugin for complex engineering tasks.

DevFlow is intended to run tasks through an explicit lifecycle:

```text
plan -> dev -> review -> done
```

and persist state, planning decisions, development notes, and review results in `DevFlowWorkspace/`.

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

- `DevFlowWorkspace/tasks/TASK-xxx/meta.json` is the single source of truth for task state
- the Markdown files are audit logs, recovery context, and stage artifacts; they do not override state
- plugin behavior and documentation should stay aligned across:
  - `plugins/devflow/.codex-plugin/plugin.json`
  - `plugins/devflow/skills/`
  - `plugins/devflow/scripts/`
  - `README.md`

## DevFlow Workspace Rules

`DevFlowWorkspace/` is a repository asset, not a disposable temp directory. Unless the user explicitly asks for it, do not delete it, reset it, or ignore it.

Each task directory should follow this file contract:

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

### Status machine

Allowed core states:

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

- `dev` must not run before `approve-plan`
- `review` must not modify code
- `review pass` means the task is ready to complete, not completed
- only explicit `done` finishes the task and clears `active-task.json`

### Agent naming

- the planning subagent is always named `Planner`
- the review subagent is always named `Reviewer`
- `Planner` is task-scoped and may be reused across plan iterations
- `Reviewer` is created per review round and does not need to be reused

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
- `render_resume.py`
- `open_console.py`

When modifying these scripts:

- keep the CLI interface as stable as possible
- when adding an action or transition, update both `README.md` and the related skill text
- treat state updates for a single task as serialized operations; avoid concurrent writes to the same `meta.json`

## Marketplace / Installation

- plugin source is stored in this repository
- the personal marketplace file lives at `~/.agents/plugins/marketplace.json`
- DevFlow is currently exposed to Codex through that personal marketplace entry

Do not treat the home-directory marketplace file as a repository file or commit target unless the user explicitly asks for it.

## Current Boundary

This repository already implements:

- the plugin manifest
- skill definitions
- the workspace file protocol
- state machine helper scripts
- the static console page

This repository does not yet fully implement:

- the main orchestrator that connects `Planner` / `Reviewer` to real `spawn_agent` and `resume_agent` calls
- end-to-end automated execution of the full `plan / dev / review / done` lifecycle inside Codex

Future work should build the orchestrator on top of the existing protocol rather than replacing the current file layout.
