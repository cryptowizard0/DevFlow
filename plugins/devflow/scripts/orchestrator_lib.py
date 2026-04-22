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
    now_iso,
    read_text,
    repo_root_for_workspace,
    resolve_task_id,
    sync_workspace_state,
    write_global_summary,
    write_json,
    write_task_summary,
    write_text,
)
from update_meta import apply_transition


EVENT_LOG_FILENAME = "orchestrator-events.jsonl"


@dataclass
class TaskContext:
    workspace: Path
    task_id: str
    task_dir: Path
    meta_path: Path
    meta: dict[str, Any]
    repo_root: Path
    worktree_path: Path | None

    def to_runtime_payload(self) -> dict[str, Any]:
        payload = dict(self.meta)
        payload.update(
            {
                "workspace": str(self.workspace),
                "task_dir": str(self.task_dir),
                "repo_root": str(self.repo_root),
                "worktree_path": str(self.worktree_path) if self.worktree_path else None,
            }
        )
        return payload


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
    deferred_fields = dict(set_fields or {})
    pre_transition_keys: list[str] = []
    if transition == "plan-updated":
        pre_transition_keys.extend(["planner_agent_id", "planner_session_resumable"])
    if transition == "review-started":
        pre_transition_keys.extend(["reviewer_agent_id", "reviewer_session_resumable"])

    for key in pre_transition_keys:
        if key in deferred_fields:
            meta[key] = deferred_fields.pop(key)

    if transition:
        apply_transition(meta, transition)
    for key, value in deferred_fields.items():
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
