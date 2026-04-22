#!/usr/bin/env python3
"""Deterministic helpers for task-level DevFlow orchestration."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    ensure_workspace,
    evaluate_gate,
    load_meta,
    normalize_task_architecture_binding,
    normalize_task_meta_runtime,
    now_iso,
    repo_root_for_workspace,
    subagent_runs_dir,
    resolve_task_id,
    sync_workspace_state,
    write_global_summary,
    write_json,
    write_task_summary,
    write_text,
)
from update_meta import apply_transition


EVENT_LOG_FILENAME = "orchestrator-events.jsonl"
ROLE_PREFIX = {
    "plan": "PLAN",
    "dev": "DEV",
    "review": "REVIEW",
}
ROLE_AGENT_NAME = {
    "plan": "Planner",
    "dev": "Dev",
    "review": "Reviewer",
}


@dataclass
class TaskContext:
    workspace: Path
    task_id: str
    task_dir: Path
    meta_path: Path
    meta: dict[str, Any]
    repo_root: Path
    worktree_path: Path | None

    def minimal_runtime_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workspace": str(self.workspace),
            "task_dir": str(self.task_dir),
            "repo_root": str(self.repo_root),
            "worktree_path": str(self.worktree_path) if self.worktree_path else None,
        }


@dataclass
class SubagentRunSpec:
    role: str
    run_id: str
    agent_name: str
    run_dir: Path
    request_path: Path
    context_path: Path
    result_md_path: Path
    result_json_path: Path

    def to_meta_fields(self, agent_id: str | None = None, status: str = "pending") -> dict[str, Any]:
        return {
            "active_subagent_role": self.role,
            "active_subagent_run_id": self.run_id,
            "active_subagent_name": self.agent_name,
            "active_subagent_id": agent_id,
            "active_subagent_status": status,
            "active_subagent_request_path": str(self.request_path),
            "active_subagent_result_path": str(self.result_json_path),
        }


def helper_script_path(script_name: str) -> Path:
    return SCRIPT_DIR / script_name


def run_helper(script_name: str, *args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        [sys.executable, str(helper_script_path(script_name)), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")
    return completed.stdout.strip()


def create_task_via_helper(
    workspace: Path,
    title: str,
    request_text: str,
    architecture_id: str | None = None,
    module_id: str | None = None,
) -> dict[str, Any]:
    args = [
        "--workspace",
        str(workspace),
        "--title",
        title,
        "--request",
        request_text,
    ]
    if architecture_id:
        args.extend(["--architecture-id", architecture_id])
    if module_id:
        args.extend(["--module-id", module_id])
    output = run_helper("init_task.py", *args, cwd=repo_root_for_workspace(workspace))
    return json.loads(output)


def load_task_context(workspace: Path, task_id: str | None = None) -> TaskContext:
    workspace = Path(workspace).resolve()
    ensure_workspace(workspace)
    resolved_task_id = resolve_task_id(workspace, task_id)
    if not resolved_task_id:
        raise FileNotFoundError("No target task found.")
    meta_path, meta = load_meta(workspace, resolved_task_id)
    normalize_task_meta_runtime(meta)
    worktree_path = None
    if meta.get("worktree_path"):
        candidate = Path(str(meta["worktree_path"])).expanduser().resolve()
        worktree_path = candidate if candidate.exists() else candidate
    return TaskContext(
        workspace=workspace,
        task_id=resolved_task_id,
        task_dir=meta_path.parent,
        meta_path=meta_path,
        meta=meta,
        repo_root=repo_root_for_workspace(workspace),
        worktree_path=worktree_path,
    )


def refresh_context(context: TaskContext) -> TaskContext:
    return load_task_context(context.workspace, context.task_id)


def append_task_event(task_dir: Path, event_type: str, payload: dict[str, Any] | None = None) -> Path:
    event_path = task_dir / EVENT_LOG_FILENAME
    event = {
        "timestamp": now_iso(),
        "event": event_type,
        "payload": payload or {},
    }
    with event_path.open("a", encoding="utf-8") as handle:
        json.dump(event, handle, ensure_ascii=False)
        handle.write("\n")
    return event_path


def update_task_state(
    context: TaskContext,
    transition: str | None = None,
    set_fields: dict[str, Any] | None = None,
    clear_fields: list[str] | None = None,
) -> TaskContext:
    meta = dict(context.meta)
    normalize_task_meta_runtime(meta)
    if transition:
        apply_transition(meta, transition)
    for key, value in (set_fields or {}).items():
        meta[key] = value
    for key in clear_fields or []:
        meta[key] = None

    normalize_task_architecture_binding(context.workspace, meta)
    meta["updated_at"] = now_iso()
    write_json(context.meta_path, meta)
    preferred_focus_task_id = None if meta.get("status") == "done" else context.task_id
    sync_workspace_state(context.workspace, preferred_focus_task_id=preferred_focus_task_id)
    write_task_summary(context.task_dir)
    write_global_summary(context.workspace, touched_task_id=context.task_id)
    return refresh_context(context)


def write_markdown_artifact(task_dir: Path, filename: str, content: str) -> Path:
    output_path = task_dir / filename
    write_text(output_path, content.rstrip() + "\n")
    return output_path


def load_artifact_text(body: str | None = None, artifact_file: str | None = None) -> str | None:
    if artifact_file:
        return Path(artifact_file).expanduser().resolve().read_text(encoding="utf-8").strip()
    if body is not None:
        return body.strip()
    return None


def append_plan_history(task_dir: Path, reason: str) -> Path:
    run_helper("append_plan_history.py", "--task-dir", str(task_dir), "--reason", reason, cwd=task_dir)
    return task_dir / "plan-history.md"


def generate_change_summary(task_dir: Path, repo_root: Path | None = None) -> Path:
    args = ["--task-dir", str(task_dir)]
    if repo_root:
        args.extend(["--repo-root", str(repo_root)])
    run_helper("generate_change_summary.py", *args, cwd=task_dir)
    return task_dir / "change-summary.md"


def require_action_allowed(context: TaskContext, action: str) -> dict[str, Any]:
    gate = evaluate_gate(action, context.meta, context.task_id)
    if not gate.allowed:
        raise RuntimeError(gate.reason)
    return gate.to_dict()


def mark_task_blocked(context: TaskContext, reason: str, current_step: str | None = None) -> TaskContext:
    set_fields: dict[str, Any] = {
        "is_blocked": True,
        "block_reason": reason,
    }
    if current_step:
        set_fields["current_step"] = current_step
    if context.meta.get("execution_mode") == "auto_dev":
        set_fields["auto_loop_state"] = "blocked"
    return update_task_state(context, set_fields=set_fields)


def clear_active_subagent_fields(role: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    return {
        "active_subagent_role": None,
        "active_subagent_run_id": None,
        "active_subagent_name": None,
        "active_subagent_id": None,
        "active_subagent_status": None,
        "active_subagent_request_path": None,
        "active_subagent_result_path": None,
        "last_subagent_role": role,
        "last_subagent_run_id": run_id,
    }


def list_architecture_input_files(context: TaskContext) -> list[Path]:
    architecture_path = context.meta.get("architecture_path")
    architecture_id = context.meta.get("architecture_id")
    if not architecture_path or not architecture_id:
        return []
    architecture_dir = Path(str(architecture_path)).expanduser().resolve()
    files = [
        architecture_dir / "architecture.md",
        architecture_dir / "data-structures.md",
        architecture_dir / "development-plan.md",
        architecture_dir / "constraints.md",
    ]
    module_id = context.meta.get("module_id")
    if module_id:
        files.append(architecture_dir / "modules" / f"{module_id}.md")
    return [path for path in files if path.exists()]


def role_input_files(context: TaskContext, role: str) -> list[Path]:
    task_files: list[Path] = [context.task_dir / "request.md", context.task_dir / "summary.md", context.workspace / "global-summary.md"]
    if role == "plan":
        task_files.extend(
            [
                context.task_dir / "plan.md",
                context.task_dir / "plan-history.md",
            ]
        )
    elif role == "dev":
        task_files.extend(
            [
                context.task_dir / "plan.md",
                context.task_dir / "review.md",
                context.task_dir / "change-summary.md",
            ]
        )
    elif role == "review":
        task_files.extend(
            [
                context.task_dir / "plan.md",
                context.task_dir / "dev.md",
                context.task_dir / "change-summary.md",
                context.task_dir / "review.md",
            ]
        )
    task_files.extend(list_architecture_input_files(context))
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in task_files:
        resolved = path.expanduser().resolve()
        if not resolved.exists() or resolved in seen:
            continue
        ordered.append(resolved)
        seen.add(resolved)
    return ordered


def next_subagent_run_id(task_dir: Path, role: str) -> str:
    prefix = f"{ROLE_PREFIX[role]}-"
    highest = 0
    runs_root = subagent_runs_dir(task_dir)
    runs_root.mkdir(parents=True, exist_ok=True)
    for child in runs_root.iterdir():
        if not child.is_dir() or not child.name.startswith(prefix):
            continue
        suffix = child.name[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1:03d}"


def create_run_spec(task_dir: Path, role: str, run_id: str | None = None) -> SubagentRunSpec:
    resolved_run_id = run_id or next_subagent_run_id(task_dir, role)
    run_dir = subagent_runs_dir(task_dir) / resolved_run_id
    return SubagentRunSpec(
        role=role,
        run_id=resolved_run_id,
        agent_name=ROLE_AGENT_NAME[role],
        run_dir=run_dir,
        request_path=run_dir / "request.json",
        context_path=run_dir / "context.md",
        result_md_path=run_dir / "result.md",
        result_json_path=run_dir / "result.json",
    )


def active_run_spec(context: TaskContext) -> SubagentRunSpec | None:
    role = context.meta.get("active_subagent_role")
    run_id = context.meta.get("active_subagent_run_id")
    if not role or not run_id:
        return None
    return create_run_spec(context.task_dir, str(role), str(run_id))


def render_handoff_context(
    context: TaskContext,
    role: str,
    run_id: str,
    input_files: list[Path],
    focus: str | None = None,
) -> str:
    lines = [
        "# DevFlow Subagent Handoff",
        "",
        f"- Role: `{role}`",
        f"- Run ID: `{run_id}`",
        f"- Task ID: `{context.task_id}`",
        f"- Task Title: {context.meta.get('title') or 'n/a'}",
        f"- Stage Status: `{context.meta.get('status') or 'n/a'}`",
        f"- Next Action: `{context.meta.get('next_action') or 'n/a'}`",
        f"- Execution Mode: `{context.meta.get('execution_mode') or 'manual'}`",
        f"- Auto Loop State: `{context.meta.get('auto_loop_state') or 'n/a'}`",
        f"- Allowed Worktree Path: `{str(context.worktree_path) if context.worktree_path else 'n/a'}`",
        "",
    ]
    if focus:
        lines.extend(["## Requested Focus", "", focus.strip(), ""])

    if role == "plan":
        lines.extend(
            [
                "## Role Contract",
                "",
                "- Produce the next complete `plan.md` body only through the declared result files.",
                "- Do not modify code, task state, or workspace summary files.",
                "- Read the listed input files instead of relying on prior chat context.",
                "",
            ]
        )
    elif role == "dev":
        lines.extend(
            [
                "## Role Contract",
                "",
                "- Implement the next bounded development slice only inside the allowed worktree.",
                "- Read only the listed input files plus repo files inside the task worktree as needed.",
                "- Do not mutate DevFlow state files directly. Report results through the declared result files.",
                "",
            ]
        )
    elif role == "review":
        lines.extend(
            [
                "## Role Contract",
                "",
                "- Review the current task changes against the listed inputs.",
                "- Do not modify code or task state files.",
                "- Write review markdown plus a verdict through the declared result files.",
                "",
            ]
        )

    lines.extend(
        [
            "## Input Files",
            "",
            *[f"- `{path}`" for path in input_files],
            "",
            "## Output Contract",
            "",
            "- Write the primary markdown output to `result.md`.",
            "- Write machine-readable completion data to `result.json`.",
            "- Do not write plan/review/task-state artifacts directly; the orchestrator will finalize those.",
            "",
        ]
    )
    return "\n".join(lines)


def build_request_payload(
    context: TaskContext,
    role: str,
    run_id: str,
    input_files: list[Path],
    output_files: list[Path],
) -> dict[str, Any]:
    return {
        "task_id": context.task_id,
        "role": role,
        "run_id": run_id,
        "status": context.meta.get("status"),
        "next_action": context.meta.get("next_action"),
        "execution_mode": context.meta.get("execution_mode"),
        "auto_loop_state": context.meta.get("auto_loop_state"),
        "worktree_path": str(context.worktree_path) if context.worktree_path else None,
        "worktree_branch": context.meta.get("worktree_branch"),
        "worktree_base_ref": context.meta.get("worktree_base_ref"),
        "architecture_id": context.meta.get("architecture_id"),
        "module_id": context.meta.get("module_id"),
        "architecture_path": context.meta.get("architecture_path"),
        "input_files": [str(path) for path in input_files],
        "output_files": [str(path) for path in output_files],
    }


def initialize_result_payload(spec: SubagentRunSpec) -> dict[str, Any]:
    return {
        "role": spec.role,
        "run_id": spec.run_id,
        "status": "pending",
        "artifact_path": str(spec.result_md_path),
        "summary": None,
        "error": None,
        "verdict": None,
        "files_touched": [],
        "commands": [],
    }


def create_subagent_run(
    context: TaskContext,
    role: str,
    focus: str | None = None,
) -> SubagentRunSpec:
    spec = create_run_spec(context.task_dir, role)
    spec.run_dir.mkdir(parents=True, exist_ok=True)
    input_files = role_input_files(context, role)
    context_text = render_handoff_context(context, role, spec.run_id, input_files, focus=focus)
    request_payload = build_request_payload(
        context,
        role,
        spec.run_id,
        input_files=input_files,
        output_files=[spec.result_md_path, spec.result_json_path],
    )
    write_json(spec.request_path, request_payload)
    write_text(spec.context_path, context_text.rstrip() + "\n")
    write_text(spec.result_md_path, "")
    write_json(spec.result_json_path, initialize_result_payload(spec))
    return spec


def overwrite_result_payload(
    spec: SubagentRunSpec,
    *,
    status: str,
    summary: str | None,
    error: str | None = None,
    verdict: str | None = None,
    files_touched: list[str] | None = None,
    commands: list[str] | None = None,
    body: str | None = None,
) -> None:
    if body is not None:
        write_text(spec.result_md_path, body.rstrip() + "\n")
    payload = initialize_result_payload(spec)
    payload.update(
        {
            "status": status,
            "summary": summary,
            "error": error,
            "verdict": verdict,
            "files_touched": files_touched or [],
            "commands": commands or [],
        }
    )
    write_json(spec.result_json_path, payload)
