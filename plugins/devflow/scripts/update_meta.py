#!/usr/bin/env python3
"""Update DevFlow task metadata through explicit transitions or key assignments."""

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
    load_meta,
    normalize_task_architecture_binding,
    now_iso,
    sync_workspace_state,
    write_global_summary,
    write_json,
    write_task_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update DevFlow meta.json.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--task-id", help="Task ID. Defaults to the focus task.")
    parser.add_argument(
        "--transition",
        choices=[
            "plan-updated",
            "plan-approved",
            "dev-started",
            "review-started",
            "review-pass",
            "review-changes-requested",
            "review-blocked",
            "task-done",
            "clear-block",
        ],
        help="Named state transition to apply before custom fields.",
    )
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Set a JSON-like value on meta.json. VALUE is parsed as JSON when possible.")
    parser.add_argument("--clear", action="append", default=[], metavar="KEY", help="Clear a key by setting it to null.")
    return parser.parse_args()


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_transition(meta: dict[str, Any], transition: str) -> None:
    if transition == "plan-updated":
        meta["status"] = "planning"
        meta["plan_version"] = int(meta.get("plan_version", 0)) + 1
        meta["next_action"] = "approve-plan"
        meta["approved_at"] = None
        meta["approved_by"] = None
        meta["is_blocked"] = False
        meta["block_reason"] = None
        meta["planner_agent_status"] = "live" if meta.get("planner_agent_id") else None
    elif transition == "plan-approved":
        meta["status"] = "plan_approved"
        meta["approved_at"] = now_iso()
        meta["next_action"] = "dev"
        meta["is_blocked"] = False
        meta["block_reason"] = None
    elif transition == "dev-started":
        meta["status"] = "developing"
        meta["next_action"] = "dev"
        meta["is_blocked"] = False
        meta["block_reason"] = None
    elif transition == "review-started":
        meta["status"] = "reviewing"
        meta["review_round"] = int(meta.get("review_round", 0)) + 1
        meta["next_action"] = "await_review_result"
        meta["reviewer_agent_status"] = "live" if meta.get("reviewer_agent_id") else None
    elif transition == "review-pass":
        timestamp = now_iso()
        meta["status"] = "developing"
        meta["last_review_verdict"] = "pass"
        meta["last_reviewed_at"] = timestamp
        meta["review_passed_at"] = timestamp
        meta["next_action"] = "done"
        meta["is_blocked"] = False
        meta["block_reason"] = None
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else None
    elif transition == "review-changes-requested":
        meta["status"] = "developing"
        meta["last_review_verdict"] = "changes_requested"
        meta["last_reviewed_at"] = now_iso()
        meta["next_action"] = "dev"
        meta["is_blocked"] = False
        meta["block_reason"] = None
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else None
    elif transition == "review-blocked":
        meta["status"] = "developing"
        meta["last_review_verdict"] = "blocked"
        meta["last_reviewed_at"] = now_iso()
        meta["next_action"] = "review"
        meta["is_blocked"] = True
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else None
    elif transition == "task-done":
        meta["status"] = "done"
        meta["next_action"] = None
        meta["completed_at"] = now_iso()
        meta["is_blocked"] = False
        meta["block_reason"] = None
        meta["planner_agent_status"] = "stale" if meta.get("planner_agent_id") else meta.get("planner_agent_status")
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else meta.get("reviewer_agent_status")
    elif transition == "clear-block":
        meta["is_blocked"] = False
        meta["block_reason"] = None


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    meta_path, meta = load_meta(workspace, args.task_id)
    task_id = meta.get("task_id")

    if args.transition:
        apply_transition(meta, args.transition)

    for item in args.set:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item}")
        key, raw_value = item.split("=", 1)
        meta[key] = parse_value(raw_value)

    for key in args.clear:
        meta[key] = None

    normalize_task_architecture_binding(workspace, meta)

    meta["updated_at"] = now_iso()
    write_json(meta_path, meta)
    preferred_focus_task_id = None if meta.get("status") == "done" else task_id
    sync_workspace_state(workspace, preferred_focus_task_id=preferred_focus_task_id)
    write_task_summary(meta_path.parent)
    write_global_summary(workspace, touched_task_id=task_id)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    print(json.dumps({"updated": True, "meta_path": str(meta_path), "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
