#!/usr/bin/env python3
"""Shared helpers for DevFlow task state and filesystem operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASKS_DIRNAME = "tasks"
ACTIVE_TASK_FILENAME = "active-task.json"
TASK_STATUS = (
    "draft",
    "planning",
    "plan_approved",
    "developing",
    "reviewing",
    "done",
)


@dataclass
class GateResult:
    action: str
    allowed: bool
    reason: str
    status: str | None
    next_action: str | None
    allowed_actions: list[str]
    task_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "reason": self.reason,
            "status": self.status,
            "next_action": self.next_action,
            "allowed_actions": self.allowed_actions,
            "task_id": self.task_id,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / TASKS_DIRNAME).mkdir(parents=True, exist_ok=True)
    active_path = workspace / ACTIVE_TASK_FILENAME
    if not active_path.exists():
        write_json(
            active_path,
            {
                "task_id": None,
                "title": None,
                "task_dir": None,
                "status": None,
            },
        )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def active_task_path(workspace: Path) -> Path:
    return workspace / ACTIVE_TASK_FILENAME


def load_active_task(workspace: Path) -> dict[str, Any]:
    ensure_workspace(workspace)
    return read_json(active_task_path(workspace))


def save_active_task(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(active_task_path(workspace), payload)


def clear_active_task(workspace: Path) -> None:
    save_active_task(
        workspace,
        {"task_id": None, "title": None, "task_dir": None, "status": None},
    )


def tasks_dir(workspace: Path) -> Path:
    return workspace / TASKS_DIRNAME


def next_task_id(workspace: Path) -> str:
    highest = 0
    for task_dir in tasks_dir(workspace).iterdir():
        if not task_dir.is_dir():
            continue
        name = task_dir.name
        if name.startswith("TASK-"):
            suffix = name.split("TASK-", 1)[1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return f"TASK-{highest + 1:03d}"


def task_dir_for_id(workspace: Path, task_id: str) -> Path:
    return tasks_dir(workspace) / task_id


def load_meta(workspace: Path, task_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    active = load_active_task(workspace)
    resolved_task_id = task_id or active.get("task_id")
    if not resolved_task_id:
        raise FileNotFoundError("No active task found.")
    task_dir = task_dir_for_id(workspace, resolved_task_id)
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for task {resolved_task_id}")
    return meta_path, read_json(meta_path)


def init_meta(task_id: str, title: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "task_id": task_id,
        "title": title,
        "status": "planning",
        "created_at": timestamp,
        "updated_at": timestamp,
        "plan_version": 1,
        "review_round": 0,
        "current_step": "draft initial plan",
        "last_completed_step": None,
        "next_action": "update-plan",
        "is_blocked": False,
        "block_reason": None,
        "approved_at": None,
        "approved_by": None,
        "planner_agent_name": "Planner",
        "planner_agent_id": None,
        "planner_agent_status": None,
        "reviewer_agent_name": "Reviewer",
        "reviewer_agent_id": None,
        "reviewer_agent_status": None,
        "last_review_verdict": None,
        "last_reviewed_at": None,
        "review_passed_at": None,
        "completed_at": None,
    }


def allowed_actions_for_meta(meta: dict[str, Any] | None) -> list[str]:
    if meta is None:
        return ["start"]
    status = meta.get("status")
    if status == "planning":
        return ["update-plan", "approve-plan", "resume"]
    if status == "plan_approved":
        return ["update-plan", "dev", "resume"]
    if status == "developing":
        actions = ["update-plan", "dev", "resume"]
        if meta.get("next_action") == "review":
            actions.append("review")
        if meta.get("next_action") == "done":
            actions.append("done")
        return actions
    if status == "reviewing":
        return ["update-plan", "resume"]
    if status == "done":
        return ["start", "resume"]
    return ["resume"]


def evaluate_gate(action: str, active: dict[str, Any], meta: dict[str, Any] | None) -> GateResult:
    task_id = active.get("task_id")
    if not task_id or meta is None:
        if action == "start":
            return GateResult(action, True, "No active task. Starting a new task is allowed.", None, None, ["start"], None)
        return GateResult(action, False, "No active task found.", None, None, ["start"], None)

    status = meta.get("status")
    allowed_actions = allowed_actions_for_meta(meta)
    next_action = meta.get("next_action")

    if meta.get("is_blocked") and action != "resume":
        return GateResult(
            action,
            False,
            f"Task is blocked: {meta.get('block_reason') or 'unknown reason'}",
            status,
            next_action,
            ["resume"],
            task_id,
        )

    if action == "start":
        if status == "done":
            return GateResult(action, True, "Active task is already done; a new task may be started.", status, next_action, allowed_actions, task_id)
        return GateResult(action, False, "Another task is still active.", status, next_action, allowed_actions, task_id)

    if action == "approve-plan":
        allowed = status == "planning"
        return GateResult(action, allowed, "Plan approval requires planning status." if not allowed else "Plan approval allowed.", status, next_action, allowed_actions, task_id)

    if action == "dev":
        allowed = status in {"plan_approved", "developing"}
        return GateResult(action, allowed, "Development requires an approved plan." if not allowed else "Development allowed.", status, next_action, allowed_actions, task_id)

    if action == "review":
        allowed = status == "developing" and next_action == "review"
        reason = "Review requires developing status with next_action=review." if not allowed else "Review allowed."
        return GateResult(action, allowed, reason, status, next_action, allowed_actions, task_id)

    if action == "done":
        allowed = status == "developing" and next_action == "done"
        reason = "Done requires developing status with next_action=done." if not allowed else "Done allowed."
        return GateResult(action, allowed, reason, status, next_action, allowed_actions, task_id)

    if action == "update-plan":
        allowed = status in {"planning", "plan_approved", "developing", "reviewing"}
        return GateResult(action, allowed, "Plan update allowed." if allowed else "Plan update is not allowed from the current status.", status, next_action, allowed_actions, task_id)

    if action == "resume":
        return GateResult(action, True, "Resume allowed.", status, next_action, allowed_actions, task_id)

    return GateResult(action, False, f"Unknown action: {action}", status, next_action, allowed_actions, task_id)


def task_file_names() -> list[str]:
    return [
        "request.md",
        "plan.md",
        "plan-history.md",
        "dev.md",
        "change-summary.md",
        "review.md",
        "summary.md",
    ]


def create_task_files(task_dir: Path, title: str, request_text: str, task_id: str) -> None:
    timestamp = now_iso()
    write_text(task_dir / "request.md", f"# Request\n\n- Task ID: `{task_id}`\n- Title: {title}\n- Created At: {timestamp}\n\n## Request\n\n{request_text.strip()}\n")
    write_text(task_dir / "plan.md", "# Plan\n\nPlan not drafted yet.\n")
    write_text(task_dir / "plan-history.md", "# Plan History\n")
    write_text(task_dir / "dev.md", "# Development Log\n")
    write_text(task_dir / "change-summary.md", "# Change Summary\n\nNot generated yet.\n")
    write_text(task_dir / "review.md", "# Review\n\nReview not run yet.\n")
    write_text(task_dir / "summary.md", "# Summary\n\nTask not completed yet.\n")
