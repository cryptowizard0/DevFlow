#!/usr/bin/env python3
"""Shared helpers for DevFlow project/task state, worktrees, and workspace summaries."""

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
PROJECTS_DIRNAME = "projects"
ACTIVE_TASK_FILENAME = "active-task.json"
ACTIVE_TASKS_FILENAME = "active-tasks.json"
ACTIVE_PROJECT_FILENAME = "active-project.json"
GLOBAL_SUMMARY_JSON_FILENAME = "global-summary.json"
GLOBAL_SUMMARY_MD_FILENAME = "global-summary.md"

DEFAULT_PROJECT_ID = "PROJECT-001"
TASK_STATUS = (
    "draft",
    "planning",
    "plan_approved",
    "developing",
    "reviewing",
    "done",
)
PROJECT_STATUS = (
    "architecting",
    "architecture_approved",
)
ARCHITECTURE_COMPLIANCE_STATUS = (
    "pending",
    "compliant",
    "deviation",
    "needs_architect_decision",
    "approved_exception",
)
REQUIRED_PLAN_SECTIONS = (
    "Architecture Context",
    "Modules In Scope",
    "Constraints Checklist",
    "Required Exceptions",
    "Implementation Order",
)
PROJECT_DOC_FILENAMES = (
    "request.md",
    "architecture.md",
    "module-map.md",
    "standards.md",
    "roadmap.md",
    "constraints.json",
    "architecture-history.md",
    "summary.md",
)
PLACEHOLDER_SENTINELS = {
    "pending",
    "pending.",
    "tbd",
    "todo",
}
PROJECT_DOC_REQUIRED_SECTIONS = {
    "architecture.md": {
        "System Description": "Describe what the system is, what it does, and who it serves.",
        "Tech Stack": "List the primary languages, frameworks, storage systems, infrastructure, and runtime dependencies.",
        "Overall Architecture": "Describe the top-level architecture shape and the major subsystems.",
        "Runtime Flow And Data Flow": "Explain the key runtime flows, request flows, background flows, and data movement between modules.",
        "Module Split": "List the major modules and summarize what each one owns.",
        "Cross-Module Constraints And Relationships": "Describe the most important relationships, dependency directions, and restrictions between modules.",
        "Schema And Data Structure Design": "Describe the key schemas, entities, messages, and shared data structures.",
        "Project Directory Layout": "Describe the intended repository / package / service layout.",
        "Key Design Decisions": "Record the critical architecture decisions that downstream tasks must follow.",
    },
    "standards.md": {
        "Code Standards": "Define coding conventions and readability expectations.",
        "Testing Requirements": "Define the minimum test bar for each module or task.",
        "Error Handling": "Define error propagation, retries, and user-facing failures.",
        "Logging And Observability": "Define logging, tracing, and monitoring expectations.",
        "API And Interface Contracts": "Define serialization, compatibility, and interface guarantees.",
    },
    "roadmap.md": {
        "Delivery Order": "List the preferred module implementation order.",
        "Suggested Task Breakdown": "List the recommended task slices under the current architecture baseline.",
    },
}
DEV_DOC_REQUIRED_SECTIONS = {
    "Compliance Declaration": "Record the followed constraints, referenced architecture docs, and used exceptions.",
    "Work Log": "Record the implementation work that was actually done in this development slice.",
}
ARCHITECTURE_CHANGE_REQUEST_REQUIRED_SECTIONS = {
    "Context": "Explain what implementation or review situation triggered this architecture change request.",
    "Requested Change": "Describe the architecture, roadmap, or exception change being requested.",
    "Why Current Architecture Blocks This Task": "Explain why the current approved baseline is insufficient.",
    "Impacted Modules Or Constraints": "List the impacted modules, constraints, and any affected ADRs.",
}
MODULE_MAP_PLACEHOLDERS = (
    "Fill in the module contract before starting tasks.",
    "add a module spec link when available",
)
IMPLEMENTATION_VERDICTS = ("pass", "changes_requested", "blocked")
ARCHITECTURE_VERDICTS = ("compliant", "deviation", "needs_architect_decision")
TASK_META_PROTECTED_KEYS = {
    "task_id",
    "title",
    "project_id",
    "status",
    "created_at",
    "updated_at",
    "plan_version",
    "review_round",
    "next_action",
    "is_blocked",
    "block_reason",
    "approved_at",
    "last_review_verdict",
    "last_reviewed_at",
    "review_passed_at",
    "completed_at",
    "worktree_path",
    "worktree_branch",
    "worktree_base_ref",
    "architecture_version",
    "module_scope",
    "constraint_refs",
    "exception_ids",
    "architecture_compliance_status",
}
PROJECT_META_PROTECTED_KEYS = {
    "project_id",
    "title",
    "status",
    "created_at",
    "updated_at",
    "architecture_version",
    "next_action",
    "approved_at",
    "changed_modules",
    "changed_constraint_refs",
}


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
        "module",
        "architecture",
        "constraint",
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
        "roadmap",
        "standard",
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
        "exception",
        "deviation",
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
        "architect",
        "module",
        "adr",
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
    project_id: str | None = None
    project_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "reason": self.reason,
            "status": self.status,
            "next_action": self.next_action,
            "allowed_actions": self.allowed_actions,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "project_status": self.project_status,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        results: list[str] = []
        for item in value:
            results.extend(normalize_string_list(item))
        return results
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value).strip()] if str(value).strip() else []


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        if value not in seen:
            results.append(value)
            seen.add(value)
    return results


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


def empty_active_project_payload() -> dict[str, Any]:
    return {
        "project_id": None,
        "title": None,
        "project_dir": None,
        "status": None,
        "architecture_version": None,
        "next_action": None,
    }


def empty_global_summary_payload() -> dict[str, Any]:
    return {
        "updated_at": None,
        "focus_task_id": None,
        "active_project_id": None,
        "active_task_count": 0,
        "done_task_count": 0,
        "needs_architect_count": 0,
        "project": None,
        "tasks": [],
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


def active_project_path(workspace: Path) -> Path:
    return workspace / ACTIVE_PROJECT_FILENAME


def global_summary_json_path(workspace: Path) -> Path:
    return workspace / GLOBAL_SUMMARY_JSON_FILENAME


def global_summary_md_path(workspace: Path) -> Path:
    return workspace / GLOBAL_SUMMARY_MD_FILENAME


def tasks_dir(workspace: Path) -> Path:
    return workspace / TASKS_DIRNAME


def projects_dir(workspace: Path) -> Path:
    return workspace / PROJECTS_DIRNAME


def task_dir_for_id(workspace: Path, task_id: str) -> Path:
    return tasks_dir(workspace) / task_id


def project_dir_for_id(workspace: Path, project_id: str) -> Path:
    return projects_dir(workspace) / project_id


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


def extract_markdown_sections(text: str, heading_prefix: str = "## ") -> dict[str, str]:
    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []

    for raw_line in text.splitlines():
        if raw_line.startswith(heading_prefix):
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
            current_heading = raw_line[len(heading_prefix) :].strip()
            buffer = []
            continue
        if current_heading is not None:
            buffer.append(raw_line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections


def normalized_doc_content(text: str) -> str:
    return clean_markdown(text).strip().lower()


def is_placeholder_content(content: str, placeholder: str | None = None) -> bool:
    normalized = normalized_doc_content(content)
    if not normalized or normalized in PLACEHOLDER_SENTINELS:
        return True
    if placeholder and normalized == normalized_doc_content(placeholder):
        return True
    return False


def validate_required_markdown_sections(path: Path, required_sections: dict[str, str]) -> list[str]:
    text = read_text(path)
    sections = extract_markdown_sections(text)
    errors: list[str] = []
    for section, placeholder in required_sections.items():
        if section not in sections:
            errors.append(f"{path.name} is missing required section: {section}.")
            continue
        if is_placeholder_content(sections[section], placeholder):
            errors.append(f"{path.name} section '{section}' still contains placeholder content.")
    return errors


def validate_module_map_document(path: Path) -> list[str]:
    text = read_text(path)
    normalized = normalized_doc_content(text)
    errors: list[str] = []

    if not normalized:
        return [f"{path.name} is empty."]

    if any(placeholder.lower() in normalized for placeholder in (item.lower() for item in MODULE_MAP_PLACEHOLDERS)):
        errors.append(f"{path.name} still contains scaffold placeholder rows.")

    sections = extract_markdown_sections(text)
    if "Module Index" not in sections:
        errors.append(f"{path.name} is missing required section: Module Index.")

    table_rows = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("|")
        and "Module ID" not in line
        and "---" not in line
    ]
    if not table_rows:
        errors.append(f"{path.name} must contain at least one concrete module row.")
    elif all("example-module" in row for row in table_rows):
        errors.append(f"{path.name} must replace the example module row with real module data.")

    return errors


def split_doc_ref(doc_ref: str) -> tuple[str, str | None]:
    path, _, anchor = doc_ref.partition("#")
    return path.strip(), anchor.strip() or None


def validate_doc_ref(project_dir: Path, raw_doc_ref: str) -> list[str]:
    doc_path_part, anchor = split_doc_ref(raw_doc_ref)
    if not doc_path_part:
        return [f"doc_ref '{raw_doc_ref}' is missing a file path."]

    candidate = (project_dir / doc_path_part).resolve()
    try:
        candidate.relative_to(project_dir.resolve())
    except ValueError:
        return [f"doc_ref '{raw_doc_ref}' escapes the project directory."]

    if not candidate.exists() or not candidate.is_file():
        return [f"doc_ref '{raw_doc_ref}' points to a missing file."]

    content = read_text(candidate)
    if not normalized_doc_content(content):
        return [f"doc_ref '{raw_doc_ref}' points to an empty file."]

    if anchor:
        sections = extract_markdown_sections(content, heading_prefix="## ")
        all_headings = set(sections.keys())
        all_headings.update(
            line.lstrip("#").strip()
            for line in content.splitlines()
            if line.startswith("#")
        )
        if anchor not in all_headings:
            return [f"doc_ref '{raw_doc_ref}' points to missing heading '{anchor}'."]

    return []


def parse_labeled_bullets(section_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        label, separator, value = line[2:].partition(":")
        if not separator:
            continue
        parsed[label.strip()] = value.strip()
    return parsed


def parse_review_verdicts(review_text: str) -> tuple[str | None, str | None]:
    implementation_match = re.search(r"implementation_verdict:\s*([a-z_]+)", review_text)
    architecture_match = re.search(r"architecture_verdict:\s*([a-z_]+)", review_text)
    implementation_verdict = implementation_match.group(1) if implementation_match else None
    architecture_verdict = architecture_match.group(1) if architecture_match else None
    return implementation_verdict, architecture_verdict


def validate_architecture_history_document(path: Path) -> list[str]:
    text = read_text(path)
    sections = extract_markdown_sections(text)
    if not sections:
        return ["architecture-history.md must record at least one concrete architecture update entry."]
    errors: list[str] = []
    for section, content in sections.items():
        if is_placeholder_content(content):
            errors.append(f"architecture-history.md entry '{section}' still contains placeholder content.")
    return errors


def validate_adr_directory(adr_dir: Path) -> list[str]:
    markdown_files = sorted(
        path for path in adr_dir.glob("*.md") if path.is_file() and path.name.lower() != "readme.md"
    )
    if not markdown_files:
        return ["adr/ must contain at least one concrete ADR markdown file before architecture approval."]

    errors: list[str] = []
    for path in markdown_files:
        if is_placeholder_content(read_text(path)):
            errors.append(f"{path.relative_to(adr_dir.parent).as_posix()} is empty or still placeholder content.")
    return errors


def validate_dev_record(task_dir: Path, meta: dict[str, Any], project_dir: Path) -> list[str]:
    path = task_dir / "dev.md"
    errors = validate_required_markdown_sections(path, DEV_DOC_REQUIRED_SECTIONS)
    if errors:
        return errors

    sections = extract_markdown_sections(read_text(path))
    compliance = parse_labeled_bullets(sections.get("Compliance Declaration", ""))
    constraints_followed = normalize_string_list(compliance.get("Constraints Followed"))
    architecture_docs = normalize_string_list(compliance.get("Architecture Docs Referenced"))
    exceptions_used = normalize_string_list(compliance.get("Exceptions Used"))

    task_constraint_refs = normalize_string_list(meta.get("constraint_refs"))
    if not constraints_followed:
        errors.append("dev.md must declare non-empty Constraints Followed.")
    elif set(constraints_followed) != set(task_constraint_refs):
        errors.append("dev.md Constraints Followed must match task meta constraint_refs exactly.")

    if not architecture_docs:
        errors.append("dev.md must declare at least one Architecture Docs Referenced entry.")
    else:
        for doc_ref in architecture_docs:
            errors.extend(validate_doc_ref(project_dir, doc_ref))

    approved_exception_ids = set(normalize_string_list(meta.get("exception_ids")))
    lowered_exceptions_used = {value.lower() for value in exceptions_used}
    raw_exceptions_field = compliance.get("Exceptions Used", "").strip()
    if not raw_exceptions_field:
        errors.append("dev.md must declare Exceptions Used and explicitly write none when no exception is used.")
    elif lowered_exceptions_used == {"none"}:
        pass
    else:
        unknown_exceptions = set(exceptions_used) - approved_exception_ids
        if unknown_exceptions:
            errors.append(
                "dev.md Exceptions Used references exceptions not approved on the task: "
                + ", ".join(sorted(unknown_exceptions))
                + "."
            )

    return errors


def validate_architecture_change_request(task_dir: Path) -> list[str]:
    path = task_dir / "architecture-change-request.md"
    text = read_text(path)
    normalized = normalized_doc_content(text)
    template_text = normalized_doc_content(
        "# Architecture Change Request\n\n"
        "Use this file only when development or review discovers a required architecture change, exception, or roadmap adjustment.\n"
    )
    if not normalized or normalized == template_text:
        return ["architecture-change-request.md must be filled in before task-driven update-arch."]
    return validate_required_markdown_sections(path, ARCHITECTURE_CHANGE_REQUEST_REQUIRED_SECTIONS)


def validate_custom_meta_mutations(
    set_items: list[str],
    clear_keys: list[str],
    protected_keys: set[str],
    *,
    label: str,
) -> None:
    attempted_keys: set[str] = set()
    for item in set_items:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item}")
        key, _ = item.split("=", 1)
        attempted_keys.add(key)
    attempted_keys.update(clear_keys)
    forbidden = sorted(key for key in attempted_keys if key in protected_keys)
    if forbidden:
        raise SystemExit(
            f"{label} metadata keys are file-backed or transition-managed and cannot be changed via --set/--clear: "
            + ", ".join(forbidden)
            + "."
        )


def ensure_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    tasks_dir(workspace).mkdir(parents=True, exist_ok=True)
    projects_dir(workspace).mkdir(parents=True, exist_ok=True)

    legacy_path = active_task_path(workspace)
    active_index_path = active_tasks_path(workspace)
    project_path = active_project_path(workspace)

    if not legacy_path.exists() and not active_index_path.exists():
        write_json(legacy_path, empty_active_task_payload())
        write_json(active_index_path, empty_active_tasks_payload())
    elif not active_index_path.exists():
        legacy = read_json(legacy_path) if legacy_path.exists() else empty_active_task_payload()
        write_json(active_index_path, migrate_legacy_active_index(workspace, legacy))
    elif not legacy_path.exists():
        write_json(legacy_path, empty_active_task_payload())

    if not project_path.exists():
        write_json(project_path, empty_active_project_payload())

    if not global_summary_json_path(workspace).exists():
        write_json(global_summary_json_path(workspace), empty_global_summary_payload())
    if not global_summary_md_path(workspace).exists():
        write_text(global_summary_md_path(workspace), "# Global Summary\n\n暂无 project / task 摘要。\n")

    sync_project_state(workspace)
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


def iter_project_meta(workspace: Path) -> list[tuple[Path, dict[str, Any]]]:
    results: list[tuple[Path, dict[str, Any]]] = []
    for project_dir in sorted(projects_dir(workspace).iterdir()):
        if not project_dir.is_dir():
            continue
        meta_path = project_dir / "meta.json"
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
        "worktree_path": meta.get("worktree_path"),
        "updated_at": meta.get("updated_at"),
        "project_id": meta.get("project_id"),
        "module_scope": normalize_string_list(meta.get("module_scope")),
        "architecture_compliance_status": meta.get("architecture_compliance_status"),
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
            }

    return empty_active_task_payload()


def sort_project_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: (
            -parse_iso_timestamp(entry.get("updated_at")),
            entry.get("project_id") or "",
        ),
    )


def project_projection(workspace: Path, meta: dict[str, Any]) -> dict[str, Any]:
    project_id = meta["project_id"]
    return {
        "project_id": project_id,
        "title": meta.get("title"),
        "project_dir": str(project_dir_for_id(workspace, project_id)),
        "status": meta.get("status"),
        "architecture_version": meta.get("architecture_version"),
        "next_action": meta.get("next_action"),
    }


def sync_project_state(workspace: Path, preferred_project_id: str | None = None) -> dict[str, Any]:
    entries = [project_projection(workspace, meta) for _, meta in iter_project_meta(workspace)]
    entries = sort_project_entries(entries)

    project_id = preferred_project_id
    active_path = active_project_path(workspace)
    if not project_id and active_path.exists():
        project_id = read_json(active_path).get("project_id")

    valid_ids = {entry["project_id"] for entry in entries}
    if project_id not in valid_ids:
        project_id = entries[0]["project_id"] if entries else None

    if not project_id:
        payload = empty_active_project_payload()
        write_json(active_path, payload)
        return payload

    for entry in entries:
        if entry["project_id"] == project_id:
            write_json(active_path, entry)
            return entry

    payload = empty_active_project_payload()
    write_json(active_path, payload)
    return payload


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


def load_active_tasks(workspace: Path) -> dict[str, Any]:
    ensure_workspace(workspace)
    return read_json(active_tasks_path(workspace))


def load_active_project(workspace: Path) -> dict[str, Any]:
    ensure_workspace(workspace)
    return read_json(active_project_path(workspace))


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


def resolve_task_id(workspace: Path, task_id: str | None = None) -> str | None:
    if task_id:
        return task_id
    active_index = load_active_tasks(workspace)
    return active_index.get("focus_task_id") or load_active_task(workspace).get("task_id")


def resolve_project_id(workspace: Path, project_id: str | None = None) -> str | None:
    if project_id:
        return project_id
    active_project = load_active_project(workspace)
    return active_project.get("project_id")


def load_meta(workspace: Path, task_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    resolved_task_id = resolve_task_id(workspace, task_id)
    if not resolved_task_id:
        raise FileNotFoundError("No focus task found.")
    task_dir = task_dir_for_id(workspace, resolved_task_id)
    meta_path = task_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for task {resolved_task_id}")
    return meta_path, read_json(meta_path)


def load_project_meta(workspace: Path, project_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    resolved_project_id = resolve_project_id(workspace, project_id)
    if not resolved_project_id:
        raise FileNotFoundError("No active project found.")
    project_dir = project_dir_for_id(workspace, resolved_project_id)
    meta_path = project_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for project {resolved_project_id}")
    return meta_path, read_json(meta_path)


def init_project_meta(project_id: str, title: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "project_id": project_id,
        "title": title,
        "status": "architecting",
        "created_at": timestamp,
        "updated_at": timestamp,
        "architecture_version": 1,
        "current_step": "draft initial architecture baseline",
        "next_action": "update-arch",
        "approved_at": None,
        "approved_by": None,
        "architect_agent_name": "Architect",
        "architect_agent_id": None,
        "architect_agent_status": None,
        "changed_modules": [],
        "changed_constraint_refs": [],
    }


def init_meta(
    task_id: str,
    title: str,
    project_id: str,
    architecture_version: int,
    module_scope: list[str],
    constraint_refs: list[str],
    exception_ids: list[str],
    worktree_path: str,
    worktree_branch: str,
    worktree_base_ref: str,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "task_id": task_id,
        "title": title,
        "project_id": project_id,
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
        "worktree_path": worktree_path,
        "worktree_branch": worktree_branch,
        "worktree_base_ref": worktree_base_ref,
        "global_summary_updated_at": None,
        "architecture_version": architecture_version,
        "module_scope": unique_preserve_order(module_scope),
        "constraint_refs": unique_preserve_order(constraint_refs),
        "exception_ids": unique_preserve_order(exception_ids),
        "architecture_compliance_status": "pending",
    }


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


def task_file_names() -> list[str]:
    return [
        "request.md",
        "plan.md",
        "plan-history.md",
        "dev.md",
        "change-summary.md",
        "review.md",
        "architecture-change-request.md",
        "summary.md",
    ]


def create_project_files(project_dir: Path, title: str, request_text: str, project_id: str) -> None:
    timestamp = now_iso()
    write_text(
        project_dir / "request.md",
        f"# Project Request\n\n- Project ID: `{project_id}`\n- Title: {title}\n- Created At: {timestamp}\n\n## Request\n\n{request_text.strip()}\n",
    )
    write_text(
        project_dir / "architecture.md",
        "# Architecture\n\n"
        "Overall system architecture design. Fill in this file before any task plan is approved.\n\n"
        "## System Description\n\nDescribe what the system is, what it does, and who it serves.\n\n"
        "## Tech Stack\n\nList the primary languages, frameworks, storage systems, infrastructure, and runtime dependencies.\n\n"
        "## Overall Architecture\n\nDescribe the top-level architecture shape and the major subsystems.\n\n"
        "## Runtime Flow And Data Flow\n\nExplain the key runtime flows, request flows, background flows, and data movement between modules.\n\n"
        "## Module Split\n\nList the major modules and summarize what each one owns.\n\n"
        "## Cross-Module Constraints And Relationships\n\nDescribe the most important relationships, dependency directions, and restrictions between modules.\n\n"
        "## Schema And Data Structure Design\n\nDescribe the key schemas, entities, messages, and shared data structures.\n\n"
        "## Project Directory Layout\n\nDescribe the intended repository / package / service layout.\n\n"
        "## Key Design Decisions\n\nRecord the critical architecture decisions that downstream tasks must follow.\n",
    )
    write_text(
        project_dir / "module-map.md",
        "# Module Map\n\n"
        "Implementation-ready module design. Use this file as the top-level module index.\n\n"
        "If the project gets large, keep the summary here and split detailed module specifications into separate markdown files, for example `modules/<module-id>.md`.\n\n"
        "## Module Index\n\n"
        "| Module ID | Responsibility | Allowed Dependencies | Forbidden Couplings | Detailed Spec |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| example-module | Fill in the module contract before starting tasks. | none | tbd | add a module spec link when available |\n\n"
        "## Detailed Design Expectations\n\n"
        "Each module definition should be implementation-ready and cover at least:\n\n"
        "- responsibilities and owned behaviors\n"
        "- boundaries and non-responsibilities\n"
        "- upstream and downstream dependencies\n"
        "- key interfaces, schema, and data contracts\n"
        "- failure handling and operational constraints\n"
        "- testing expectations for the module\n",
    )
    write_text(
        project_dir / "standards.md",
        "# Standards\n\n"
        "Code standards, testing requirements, error handling, logging, and interface contracts.\n\n"
        "## Code Standards\n\nDefine coding conventions and readability expectations.\n\n"
        "## Testing Requirements\n\nDefine the minimum test bar for each module or task.\n\n"
        "## Error Handling\n\nDefine error propagation, retries, and user-facing failures.\n\n"
        "## Logging And Observability\n\nDefine logging, tracing, and monitoring expectations.\n\n"
        "## API And Interface Contracts\n\nDefine serialization, compatibility, and interface guarantees.\n",
    )
    write_text(
        project_dir / "roadmap.md",
        "# Roadmap\n\n"
        "Complete development plan for the approved architecture baseline.\n\n"
        "## Delivery Order\n\nList the preferred module implementation order.\n\n"
        "## Suggested Task Breakdown\n\nList the recommended task slices under the current architecture baseline.\n",
    )
    write_json(
        project_dir / "constraints.json",
        {
            "architecture_version": 1,
            "modules": [],
            "constraints": [],
            "exceptions": [],
            "roadmap": {
                "open_module_ids": [],
                "recommended_task_order": [],
            },
        },
    )
    write_text(
        project_dir / "architecture-history.md",
        "# Architecture History\n\n"
        "## Version 1\n\n"
        "Pending.\n",
    )
    write_text(
        project_dir / "summary.md",
        "# Project Summary\n\n"
        "Project-level summary only. This file records the latest architecture baseline, changed modules, and open architecture decisions.\n",
    )
    write_text(
        project_dir / "adr" / "README.md",
        "# ADR\n\nStore architecture decisions and approved exceptions here. Changes must be explicit and auditable.\n",
    )


def plan_template() -> str:
    lines = ["# Plan", ""]
    for section in REQUIRED_PLAN_SECTIONS:
        lines.extend([f"## {section}", "", "Pending.", ""])
    return "\n".join(lines).rstrip() + "\n"


def create_task_files(task_dir: Path, title: str, request_text: str, task_id: str) -> None:
    timestamp = now_iso()
    write_text(
        task_dir / "request.md",
        f"# Request\n\n- Task ID: `{task_id}`\n- Title: {title}\n- Created At: {timestamp}\n\n## Request\n\n{request_text.strip()}\n",
    )
    write_text(task_dir / "plan.md", plan_template())
    write_text(task_dir / "plan-history.md", "# Plan History\n")
    write_text(
        task_dir / "dev.md",
        "# Development Log\n\n"
        "## Compliance Declaration\n\n"
        "- Constraints Followed: \n"
        "- Architecture Docs Referenced: \n"
        "- Exceptions Used: none\n\n"
        "## Work Log\n\nPending.\n",
    )
    write_text(
        task_dir / "change-summary.md",
        "# Change Summary\n\nNot generated yet.\n",
    )
    write_text(
        task_dir / "review.md",
        "# Review\n\n"
        "## Verdicts\n\n"
        "- implementation_verdict: pending\n"
        "- architecture_verdict: pending\n\n"
        "## Findings\n\nReview not run yet.\n",
    )
    write_text(
        task_dir / "architecture-change-request.md",
        "# Architecture Change Request\n\n"
        "Use this file only when development or review discovers a required architecture change, exception, or roadmap adjustment.\n\n"
        "## Context\n\n"
        "Pending.\n\n"
        "## Requested Change\n\n"
        "Pending.\n\n"
        "## Why Current Architecture Blocks This Task\n\n"
        "Pending.\n\n"
        "## Impacted Modules Or Constraints\n\n"
        "Pending.\n",
    )
    write_text(
        task_dir / "summary.md",
        "# Summary\n\n"
        "This is the task-local summary for the current task. "
        "It records the latest task snapshot, architecture binding, key structures, config notes, and pitfalls for this task only. "
        "Use `DevFlowWorkspace/global-summary.md` for workspace-level shared context.\n",
    )


def constraints_path_for_project_dir(project_dir: Path) -> Path:
    return project_dir / "constraints.json"


def load_constraints_payload(project_dir: Path) -> dict[str, Any]:
    path = constraints_path_for_project_dir(project_dir)
    if not path.exists():
        raise FileNotFoundError(f"Missing constraints.json for project {project_dir.name}")
    return read_json(path)


def module_records(constraints_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = constraints_payload.get("modules")
    return records if isinstance(records, list) else []


def constraint_records(constraints_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = constraints_payload.get("constraints")
    return records if isinstance(records, list) else []


def exception_records(constraints_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = constraints_payload.get("exceptions")
    return records if isinstance(records, list) else []


def roadmap_payload(constraints_payload: dict[str, Any]) -> dict[str, Any]:
    payload = constraints_payload.get("roadmap")
    return payload if isinstance(payload, dict) else {}


def module_ids(constraints_payload: dict[str, Any]) -> set[str]:
    return {str(record.get("id")).strip() for record in module_records(constraints_payload) if str(record.get("id")).strip()}


def constraint_ids(constraints_payload: dict[str, Any]) -> set[str]:
    return {str(record.get("id")).strip() for record in constraint_records(constraints_payload) if str(record.get("id")).strip()}


def approved_exception_ids(constraints_payload: dict[str, Any]) -> set[str]:
    approved: set[str] = set()
    for record in exception_records(constraints_payload):
        exception_id = str(record.get("id")).strip()
        if exception_id and str(record.get("status")).strip().lower() == "approved":
            approved.add(exception_id)
    return approved


def open_module_ids(constraints_payload: dict[str, Any]) -> set[str]:
    roadmap = roadmap_payload(constraints_payload)
    values = roadmap.get("open_module_ids")
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def validate_constraints_payload(
    constraints_payload: dict[str, Any],
    project_meta: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    architecture_version = constraints_payload.get("architecture_version")
    if not isinstance(architecture_version, int):
        errors.append("constraints.json must define integer architecture_version.")
    if project_meta and architecture_version != project_meta.get("architecture_version"):
        errors.append("constraints.json architecture_version must match project meta.")

    module_id_list = [str(record.get("id")).strip() for record in module_records(constraints_payload) if str(record.get("id")).strip()]
    if not module_id_list:
        errors.append("constraints.json must define at least one module.")
    elif len(set(module_id_list)) != len(module_id_list):
        errors.append("constraints.json module ids must be unique.")

    constraint_id_list = [str(record.get("id")).strip() for record in constraint_records(constraints_payload) if str(record.get("id")).strip()]
    if not constraint_id_list:
        errors.append("constraints.json must define at least one constraint.")
    elif len(set(constraint_id_list)) != len(constraint_id_list):
        errors.append("constraints.json constraint ids must be unique.")

    exception_id_list = [str(record.get("id")).strip() for record in exception_records(constraints_payload) if str(record.get("id")).strip()]
    if len(set(exception_id_list)) != len(exception_id_list):
        errors.append("constraints.json exception ids must be unique.")

    valid_module_ids = set(module_id_list)
    valid_constraint_ids = set(constraint_id_list)
    roadmap_open_ids = open_module_ids(constraints_payload)
    unknown_open_ids = roadmap_open_ids - valid_module_ids
    if unknown_open_ids:
        errors.append(f"roadmap.open_module_ids references unknown modules: {', '.join(sorted(unknown_open_ids))}.")

    for record in module_records(constraints_payload):
        depends_on = set(normalize_string_list(record.get("depends_on")))
        unknown_dependencies = depends_on - valid_module_ids
        if unknown_dependencies:
            errors.append(
                f"Module {record.get('id')} depends_on unknown modules: {', '.join(sorted(unknown_dependencies))}."
            )
        referenced_constraints = set(normalize_string_list(record.get("constraint_refs")))
        unknown_constraints = referenced_constraints - valid_constraint_ids
        if unknown_constraints:
            errors.append(
                f"Module {record.get('id')} references unknown constraint ids: {', '.join(sorted(unknown_constraints))}."
            )
        doc_refs = normalize_string_list(record.get("doc_refs"))
        if not doc_refs:
            errors.append(f"Module {record.get('id')} must declare non-empty doc_refs.")
        elif project_dir is not None:
            for doc_ref in doc_refs:
                errors.extend(validate_doc_ref(project_dir, doc_ref))

    for record in exception_records(constraints_payload):
        referenced_constraints = set(normalize_string_list(record.get("constraint_refs")))
        unknown_constraints = referenced_constraints - valid_constraint_ids
        if unknown_constraints:
            errors.append(
                f"Exception {record.get('id')} references unknown constraint ids: {', '.join(sorted(unknown_constraints))}."
            )
        scoped_modules = set(normalize_string_list(record.get("module_scope")))
        unknown_modules = scoped_modules - valid_module_ids
        if unknown_modules:
            errors.append(
                f"Exception {record.get('id')} references unknown module ids: {', '.join(sorted(unknown_modules))}."
            )

    return errors


def plan_missing_sections(plan_text: str) -> list[str]:
    missing: list[str] = []
    for section in REQUIRED_PLAN_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\s*$"
        if not re.search(pattern, plan_text, flags=re.MULTILINE):
            missing.append(section)
    return missing


def validate_plan_sections(plan_path: Path) -> list[str]:
    text = read_text(plan_path)
    sections = extract_markdown_sections(text)
    errors: list[str] = []
    for section in REQUIRED_PLAN_SECTIONS:
        if section not in sections:
            errors.append(f"plan.md is missing required section: {section}.")
            continue
        if is_placeholder_content(sections[section]):
            errors.append(f"plan.md section '{section}' still contains placeholder content.")
    return errors


def validate_project_documents(project_dir: Path) -> list[str]:
    errors: list[str] = []
    for filename, required_sections in PROJECT_DOC_REQUIRED_SECTIONS.items():
        errors.extend(validate_required_markdown_sections(project_dir / filename, required_sections))
    errors.extend(validate_module_map_document(project_dir / "module-map.md"))
    return errors


def validate_project_ready(workspace: Path, project_meta: dict[str, Any]) -> list[str]:
    project_dir = project_dir_for_id(workspace, project_meta["project_id"])
    errors: list[str] = []
    for filename in PROJECT_DOC_FILENAMES:
        if not (project_dir / filename).exists():
            errors.append(f"Missing project artifact: {filename}.")

    adr_dir = project_dir / "adr"
    if not adr_dir.exists():
        errors.append("Missing adr/ directory.")

    if errors:
        return errors

    try:
        constraints_payload = load_constraints_payload(project_dir)
    except FileNotFoundError as error:
        return [str(error)]

    errors.extend(validate_project_documents(project_dir))
    errors.extend(validate_architecture_history_document(project_dir / "architecture-history.md"))
    errors.extend(validate_adr_directory(adr_dir))
    errors.extend(validate_constraints_payload(constraints_payload, project_meta, project_dir=project_dir))
    return errors


def validate_task_architecture_binding(
    workspace: Path,
    meta: dict[str, Any],
    *,
    require_project_approved: bool = False,
    require_open_modules: bool = False,
) -> list[str]:
    errors: list[str] = []

    project_id = meta.get("project_id")
    if not project_id:
        return ["Task meta is missing project_id."]

    try:
        _, project_meta = load_project_meta(workspace, str(project_id))
    except FileNotFoundError as error:
        return [str(error)]

    project_status = project_meta.get("status")
    if require_project_approved and project_status != "architecture_approved":
        errors.append("Project architecture is not approved.")

    project_dir = project_dir_for_id(workspace, str(project_id))
    try:
        constraints_payload = load_constraints_payload(project_dir)
    except FileNotFoundError as error:
        return [str(error)]

    errors.extend(validate_constraints_payload(constraints_payload, project_meta, project_dir=project_dir))
    if errors:
        return errors

    architecture_version = meta.get("architecture_version")
    if not isinstance(architecture_version, int):
        errors.append("Task meta must define integer architecture_version.")
    elif architecture_version > int(project_meta.get("architecture_version", 0)):
        errors.append("Task architecture_version cannot be ahead of the project architecture_version.")

    valid_module_ids = module_ids(constraints_payload)
    valid_constraint_ids = constraint_ids(constraints_payload)
    valid_exception_ids = approved_exception_ids(constraints_payload)
    open_modules = open_module_ids(constraints_payload)

    module_scope = normalize_string_list(meta.get("module_scope"))
    if not module_scope:
        errors.append("Task meta must define non-empty module_scope.")
    else:
        unknown_modules = set(module_scope) - valid_module_ids
        if unknown_modules:
            errors.append(f"Task module_scope references unknown modules: {', '.join(sorted(unknown_modules))}.")
        if require_open_modules:
            if not open_modules:
                errors.append("constraints.json roadmap.open_module_ids is empty; no modules are open for start-plan.")
            else:
                closed_modules = set(module_scope) - open_modules
                if closed_modules:
                    errors.append(
                        f"Task module_scope references modules not open in roadmap.open_module_ids: {', '.join(sorted(closed_modules))}."
                    )

    constraint_refs = normalize_string_list(meta.get("constraint_refs"))
    if not constraint_refs:
        errors.append("Task meta must define non-empty constraint_refs.")
    else:
        unknown_constraints = set(constraint_refs) - valid_constraint_ids
        if unknown_constraints:
            errors.append(
                f"Task constraint_refs reference unknown constraints: {', '.join(sorted(unknown_constraints))}."
            )

    exception_ids = normalize_string_list(meta.get("exception_ids"))
    unknown_exceptions = set(exception_ids) - valid_exception_ids
    if unknown_exceptions:
        errors.append(
            f"Task exception_ids reference exceptions that are not approved: {', '.join(sorted(unknown_exceptions))}."
        )

    compliance_status = meta.get("architecture_compliance_status")
    if compliance_status not in ARCHITECTURE_COMPLIANCE_STATUS:
        errors.append(
            "Task architecture_compliance_status must be one of: "
            + ", ".join(ARCHITECTURE_COMPLIANCE_STATUS)
            + "."
        )

    return errors


def blocked_for_architecture(meta: dict[str, Any]) -> bool:
    return meta.get("architecture_compliance_status") in {"deviation", "needs_architect_decision"}


def allowed_actions_for_project(project_meta: dict[str, Any] | None) -> list[str]:
    if project_meta is None:
        return ["start-project"]

    status = project_meta.get("status")
    if status == "architecting":
        return ["update-arch", "approve-arch", "resume"]
    if status == "architecture_approved":
        return ["update-arch", "start-plan", "resume"]
    return ["resume"]


def allowed_actions_for_task(meta: dict[str, Any] | None, project_meta: dict[str, Any] | None) -> list[str]:
    if meta is None:
        if project_meta and project_meta.get("status") == "architecture_approved":
            return ["start-plan", "resume"]
        return ["resume"]

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
        return ["start-plan", "resume"]
    return ["resume"]


def evaluate_gate(
    action: str,
    workspace: Path,
    meta: dict[str, Any] | None = None,
    task_id: str | None = None,
    project_meta: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> GateResult:
    try:
        active_project_meta = project_meta
        active_project_id = project_id
        if active_project_meta is None:
            try:
                _, active_project_meta = load_project_meta(workspace, project_id)
                active_project_id = active_project_meta.get("project_id")
            except FileNotFoundError:
                active_project_meta = None
                active_project_id = None
    except FileNotFoundError:
        active_project_meta = None
        active_project_id = None

    if action == "start-project":
        existing_projects = iter_project_meta(workspace)
        allowed = not existing_projects
        reason = "Project bootstrap allowed." if allowed else "A project already exists; use update-arch instead."
        return GateResult(
            action,
            allowed,
            reason,
            active_project_meta.get("status") if active_project_meta else None,
            active_project_meta.get("next_action") if active_project_meta else None,
            ["start-project"] if allowed else allowed_actions_for_project(active_project_meta),
            None,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action in {"update-arch", "approve-arch", "start-plan"} and active_project_meta is None:
        return GateResult(
            action,
            False,
            "No active project found.",
            None,
            None,
            ["start-project"],
            None,
            None,
            None,
        )

    if action == "update-arch":
        return GateResult(
            action,
            True,
            "Architecture update allowed.",
            active_project_meta.get("status"),
            active_project_meta.get("next_action"),
            allowed_actions_for_project(active_project_meta),
            None,
            active_project_id,
            active_project_meta.get("status"),
        )

    if action == "approve-arch":
        errors = validate_project_ready(workspace, active_project_meta)
        allowed = active_project_meta.get("status") == "architecting" and not errors
        reason = "Architecture approval allowed." if allowed else "; ".join(errors) or "Architecture approval requires architecting status."
        return GateResult(
            action,
            allowed,
            reason,
            active_project_meta.get("status"),
            active_project_meta.get("next_action"),
            allowed_actions_for_project(active_project_meta),
            None,
            active_project_id,
            active_project_meta.get("status"),
        )

    if action == "start-plan":
        allowed = active_project_meta.get("status") == "architecture_approved"
        reason = (
            "Task start allowed under approved architecture."
            if allowed
            else "start-plan requires an approved project architecture."
        )
        return GateResult(
            action,
            allowed,
            reason,
            active_project_meta.get("status"),
            active_project_meta.get("next_action"),
            allowed_actions_for_project(active_project_meta),
            None,
            active_project_id,
            active_project_meta.get("status"),
        )

    if meta is None or not task_id:
        return GateResult(
            action,
            False,
            "No target task found.",
            None,
            None,
            allowed_actions_for_task(None, active_project_meta),
            None,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    status = meta.get("status")
    allowed_actions = allowed_actions_for_task(meta, active_project_meta)
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
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action == "approve-plan":
        errors = validate_task_architecture_binding(
            workspace,
            meta,
            require_project_approved=True,
            require_open_modules=False,
        )
        errors.extend(validate_plan_sections(task_dir_for_id(workspace, task_id) / "plan.md"))
        allowed = status == "planning" and not errors
        reason = "Plan approval allowed." if allowed else "; ".join(errors) or "Plan approval requires planning status."
        return GateResult(
            action,
            allowed,
            reason,
            status,
            next_action,
            allowed_actions,
            task_id,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action == "dev":
        errors = validate_task_architecture_binding(workspace, meta, require_project_approved=True)
        if blocked_for_architecture(meta) and meta.get("architecture_compliance_status") != "approved_exception":
            errors.append("Task requires an Architect decision before development may continue.")
        allowed = status in {"plan_approved", "developing"} and not errors
        reason = "Development allowed." if allowed else "; ".join(errors) or "Development requires an approved plan."
        return GateResult(
            action,
            allowed,
            reason,
            status,
            next_action,
            allowed_actions,
            task_id,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action == "review":
        errors = validate_task_architecture_binding(workspace, meta, require_project_approved=True)
        if blocked_for_architecture(meta):
            errors.append("Task requires an Architect decision before review may proceed.")
        project_dir = project_dir_for_id(workspace, str(meta.get("project_id")))
        errors.extend(validate_dev_record(task_dir_for_id(workspace, task_id), meta, project_dir))
        allowed = status == "developing" and next_action == "review" and not errors
        reason = (
            "Review allowed."
            if allowed
            else "; ".join(errors) or "Review requires developing status with next_action=review."
        )
        return GateResult(
            action,
            allowed,
            reason,
            status,
            next_action,
            allowed_actions,
            task_id,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action == "done":
        architecture_ok = meta.get("architecture_compliance_status") in {"compliant", "approved_exception"}
        allowed = status == "developing" and next_action == "done" and meta.get("last_review_verdict") == "pass" and architecture_ok
        if allowed:
            reason = "Done allowed."
        else:
            reason = "Done requires pass review plus compliant architecture status or approved exception."
        return GateResult(
            action,
            allowed,
            reason,
            status,
            next_action,
            allowed_actions,
            task_id,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

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
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    if action == "resume":
        return GateResult(
            action,
            True,
            "Resume allowed.",
            status,
            next_action,
            allowed_actions,
            task_id,
            active_project_id,
            active_project_meta.get("status") if active_project_meta else None,
        )

    return GateResult(
        action,
        False,
        f"Unknown action: {action}",
        status,
        next_action,
        allowed_actions,
        task_id,
        active_project_id,
        active_project_meta.get("status") if active_project_meta else None,
    )


def build_project_summary_entry(project_dir: Path) -> dict[str, Any]:
    meta = read_json(project_dir / "meta.json")
    request_text = read_text(project_dir / "request.md")
    architecture_text = read_text(project_dir / "architecture.md")
    module_map_text = read_text(project_dir / "module-map.md")
    standards_text = read_text(project_dir / "standards.md")
    roadmap_text = read_text(project_dir / "roadmap.md")
    history_text = read_text(project_dir / "architecture-history.md")
    constraints_payload = load_constraints_payload(project_dir)
    sources = [request_text, architecture_text, module_map_text, standards_text, roadmap_text, history_text]

    pending_exceptions = 0
    approved_exceptions = 0
    for record in exception_records(constraints_payload):
        if str(record.get("status")).strip().lower() == "approved":
            approved_exceptions += 1
        else:
            pending_exceptions += 1

    return {
        "project_id": meta.get("project_id"),
        "title": meta.get("title"),
        "status": meta.get("status"),
        "next_action": meta.get("next_action"),
        "architecture_version": meta.get("architecture_version"),
        "updated_at": meta.get("updated_at"),
        "approved_at": meta.get("approved_at"),
        "changed_modules": normalize_string_list(meta.get("changed_modules")),
        "changed_constraint_refs": normalize_string_list(meta.get("changed_constraint_refs")),
        "module_count": len(module_records(constraints_payload)),
        "constraint_count": len(constraint_records(constraints_payload)),
        "approved_exception_count": approved_exceptions,
        "pending_exception_count": pending_exceptions,
        "overview": first_meaningful_line(architecture_text, roadmap_text, request_text, standards_text),
        "key_structures": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_structures"]),
        "key_config": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_config"]),
        "pitfalls": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["pitfalls"]),
        "cross_task_notes": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["cross_task_notes"]),
    }


def render_project_summary(project_dir: Path) -> str:
    entry = build_project_summary_entry(project_dir)
    changed_modules = ", ".join(entry["changed_modules"]) if entry["changed_modules"] else "n/a"
    changed_constraints = ", ".join(entry["changed_constraint_refs"]) if entry["changed_constraint_refs"] else "n/a"
    return "\n".join(
        [
            "# Project Summary",
            "",
            "Project-level summary only. This file records the latest architecture baseline, changed modules, and open architecture decisions.",
            "",
            f"- Project ID: `{entry['project_id']}`",
            f"- Title: {entry['title']}",
            f"- Project Status: `{entry['status']}`",
            f"- Next Action: `{entry['next_action'] or 'n/a'}`",
            f"- Architecture Version: `{entry['architecture_version']}`",
            f"- Changed Modules: {changed_modules}",
            f"- Changed Constraint Refs: {changed_constraints}",
            f"- Approved Exceptions: {entry['approved_exception_count']}",
            f"- Pending Exceptions: {entry['pending_exception_count']}",
            f"- Last Updated: {entry['updated_at'] or 'n/a'}",
            "",
            "## Architecture Overview",
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


def write_project_summary(project_dir: Path) -> Path:
    summary_path = project_dir / "summary.md"
    write_text(summary_path, render_project_summary(project_dir))
    return summary_path


def build_task_summary_entry(task_dir: Path) -> dict[str, Any]:
    meta = read_json(task_dir / "meta.json")
    request_text = read_text(task_dir / "request.md")
    plan_text = read_text(task_dir / "plan.md")
    dev_text = read_text(task_dir / "dev.md")
    review_text = read_text(task_dir / "review.md")
    change_summary_text = read_text(task_dir / "change-summary.md")
    architecture_change_request_text = read_text(task_dir / "architecture-change-request.md")
    sources = [request_text, plan_text, dev_text, review_text, change_summary_text, architecture_change_request_text]

    return {
        "task_id": meta.get("task_id"),
        "title": meta.get("title"),
        "status": meta.get("status"),
        "next_action": meta.get("next_action"),
        "is_blocked": meta.get("is_blocked", False),
        "block_reason": meta.get("block_reason"),
        "updated_at": meta.get("updated_at"),
        "worktree_path": meta.get("worktree_path"),
        "worktree_branch": meta.get("worktree_branch"),
        "worktree_base_ref": meta.get("worktree_base_ref"),
        "project_id": meta.get("project_id"),
        "architecture_version": meta.get("architecture_version"),
        "module_scope": normalize_string_list(meta.get("module_scope")),
        "constraint_refs": normalize_string_list(meta.get("constraint_refs")),
        "exception_ids": normalize_string_list(meta.get("exception_ids")),
        "architecture_compliance_status": meta.get("architecture_compliance_status"),
        "overview": first_meaningful_line(dev_text, plan_text, request_text, review_text, change_summary_text),
        "key_structures": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_structures"]),
        "key_config": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["key_config"]),
        "pitfalls": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["pitfalls"]),
        "cross_task_notes": extract_keyword_lines(sources, SUMMARY_SECTION_KEYWORDS["cross_task_notes"]),
    }


def render_task_summary(task_dir: Path) -> str:
    entry = build_task_summary_entry(task_dir)
    module_scope = ", ".join(entry["module_scope"]) if entry["module_scope"] else "n/a"
    constraint_refs = ", ".join(entry["constraint_refs"]) if entry["constraint_refs"] else "n/a"
    exception_ids = ", ".join(entry["exception_ids"]) if entry["exception_ids"] else "n/a"
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
            f"- Blocked: {'yes' if entry['is_blocked'] else 'no'}",
            f"- Block Reason: {entry['block_reason'] or 'n/a'}",
            f"- Project ID: `{entry['project_id'] or 'n/a'}`",
            f"- Architecture Version: `{entry['architecture_version'] or 'n/a'}`",
            f"- Module Scope: {module_scope}",
            f"- Constraint Refs: {constraint_refs}",
            f"- Exception IDs: {exception_ids}",
            f"- Architecture Compliance: `{entry['architecture_compliance_status'] or 'n/a'}`",
            f"- Worktree Path: `{entry['worktree_path'] or 'n/a'}`",
            f"- Worktree Branch: `{entry['worktree_branch'] or 'n/a'}`",
            f"- Worktree Base Ref: `{entry['worktree_base_ref'] or 'n/a'}`",
            f"- Last Updated: {entry['updated_at'] or 'n/a'}",
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


def build_global_summary_payload(workspace: Path) -> dict[str, Any]:
    active_index = load_active_tasks(workspace)
    active_project = load_active_project(workspace)
    task_entries: list[dict[str, Any]] = []
    done_task_count = 0
    needs_architect_count = 0
    for _, meta in iter_task_meta(workspace):
        task_dir = task_dir_for_id(workspace, meta["task_id"])
        entry = build_task_summary_entry(task_dir)
        task_entries.append(entry)
        if meta.get("status") == "done":
            done_task_count += 1
        if meta.get("architecture_compliance_status") == "needs_architect_decision":
            needs_architect_count += 1

    task_entries.sort(
        key=lambda entry: (-parse_iso_timestamp(entry.get("updated_at")), entry.get("task_id") or "")
    )

    project_entry = None
    if active_project.get("project_id"):
        project_entry = build_project_summary_entry(project_dir_for_id(workspace, active_project["project_id"]))

    return {
        "updated_at": now_iso(),
        "focus_task_id": active_index.get("focus_task_id"),
        "active_project_id": active_project.get("project_id"),
        "active_task_count": len(active_index.get("tasks", [])),
        "done_task_count": done_task_count,
        "needs_architect_count": needs_architect_count,
        "project": project_entry,
        "tasks": task_entries,
    }


def render_global_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# Global Summary",
        "",
        f"- Updated At: {payload.get('updated_at') or 'n/a'}",
        f"- Active Project: `{payload.get('active_project_id') or 'n/a'}`",
        f"- Focus Task: `{payload.get('focus_task_id') or 'n/a'}`",
        f"- Active Tasks: {payload.get('active_task_count', 0)}",
        f"- Done Tasks: {payload.get('done_task_count', 0)}",
        f"- Needs Architect: {payload.get('needs_architect_count', 0)}",
        "",
        "新 task 在规划或开发前应先阅读本文件，优先复用已有结论并避开已知坑。",
        "",
    ]

    project = payload.get("project")
    if project:
        changed_modules = ", ".join(project.get("changed_modules") or []) or "n/a"
        lines.extend(
            [
                f"## {project['project_id']} · {project['title']}",
                "",
                f"- Project Status: `{project['status']}`",
                f"- Next Action: `{project['next_action'] or 'n/a'}`",
                f"- Architecture Version: `{project['architecture_version']}`",
                f"- Changed Modules: {changed_modules}",
                f"- Approved Exceptions: {project['approved_exception_count']}",
                f"- Pending Exceptions: {project['pending_exception_count']}",
                f"- Updated At: {project['updated_at'] or 'n/a'}",
                "",
                project["overview"],
                "",
                "### Key Structures / Interfaces / File Contracts",
                "",
                format_bullet_lines(project["key_structures"], "暂无明确记录。"),
                "",
                "### Key Config / Environment",
                "",
                format_bullet_lines(project["key_config"], "暂无明确记录。"),
                "",
                "### Pitfalls / Bugs / Mistakes",
                "",
                format_bullet_lines(project["pitfalls"], "暂无明确记录。"),
                "",
                "### Cross-Task Notes",
                "",
                format_bullet_lines(project["cross_task_notes"], "暂无明确记录。"),
                "",
            ]
        )

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
                f"- Project ID: `{entry['project_id'] or 'n/a'}`",
                f"- Architecture Version: `{entry['architecture_version'] or 'n/a'}`",
                f"- Module Scope: {', '.join(entry['module_scope']) or 'n/a'}",
                f"- Constraint Refs: {', '.join(entry['constraint_refs']) or 'n/a'}",
                f"- Architecture Compliance: `{entry['architecture_compliance_status'] or 'n/a'}`",
                f"- Worktree: `{entry['worktree_path'] or 'n/a'}`",
                f"- Branch: `{entry['worktree_branch'] or 'n/a'}`",
                f"- Updated At: {entry['updated_at'] or 'n/a'}",
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

    return "\n".join(lines)


def update_task_global_summary_timestamp(task_dir: Path, timestamp: str) -> None:
    meta_path = task_dir / "meta.json"
    meta = read_json(meta_path)
    meta["global_summary_updated_at"] = timestamp
    write_json(meta_path, meta)


def write_global_summary(workspace: Path, touched_task_id: str | None = None) -> tuple[Path, Path]:
    payload = build_global_summary_payload(workspace)
    write_json(global_summary_json_path(workspace), payload)
    write_text(global_summary_md_path(workspace), render_global_summary(payload))
    if touched_task_id:
        task_dir = task_dir_for_id(workspace, touched_task_id)
        meta_path = task_dir / "meta.json"
        if meta_path.exists():
            update_task_global_summary_timestamp(task_dir, payload["updated_at"])
    return global_summary_json_path(workspace), global_summary_md_path(workspace)


def scan_architecture_drift(workspace: Path, project_meta: dict[str, Any]) -> list[str]:
    changed_modules = set(normalize_string_list(project_meta.get("changed_modules")))
    changed_constraints = set(normalize_string_list(project_meta.get("changed_constraint_refs")))
    if not changed_modules and not changed_constraints:
        return []

    affected_task_ids: list[str] = []
    for meta_path, meta in iter_task_meta(workspace):
        if meta.get("status") == "done":
            continue
        if meta.get("project_id") != project_meta.get("project_id"):
            continue
        if meta.get("architecture_compliance_status") == "approved_exception":
            continue

        module_scope = set(normalize_string_list(meta.get("module_scope")))
        constraint_refs = set(normalize_string_list(meta.get("constraint_refs")))
        if not (module_scope & changed_modules or constraint_refs & changed_constraints):
            continue

        meta["is_blocked"] = True
        meta["block_reason"] = "Architecture drift requires Architect review."
        meta["architecture_compliance_status"] = "needs_architect_decision"
        meta["updated_at"] = now_iso()
        write_json(meta_path, meta)
        write_task_summary(meta_path.parent)
        affected_task_ids.append(str(meta.get("task_id")))

    return affected_task_ids
