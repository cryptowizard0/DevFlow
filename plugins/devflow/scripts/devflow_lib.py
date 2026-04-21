#!/usr/bin/env python3
"""Shared helpers for DevFlow task state, worktrees, and workspace summaries."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASKS_DIRNAME = "tasks"
ARCHITECTURES_DIRNAME = "architectures"
ACTIVE_TASK_FILENAME = "active-task.json"
ACTIVE_TASKS_FILENAME = "active-tasks.json"
GLOBAL_SUMMARY_JSON_FILENAME = "global-summary.json"
GLOBAL_SUMMARY_MD_FILENAME = "global-summary.md"
TASK_STATUS = (
    "draft",
    "planning",
    "plan_approved",
    "developing",
    "reviewing",
    "done",
)
EXECUTION_MODES = (
    "manual",
    "auto_dev",
)
AUTO_LOOP_STATES = (
    "running",
    "awaiting_done",
    "blocked",
)


SUMMARY_SECTION_KEYWORDS = {
    "key_structures": (
        "结构",
        "数据结构",
        "schema",
        "interface",
        "api",
        "contract",
        "protocol",
        "json",
        "meta",
        "file",
        "path",
        "worktree",
        "branch",
    ),
    "key_config": (
        "config",
        "配置",
        "环境",
        "env",
        "flag",
        "路径",
        "path",
        "命令",
        "变量",
        "workspace",
        "worktree",
        "branch",
    ),
    "pitfalls": (
        "坑",
        "bug",
        "错误",
        "失败",
        "fail",
        "issue",
        "mistake",
        "wrong",
        "blocked",
        "block",
        "gotcha",
        "注意不要",
    ),
    "cross_task_notes": (
        "依赖",
        "dependency",
        "其他 task",
        "其他任务",
        "共享",
        "shared",
        "global",
        "协调",
        "注意",
        "note",
        "upstream",
        "downstream",
    ),
}


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


def resolve_worktree_root() -> Path:
    explicit_root = os.environ.get("DEVFLOW_WORKTREE_ROOT")
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "worktrees" / "devflow"

    legacy_codex_root = Path.home() / ".codex"
    if legacy_codex_root.exists():
        return legacy_codex_root / "worktrees" / "devflow"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser().resolve() / "devflow" / "worktrees"

    return Path.home() / ".local" / "share" / "devflow" / "worktrees"


def empty_active_task_payload() -> dict[str, Any]:
    return {"task_id": None, "title": None, "task_dir": None, "status": None}


def empty_active_tasks_payload() -> dict[str, Any]:
    return {"focus_task_id": None, "tasks": []}


def empty_global_summary_payload() -> dict[str, Any]:
    return {
        "updated_at": None,
        "focus_task_id": None,
        "active_task_count": 0,
        "done_task_count": 0,
        "architecture_count": 0,
        "published_architecture_count": 0,
        "tasks": [],
        "architectures": [],
    }


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


def active_tasks_path(workspace: Path) -> Path:
    return workspace / ACTIVE_TASKS_FILENAME


def global_summary_json_path(workspace: Path) -> Path:
    return workspace / GLOBAL_SUMMARY_JSON_FILENAME


def global_summary_md_path(workspace: Path) -> Path:
    return workspace / GLOBAL_SUMMARY_MD_FILENAME


def tasks_dir(workspace: Path) -> Path:
    return workspace / TASKS_DIRNAME


def architectures_dir(workspace: Path) -> Path:
    return workspace / ARCHITECTURES_DIRNAME


def task_dir_for_id(workspace: Path, task_id: str) -> Path:
    return tasks_dir(workspace) / task_id


def architecture_dir_for_id(workspace: Path, architecture_id: str) -> Path:
    return architectures_dir(workspace) / architecture_id


def parse_iso_timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0


def clean_markdown(text: str) -> str:
    cleaned_lines = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def compact_line(value: str, max_length: int = 220) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def first_meaningful_line(*texts: str) -> str:
    for text in texts:
        cleaned = clean_markdown(text)
        for line in cleaned.splitlines():
            candidate = compact_line(line)
            if candidate:
                return candidate
    return "暂无概要。"


def extract_keyword_lines(texts: list[str], keywords: tuple[str, ...], limit: int = 4) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for text in texts:
        cleaned = clean_markdown(text)
        for raw_line in cleaned.splitlines():
            candidate = compact_line(raw_line)
            if not candidate:
                continue
            lowered = candidate.lower()
            if any(keyword in lowered for keyword in lowered_keywords):
                if candidate not in seen:
                    matches.append(candidate)
                    seen.add(candidate)
            if len(matches) >= limit:
                return matches
    return matches


def format_bullet_lines(lines: list[str], empty_text: str) -> str:
    if not lines:
        return f"- {empty_text}"
    return "\n".join(f"- {line}" for line in lines)


def ensure_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    tasks_dir(workspace).mkdir(parents=True, exist_ok=True)
    architectures_dir(workspace).mkdir(parents=True, exist_ok=True)

    legacy_path = active_task_path(workspace)
    active_index_path = active_tasks_path(workspace)

    if not legacy_path.exists() and not active_index_path.exists():
        write_json(legacy_path, empty_active_task_payload())
        write_json(active_index_path, empty_active_tasks_payload())
    elif not active_index_path.exists():
        legacy = read_json(legacy_path) if legacy_path.exists() else empty_active_task_payload()
        write_json(active_index_path, migrate_legacy_active_index(workspace, legacy))
    elif not legacy_path.exists():
        write_json(legacy_path, empty_active_task_payload())

    if not global_summary_json_path(workspace).exists():
        write_json(global_summary_json_path(workspace), empty_global_summary_payload())
    if not global_summary_md_path(workspace).exists():
        write_text(global_summary_md_path(workspace), "# Global Summary\n\n暂无任务摘要。\n")

    sync_workspace_state(workspace)


def migrate_legacy_active_index(workspace: Path, legacy_active: dict[str, Any]) -> dict[str, Any]:
    task_id = legacy_active.get("task_id")
    if not task_id:
        return empty_active_tasks_payload()

    task_dir = task_dir_for_id(workspace, task_id)
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        return empty_active_tasks_payload()

    meta = read_json(meta_path)
    if meta.get("status") == "done":
        return empty_active_tasks_payload()

    return {
        "focus_task_id": task_id,
        "tasks": [task_index_entry(workspace, meta)],
    }


def iter_task_meta(workspace: Path) -> list[tuple[Path, dict[str, Any]]]:
    results: list[tuple[Path, dict[str, Any]]] = []
    for task_dir in sorted(tasks_dir(workspace).iterdir()):
        if not task_dir.is_dir():
            continue
        meta_path = task_dir / "meta.json"
        if meta_path.exists():
            results.append((meta_path, read_json(meta_path)))
    return results


def iter_architecture_meta(workspace: Path) -> list[tuple[Path, dict[str, Any]]]:
    results: list[tuple[Path, dict[str, Any]]] = []
    for architecture_dir in sorted(architectures_dir(workspace).iterdir()):
        if not architecture_dir.is_dir():
            continue
        meta_path = architecture_dir / "meta.json"
        if meta_path.exists():
            results.append((meta_path, read_json(meta_path)))
    return results


def task_index_entry(workspace: Path, meta: dict[str, Any]) -> dict[str, Any]:
    task_id = meta["task_id"]
    return {
        "task_id": task_id,
        "title": meta.get("title"),
        "task_dir": str(task_dir_for_id(workspace, task_id)),
        "status": meta.get("status"),
        "is_blocked": meta.get("is_blocked", False),
        "execution_mode": meta.get("execution_mode", "manual"),
        "auto_loop_state": meta.get("auto_loop_state"),
        "worktree_path": meta.get("worktree_path"),
        "updated_at": meta.get("updated_at"),
    }


def sort_task_index_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: (
            -parse_iso_timestamp(entry.get("updated_at")),
            entry.get("task_id") or "",
        ),
    )


def focus_projection(active_index: dict[str, Any]) -> dict[str, Any]:
    focus_task_id = active_index.get("focus_task_id")
    if not focus_task_id:
        return empty_active_task_payload()

    for entry in active_index.get("tasks", []):
        if entry.get("task_id") == focus_task_id:
            return {
                "task_id": entry.get("task_id"),
                "title": entry.get("title"),
                "task_dir": entry.get("task_dir"),
                "status": entry.get("status"),
                "execution_mode": entry.get("execution_mode"),
                "auto_loop_state": entry.get("auto_loop_state"),
            }

    return empty_active_task_payload()


def sync_workspace_state(workspace: Path, preferred_focus_task_id: str | None = None) -> dict[str, Any]:
    entries = [
        task_index_entry(workspace, meta)
        for _, meta in iter_task_meta(workspace)
        if meta.get("status") != "done"
    ]
    entries = sort_task_index_entries(entries)

    existing_focus_task_id = None
    active_index_path = active_tasks_path(workspace)
    if active_index_path.exists():
        existing_focus_task_id = read_json(active_index_path).get("focus_task_id")
    if not existing_focus_task_id and active_task_path(workspace).exists():
        existing_focus_task_id = read_json(active_task_path(workspace)).get("task_id")

    valid_ids = {entry["task_id"] for entry in entries}
    focus_task_id = preferred_focus_task_id or existing_focus_task_id
    if focus_task_id not in valid_ids:
        focus_task_id = entries[0]["task_id"] if entries else None

    payload = {
        "focus_task_id": focus_task_id,
        "tasks": entries,
    }
    write_json(active_index_path, payload)
    write_json(active_task_path(workspace), focus_projection(payload))
    return payload


def load_active_task(workspace: Path) -> dict[str, Any]:
    ensure_workspace(workspace)
    return read_json(active_task_path(workspace))


def save_active_task(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(active_task_path(workspace), payload)
    focus_task_id = payload.get("task_id")
    sync_workspace_state(workspace, preferred_focus_task_id=focus_task_id)


def clear_active_task(workspace: Path) -> None:
    sync_workspace_state(workspace, preferred_focus_task_id=None)


def load_active_tasks(workspace: Path) -> dict[str, Any]:
    ensure_workspace(workspace)
    return read_json(active_tasks_path(workspace))


def save_active_tasks(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(active_tasks_path(workspace), payload)
    write_json(active_task_path(workspace), focus_projection(payload))


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


def next_architecture_id(workspace: Path) -> str:
    highest = 0
    for architecture_dir in architectures_dir(workspace).iterdir():
        if not architecture_dir.is_dir():
            continue
        name = architecture_dir.name
        if name.startswith("ARCH-"):
            suffix = name.split("ARCH-", 1)[1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return f"ARCH-{highest + 1:03d}"


def resolve_task_id(workspace: Path, task_id: str | None = None) -> str | None:
    if task_id:
        return task_id
    active_index = load_active_tasks(workspace)
    return active_index.get("focus_task_id") or load_active_task(workspace).get("task_id")


def load_meta(workspace: Path, task_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    resolved_task_id = resolve_task_id(workspace, task_id)
    if not resolved_task_id:
        raise FileNotFoundError("No focus task found.")
    task_dir = task_dir_for_id(workspace, resolved_task_id)
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for task {resolved_task_id}")
    return meta_path, read_json(meta_path)


def load_architecture_meta(workspace: Path, architecture_id: str) -> tuple[Path, dict[str, Any]]:
    architecture_dir = architecture_dir_for_id(workspace, architecture_id)
    meta_path = architecture_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for architecture {architecture_id}")
    return meta_path, read_json(meta_path)


def normalize_module_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError(f"Invalid module id: {value!r}")
    return normalized


def normalize_module_ids(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_module_id(value)
        if normalized in seen:
            continue
        normalized_values.append(normalized)
        seen.add(normalized)
    return normalized_values


def module_doc_path(architecture_dir: Path, module_id: str) -> Path:
    return architecture_dir / "modules" / f"{module_id}.md"


def normalize_task_architecture_binding(
    workspace: Path,
    meta: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    architecture_id = meta.get("architecture_id")
    module_id = meta.get("module_id")

    if not architecture_id and not module_id:
        meta["architecture_id"] = None
        meta["module_id"] = None
        meta["architecture_path"] = None
        return None, None, None

    if not architecture_id or not module_id:
        raise ValueError("Task architecture binding requires both architecture_id and module_id.")

    architecture_id = str(architecture_id)
    normalized_module_id = normalize_module_id(str(module_id))
    architecture_dir = architecture_dir_for_id(workspace, architecture_id)
    if not architecture_dir.exists():
        raise FileNotFoundError(f"Architecture not found: {architecture_id}")

    _, architecture_meta = load_architecture_meta(workspace, architecture_id)
    known_module_ids = normalize_module_ids(
        [str(item) for item in (architecture_meta.get("module_ids") or [])]
    )
    if known_module_ids and normalized_module_id not in known_module_ids:
        raise ValueError(
            f"Module {normalized_module_id} is not registered in architecture {architecture_id}."
        )

    module_path = module_doc_path(architecture_dir, normalized_module_id)
    if not module_path.exists():
        raise FileNotFoundError(f"Module document not found: {module_path}")

    meta["architecture_id"] = architecture_id
    meta["module_id"] = normalized_module_id
    meta["architecture_path"] = str(architecture_dir)
    return architecture_id, normalized_module_id, str(architecture_dir)


def init_meta(
    task_id: str,
    title: str,
    worktree_path: str,
    worktree_branch: str,
    worktree_base_ref: str,
    architecture_id: str | None = None,
    module_id: str | None = None,
    architecture_path: str | None = None,
) -> dict[str, Any]:
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
        "execution_mode": "manual",
        "auto_loop_state": None,
        "worktree_path": worktree_path,
        "worktree_branch": worktree_branch,
        "worktree_base_ref": worktree_base_ref,
        "architecture_id": architecture_id,
        "module_id": module_id,
        "architecture_path": architecture_path,
        "global_summary_updated_at": None,
    }


def is_auto_dev_enabled(meta: dict[str, Any] | None) -> bool:
    return bool(meta) and meta.get("execution_mode") == "auto_dev"


def is_auto_dev_running(meta: dict[str, Any] | None) -> bool:
    return is_auto_dev_enabled(meta) and meta.get("auto_loop_state") == "running"


def is_auto_dev_resumable(meta: dict[str, Any] | None) -> bool:
    return bool(meta) and is_auto_dev_running(meta) and meta.get("status") in {
        "plan_approved",
        "developing",
        "reviewing",
    }


def can_restart_auto_dev(meta: dict[str, Any] | None) -> bool:
    if not meta or meta.get("status") != "developing":
        return False
    if meta.get("next_action") not in {"dev", "review"}:
        return False
    if meta.get("execution_mode") != "auto_dev":
        return False
    return meta.get("auto_loop_state") in {None, "blocked"}


def auto_dev_next_step(meta: dict[str, Any] | None) -> str | None:
    if not meta or not is_auto_dev_enabled(meta):
        return None

    if meta.get("is_blocked") or meta.get("auto_loop_state") == "blocked":
        return None

    if meta.get("auto_loop_state") == "awaiting_done" or meta.get("next_action") == "done":
        return None

    if meta.get("auto_loop_state") != "running":
        return None

    status = meta.get("status")
    next_action = meta.get("next_action")

    if status == "plan_approved":
        return "dev"
    if status == "developing":
        if next_action == "review":
            return "review"
        return "dev"
    if status == "reviewing":
        return "await_review_result"
    return None


def auto_dev_stop_reason(meta: dict[str, Any] | None) -> str | None:
    if not meta or not is_auto_dev_enabled(meta):
        return "manual_mode"
    if meta.get("is_blocked") or meta.get("auto_loop_state") == "blocked":
        return "blocked"
    if meta.get("auto_loop_state") == "awaiting_done" or meta.get("next_action") == "done":
        return "awaiting_done"
    if meta.get("auto_loop_state") != "running":
        return "not_running"
    if auto_dev_next_step(meta):
        return None
    return "unsupported_state"


def allowed_actions_for_meta(meta: dict[str, Any] | None) -> list[str]:
    if meta is None:
        return ["start"]
    status = meta.get("status")
    if status == "planning":
        return ["update-plan", "approve-plan", "resume"]
    if status == "plan_approved":
        return ["update-plan", "dev", "auto-dev", "resume"]
    if status == "developing":
        actions = ["update-plan", "dev", "resume"]
        if is_auto_dev_resumable(meta) or can_restart_auto_dev(meta):
            actions.append("auto-dev")
        if meta.get("next_action") == "review":
            actions.append("review")
        if meta.get("next_action") == "done":
            actions.append("done")
        return actions
    if status == "reviewing":
        actions = ["update-plan", "resume"]
        if is_auto_dev_resumable(meta):
            actions.append("auto-dev")
        return actions
    if status == "done":
        return ["start", "resume"]
    return ["resume"]


def evaluate_gate(action: str, meta: dict[str, Any] | None, task_id: str | None = None) -> GateResult:
    if action == "start":
        return GateResult(action, True, "Parallel task start allowed.", None, None, ["start"], None)

    if meta is None or not task_id:
        return GateResult(action, False, "No target task found.", None, None, ["start"], None)

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

    if action == "approve-plan":
        allowed = status == "planning"
        return GateResult(
            action,
            allowed,
            "Plan approval requires planning status." if not allowed else "Plan approval allowed.",
            status,
            next_action,
            allowed_actions,
            task_id,
        )

    if action == "dev":
        allowed = status in {"plan_approved", "developing"}
        return GateResult(
            action,
            allowed,
            "Development requires an approved plan." if not allowed else "Development allowed.",
            status,
            next_action,
            allowed_actions,
            task_id,
        )

    if action == "auto-dev":
        allowed = status == "plan_approved" or is_auto_dev_resumable(meta) or can_restart_auto_dev(meta)
        reason = (
            "Auto-dev requires plan_approved, a resumable auto-dev task, or a restartable blocked auto-dev task."
            if not allowed
            else "Auto-dev allowed."
        )
        return GateResult(action, allowed, reason, status, next_action, allowed_actions, task_id)

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
        return GateResult(
            action,
            allowed,
            "Plan update allowed." if allowed else "Plan update is not allowed from the current status.",
            status,
            next_action,
            allowed_actions,
            task_id,
        )

    if action == "resume":
        return GateResult(action, True, "Resume allowed.", status, next_action, allowed_actions, task_id)

    return GateResult(action, False, f"Unknown action: {action}", status, next_action, allowed_actions, task_id)


def repo_root_for_workspace(workspace: Path) -> Path:
    for candidate in [workspace.parent, *workspace.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise FileNotFoundError(f"Unable to locate git repo root for workspace {workspace}")


def run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def resolve_worktree_base_ref(repo_root: Path) -> str:
    branch_name = run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch_name and branch_name != "HEAD":
        return branch_name
    return run_git(repo_root, "rev-parse", "HEAD")


def default_worktree_path(repo_root: Path, task_id: str) -> Path:
    return resolve_worktree_root() / repo_root.name / task_id


def create_task_worktree(repo_root: Path, task_id: str) -> tuple[Path, str, str]:
    worktree_path = default_worktree_path(repo_root, task_id)
    worktree_branch = f"codex/devflow/{task_id}"
    worktree_base_ref = resolve_worktree_base_ref(repo_root)

    if worktree_path.exists() and any(worktree_path.iterdir()):
        raise FileExistsError(f"Worktree path already exists and is not empty: {worktree_path}")

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", worktree_branch, str(worktree_path), worktree_base_ref],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return worktree_path, worktree_branch, worktree_base_ref


def architecture_file_names() -> list[str]:
    return [
        "request.md",
        "outline.md",
        "architecture.md",
        "data-structures.md",
        "constraints.md",
        "development-plan.md",
        "summary.md",
    ]


def init_architecture_meta(architecture_id: str, title: str, module_ids: list[str]) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "architecture_id": architecture_id,
        "title": title,
        "status": "discovering",
        "created_at": timestamp,
        "updated_at": timestamp,
        "outline_version": 0,
        "module_ids": normalize_module_ids(module_ids),
        "linked_task_ids": [],
    }


def create_architecture_files(
    architecture_dir: Path,
    title: str,
    request_text: str,
    architecture_id: str,
    module_ids: list[str],
) -> None:
    timestamp = now_iso()
    normalized_module_ids = normalize_module_ids(module_ids)
    modules_dir = architecture_dir / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)

    write_text(
        architecture_dir / "request.md",
        (
            "# Request\n\n"
            f"- Architecture ID: `{architecture_id}`\n"
            f"- Title: {title}\n"
            f"- Created At: {timestamp}\n\n"
            "## Request\n\n"
            f"{request_text.strip()}\n"
        ),
    )
    write_text(
        architecture_dir / "outline.md",
        (
            "# Outline\n\n"
            "Outline not drafted yet.\n"
        ),
    )
    write_text(
        architecture_dir / "architecture.md",
        (
            "# Architecture Design\n\n"
            "Architecture design not published yet.\n"
        ),
    )
    write_text(
        architecture_dir / "data-structures.md",
        (
            "# Data Structures\n\n"
            "Data structure design not published yet.\n"
        ),
    )
    write_text(
        architecture_dir / "constraints.md",
        (
            "# Constraints\n\n"
            "Project constraints not published yet.\n"
        ),
    )
    write_text(
        architecture_dir / "development-plan.md",
        (
            "# Development Plan\n\n"
            "Development sequencing not published yet.\n"
        ),
    )
    for module_id in normalized_module_ids:
        write_text(
            module_doc_path(architecture_dir, module_id),
            (
                f"# Module: {module_id}\n\n"
                "Module design not published yet.\n"
            ),
        )
    write_text(
        architecture_dir / "summary.md",
        (
            "# Architecture Summary\n\n"
            "This file summarizes a published architecture package for downstream DevFlow tasks.\n"
        ),
    )


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
    write_text(
        task_dir / "summary.md",
        "# Summary\n\n"
        "This is the task-local summary for the current task. "
        "It records the latest task snapshot, key structures, config notes, and pitfalls for this task only. "
        "Use `DevFlowWorkspace/global-summary.md` for cross-task shared context.\n",
    )


def build_architecture_summary_entry(architecture_dir: Path) -> dict[str, Any]:
    meta = read_json(architecture_dir / "meta.json")
    request_text = read_text(architecture_dir / "request.md")
    outline_text = read_text(architecture_dir / "outline.md")
    architecture_text = read_text(architecture_dir / "architecture.md")
    data_structures_text = read_text(architecture_dir / "data-structures.md")
    constraints_text = read_text(architecture_dir / "constraints.md")
    development_plan_text = read_text(architecture_dir / "development-plan.md")
    module_texts = [
        read_text(path)
        for path in sorted((architecture_dir / "modules").glob("*.md"))
    ]
    sources = [
        request_text,
        outline_text,
        architecture_text,
        data_structures_text,
        constraints_text,
        development_plan_text,
        *module_texts,
    ]

    return {
        "architecture_id": meta.get("architecture_id"),
        "title": meta.get("title"),
        "status": meta.get("status"),
        "updated_at": meta.get("updated_at"),
        "outline_version": meta.get("outline_version"),
        "module_ids": normalize_module_ids([str(item) for item in (meta.get("module_ids") or [])]),
        "linked_task_ids": [str(item) for item in (meta.get("linked_task_ids") or [])],
        "overview": first_meaningful_line(architecture_text, outline_text, request_text, *module_texts),
        "key_structures": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_structures"]),
        "key_config": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_config"]),
        "pitfalls": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["pitfalls"]),
        "cross_task_notes": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["cross_task_notes"]),
    }


def render_architecture_summary(architecture_dir: Path) -> str:
    entry = build_architecture_summary_entry(architecture_dir)
    module_list = ", ".join(f"`{item}`" for item in entry["module_ids"]) or "n/a"
    linked_task_list = ", ".join(f"`{item}`" for item in entry["linked_task_ids"]) or "n/a"
    return "\n".join(
        [
            "# Architecture Summary",
            "",
            "Architecture-local summary only. This file is the downstream handoff snapshot for this architecture package.",
            "",
            f"- Architecture ID: `{entry['architecture_id']}`",
            f"- Title: {entry['title']}",
            f"- Status: `{entry['status']}`",
            f"- Outline Version: `{entry['outline_version']}`",
            f"- Modules: {module_list}",
            f"- Linked Tasks: {linked_task_list}",
            f"- Last Updated: {entry['updated_at'] or 'n/a'}",
            "",
            "## Overview",
            "",
            entry["overview"],
            "",
            "## Key Structures / Interfaces / File Contracts",
            "",
            format_bullet_lines(entry["key_structures"], "No clear records yet."),
            "",
            "## Key Config / Environment",
            "",
            format_bullet_lines(entry["key_config"], "No clear records yet."),
            "",
            "## Pitfalls / Bugs / Mistakes",
            "",
            format_bullet_lines(entry["pitfalls"], "No clear records yet."),
            "",
            "## Cross-Task Notes",
            "",
            format_bullet_lines(entry["cross_task_notes"], "No clear records yet."),
            "",
        ]
    )


def write_architecture_summary(architecture_dir: Path) -> Path:
    summary_path = architecture_dir / "summary.md"
    write_text(summary_path, render_architecture_summary(architecture_dir))
    return summary_path


def build_task_summary_entry(task_dir: Path) -> dict[str, Any]:
    meta = read_json(task_dir / "meta.json")
    request_text = read_text(task_dir / "request.md")
    plan_text = read_text(task_dir / "plan.md")
    dev_text = read_text(task_dir / "dev.md")
    review_text = read_text(task_dir / "review.md")
    change_summary_text = read_text(task_dir / "change-summary.md")
    sources = [request_text, plan_text, dev_text, review_text, change_summary_text]

    architecture_id = meta.get("architecture_id")
    architecture_path = meta.get("architecture_path")
    module_id = meta.get("module_id")
    architecture_title = None
    architecture_overview = None
    if architecture_id and architecture_path:
        architecture_dir = Path(str(architecture_path))
        meta_path = architecture_dir / "meta.json"
        if meta_path.exists():
            architecture_meta = read_json(meta_path)
            architecture_title = architecture_meta.get("title")
        architecture_sources = [
            read_text(architecture_dir / "summary.md"),
            read_text(architecture_dir / "architecture.md"),
            read_text(architecture_dir / "data-structures.md"),
            read_text(architecture_dir / "constraints.md"),
            read_text(architecture_dir / "development-plan.md"),
        ]
        if module_id:
            architecture_sources.append(read_text(module_doc_path(architecture_dir, str(module_id))))
        sources.extend(architecture_sources)
        architecture_overview = first_meaningful_line(*architecture_sources)

    return {
        "task_id": meta.get("task_id"),
        "title": meta.get("title"),
        "status": meta.get("status"),
        "next_action": meta.get("next_action"),
        "execution_mode": meta.get("execution_mode", "manual"),
        "auto_loop_state": meta.get("auto_loop_state"),
        "auto_dev_next_step": auto_dev_next_step(meta),
        "is_blocked": meta.get("is_blocked", False),
        "block_reason": meta.get("block_reason"),
        "updated_at": meta.get("updated_at"),
        "worktree_path": meta.get("worktree_path"),
        "worktree_branch": meta.get("worktree_branch"),
        "worktree_base_ref": meta.get("worktree_base_ref"),
        "architecture_id": architecture_id,
        "module_id": module_id,
        "architecture_path": architecture_path,
        "architecture_title": architecture_title,
        "architecture_overview": architecture_overview,
        "overview": first_meaningful_line(dev_text, plan_text, architecture_overview or "", request_text, review_text),
        "key_structures": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_structures"]),
        "key_config": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_config"]),
        "pitfalls": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["pitfalls"]),
        "cross_task_notes": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["cross_task_notes"]),
    }


def render_task_summary(task_dir: Path) -> str:
    entry = build_task_summary_entry(task_dir)
    return "\n".join(
        [
            "# Summary",
            "",
            "Task-local summary only. This file is the handoff and recovery snapshot for this task.",
            "It is not the cross-task shared summary; use `DevFlowWorkspace/global-summary.md` for workspace-level knowledge.",
            "",
            f"- Task ID: `{entry['task_id']}`",
            f"- Title: {entry['title']}",
            f"- Stage Status: `{entry['status']}`",
            f"- Next Action: `{entry['next_action'] or 'n/a'}`",
            f"- Execution Mode: `{entry['execution_mode'] or 'manual'}`",
            f"- Auto Loop State: `{entry['auto_loop_state'] or 'n/a'}`",
            f"- Auto Next Step: `{entry['auto_dev_next_step'] or 'n/a'}`",
            f"- Blocked: {'yes' if entry['is_blocked'] else 'no'}",
            f"- Block Reason: {entry['block_reason'] or 'n/a'}",
            f"- Worktree Path: `{entry['worktree_path'] or 'n/a'}`",
            f"- Worktree Branch: `{entry['worktree_branch'] or 'n/a'}`",
            f"- Worktree Base Ref: `{entry['worktree_base_ref'] or 'n/a'}`",
            f"- Architecture ID: `{entry['architecture_id'] or 'n/a'}`",
            f"- Module ID: `{entry['module_id'] or 'n/a'}`",
            f"- Architecture Path: `{entry['architecture_path'] or 'n/a'}`",
            f"- Last Updated: {entry['updated_at'] or 'n/a'}",
            "",
            "## Architecture Context",
            "",
            entry["architecture_overview"] or "No linked architecture.",
            "",
            "## Work Overview",
            "",
            entry["overview"],
            "",
            "## Key Structures / Interfaces / File Contracts",
            "",
            format_bullet_lines(entry["key_structures"], "暂无明确记录。"),
            "",
            "## Key Config / Environment",
            "",
            format_bullet_lines(entry["key_config"], "暂无明确记录。"),
            "",
            "## Pitfalls / Bugs / Mistakes",
            "",
            format_bullet_lines(entry["pitfalls"], "暂无明确记录。"),
            "",
            "## Cross-Task Notes",
            "",
            format_bullet_lines(entry["cross_task_notes"], "暂无明确记录。"),
            "",
        ]
    )


def write_task_summary(task_dir: Path) -> Path:
    summary_path = task_dir / "summary.md"
    write_text(summary_path, render_task_summary(task_dir))
    return summary_path


def sync_architecture_linked_tasks(workspace: Path) -> None:
    task_links: dict[str, list[str]] = {}
    for _, task_meta in iter_task_meta(workspace):
        architecture_id = task_meta.get("architecture_id")
        if not architecture_id:
            continue
        task_links.setdefault(str(architecture_id), []).append(str(task_meta["task_id"]))

    for meta_path, architecture_meta in iter_architecture_meta(workspace):
        architecture_id = str(architecture_meta.get("architecture_id"))
        linked_task_ids = sorted(task_links.get(architecture_id, []))
        if architecture_meta.get("linked_task_ids") == linked_task_ids:
            continue
        architecture_meta["linked_task_ids"] = linked_task_ids
        architecture_meta["updated_at"] = now_iso()
        write_json(meta_path, architecture_meta)


def build_global_summary_payload(workspace: Path) -> dict[str, Any]:
    active_index = load_active_tasks(workspace)
    task_entries: list[dict[str, Any]] = []
    done_task_count = 0
    for _, meta in iter_task_meta(workspace):
        task_dir = task_dir_for_id(workspace, meta["task_id"])
        entry = build_task_summary_entry(task_dir)
        task_entries.append(entry)
        if meta.get("status") == "done":
            done_task_count += 1

    task_entries.sort(
        key=lambda entry: (-parse_iso_timestamp(entry.get("updated_at")), entry.get("task_id") or "")
    )

    architecture_entries = [
        build_architecture_summary_entry(meta_path.parent)
        for meta_path, _ in iter_architecture_meta(workspace)
    ]
    architecture_entries.sort(
        key=lambda entry: (-parse_iso_timestamp(entry.get("updated_at")), entry.get("architecture_id") or "")
    )

    return {
        "updated_at": now_iso(),
        "focus_task_id": active_index.get("focus_task_id"),
        "active_task_count": len(active_index.get("tasks", [])),
        "done_task_count": done_task_count,
        "architecture_count": len(architecture_entries),
        "published_architecture_count": sum(
            1 for entry in architecture_entries if entry.get("status") == "published"
        ),
        "tasks": task_entries,
        "architectures": architecture_entries,
    }


def render_global_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# Global Summary",
        "",
        f"- Updated At: {payload.get('updated_at') or 'n/a'}",
        f"- Focus Task: `{payload.get('focus_task_id') or 'n/a'}`",
        f"- Active Tasks: {payload.get('active_task_count', 0)}",
        f"- Done Tasks: {payload.get('done_task_count', 0)}",
        f"- Architectures: {payload.get('architecture_count', 0)}",
        f"- Published Architectures: {payload.get('published_architecture_count', 0)}",
        "",
        "新 task 在规划或开发前应先阅读本文件，优先复用已有结论并避开已知坑。",
        "",
    ]

    tasks = payload.get("tasks", [])
    if not tasks:
        lines.extend(["暂无任务摘要。", ""])
        return "\n".join(lines)

    for entry in tasks:
        lines.extend(
            [
                f"## {entry['task_id']} · {entry['title']}",
                "",
                f"- Stage Status: `{entry['status']}`",
                f"- Next Action: `{entry['next_action'] or 'n/a'}`",
                f"- Execution Mode: `{entry['execution_mode'] or 'manual'}`",
                f"- Auto Loop State: `{entry['auto_loop_state'] or 'n/a'}`",
                f"- Worktree: `{entry['worktree_path'] or 'n/a'}`",
                f"- Branch: `{entry['worktree_branch'] or 'n/a'}`",
                f"- Architecture: `{entry['architecture_id'] or 'n/a'}` / module `{entry['module_id'] or 'n/a'}`",
                f"- Updated At: {entry['updated_at'] or 'n/a'}",
                "",
                entry["architecture_overview"] or "No linked architecture.",
                "",
                entry["overview"],
                "",
                "### Key Structures / Interfaces / File Contracts",
                "",
                format_bullet_lines(entry["key_structures"], "暂无明确记录。"),
                "",
                "### Key Config / Environment",
                "",
                format_bullet_lines(entry["key_config"], "暂无明确记录。"),
                "",
                "### Pitfalls / Bugs / Mistakes",
                "",
                format_bullet_lines(entry["pitfalls"], "暂无明确记录。"),
                "",
                "### Cross-Task Notes",
                "",
                format_bullet_lines(entry["cross_task_notes"], "暂无明确记录。"),
                "",
            ]
        )

    architectures = payload.get("architectures", [])
    if architectures:
        lines.extend(["## Architectures", ""])
        for entry in architectures:
            module_list = ", ".join(f"`{item}`" for item in entry.get("module_ids", [])) or "n/a"
            linked_task_list = ", ".join(f"`{item}`" for item in entry.get("linked_task_ids", [])) or "n/a"
            lines.extend(
                [
                    f"### {entry['architecture_id']} · {entry['title']}",
                    "",
                    f"- Status: `{entry['status']}`",
                    f"- Modules: {module_list}",
                    f"- Linked Tasks: {linked_task_list}",
                    f"- Updated At: {entry['updated_at'] or 'n/a'}",
                    "",
                    entry["overview"],
                    "",
                ]
            )

    return "\n".join(lines)


def update_task_global_summary_timestamp(task_dir: Path, timestamp: str) -> None:
    meta_path = task_dir / "meta.json"
    meta = read_json(meta_path)
    meta["global_summary_updated_at"] = timestamp
    write_json(meta_path, meta)


def write_global_summary(workspace: Path, touched_task_id: str | None = None) -> tuple[Path, Path]:
    sync_architecture_linked_tasks(workspace)
    payload = build_global_summary_payload(workspace)
    write_json(global_summary_json_path(workspace), payload)
    write_text(global_summary_md_path(workspace), render_global_summary(payload))
    if touched_task_id:
        task_dir = task_dir_for_id(workspace, touched_task_id)
        meta_path = task_dir / "meta.json"
        if meta_path.exists():
            update_task_global_summary_timestamp(task_dir, payload["updated_at"])
    return global_summary_json_path(workspace), global_summary_md_path(workspace)
