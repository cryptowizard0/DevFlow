#!/usr/bin/env python3
"""Update DevFlow project metadata through explicit architecture transitions or key assignments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    load_project_meta,
    load_meta,
    now_iso,
    normalize_string_list,
    PROJECT_META_PROTECTED_KEYS,
    scan_architecture_drift,
    sync_project_state,
    sync_workspace_state,
    validate_architecture_change_request,
    validate_custom_meta_mutations,
    validate_project_ready,
    write_global_summary,
    write_json,
    write_project_summary,
    write_task_summary,
    task_dir_for_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update DevFlow project meta.json.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--project-id", help="Project ID. Defaults to the active project.")
    parser.add_argument(
        "--transition",
        choices=["arch-updated", "arch-approved"],
        help="Named architecture transition to apply before custom fields.",
    )
    parser.add_argument("--restatement", action="store_true", help="Record update-arch as a non-semantic documentation restatement.")
    parser.add_argument(
        "--source-task-id",
        help="Task ID whose architecture-change-request.md justifies this architecture update. Required for semantic updates on an already approved project.",
    )
    parser.add_argument("--changed-module", action="append", default=[], help="Changed module ID. May be repeated or comma-separated.")
    parser.add_argument("--changed-constraint-ref", action="append", default=[], help="Changed constraint ID. May be repeated or comma-separated.")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Set a JSON-like value on meta.json. VALUE is parsed as JSON when possible. File-backed and transition-managed keys are protected.")
    parser.add_argument("--clear", action="append", default=[], metavar="KEY", help="Clear a key by setting it to null. File-backed and transition-managed keys are protected.")
    return parser.parse_args()


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_transition(meta: dict[str, Any], transition: str, restatement: bool) -> None:
    if transition == "arch-updated":
        if not restatement:
            meta["architecture_version"] = int(meta.get("architecture_version", 0)) + 1
        meta["status"] = "architecting"
        meta["approved_at"] = None
        meta["approved_by"] = None
        meta["next_action"] = "approve-arch"
        meta["current_step"] = "update architecture baseline"
        meta["architect_agent_status"] = "live" if meta.get("architect_agent_id") else meta.get("architect_agent_status")
    elif transition == "arch-approved":
        meta["status"] = "architecture_approved"
        meta["approved_at"] = now_iso()
        meta["next_action"] = "start-plan"
        meta["current_step"] = "architecture approved"


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    meta_path, meta = load_project_meta(workspace, args.project_id)

    meta.setdefault("changed_modules", [])
    meta.setdefault("changed_constraint_refs", [])

    validate_custom_meta_mutations(args.set, args.clear, PROJECT_META_PROTECTED_KEYS, label="Project")

    if args.transition == "arch-updated" and meta.get("status") == "architecture_approved" and not args.restatement:
        if not args.source_task_id:
            raise SystemExit(
                "Semantic update-arch on an approved project requires --source-task-id so the change is grounded in architecture-change-request.md."
            )
        task_meta_path, task_meta = load_meta(workspace, args.source_task_id)
        if task_meta.get("project_id") != meta.get("project_id"):
            raise SystemExit(
                f"Task {task_meta.get('task_id')} belongs to project {task_meta.get('project_id')}, "
                f"not {meta.get('project_id')}."
            )
        request_errors = validate_architecture_change_request(task_meta_path.parent)
        if request_errors:
            raise SystemExit("; ".join(request_errors))

    if args.transition == "arch-approved":
        readiness_errors = validate_project_ready(workspace, meta)
        if readiness_errors:
            raise SystemExit("; ".join(readiness_errors))

    if args.transition:
        apply_transition(meta, args.transition, args.restatement)

    changed_modules = normalize_string_list(args.changed_module) if args.changed_module else normalize_string_list(meta.get("changed_modules"))
    changed_constraints = (
        normalize_string_list(args.changed_constraint_ref)
        if args.changed_constraint_ref
        else normalize_string_list(meta.get("changed_constraint_refs"))
    )
    if args.transition == "arch-updated" and args.restatement and not args.changed_module and not args.changed_constraint_ref:
        changed_modules = []
        changed_constraints = []
    meta["changed_modules"] = changed_modules
    meta["changed_constraint_refs"] = changed_constraints

    for item in args.set:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item}")
        key, raw_value = item.split("=", 1)
        meta[key] = parse_value(raw_value)

    for key in args.clear:
        meta[key] = None

    meta["updated_at"] = now_iso()
    write_json(meta_path, meta)
    affected_task_ids = scan_architecture_drift(workspace, meta)
    for task_id in affected_task_ids:
        write_task_summary(task_dir_for_id(workspace, task_id))
    sync_project_state(workspace, preferred_project_id=meta.get("project_id"))
    sync_workspace_state(workspace)
    write_project_summary(meta_path.parent)
    write_global_summary(workspace)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    print(
        json.dumps(
            {
                "updated": True,
                "meta_path": str(meta_path),
                "meta": meta,
                "affected_task_ids": affected_task_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
