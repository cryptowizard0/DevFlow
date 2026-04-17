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
    now_iso,
    normalize_string_list,
    parse_review_verdicts,
    TASK_META_PROTECTED_KEYS,
    sync_workspace_state,
    validate_custom_meta_mutations,
    write_global_summary,
    write_json,
    read_text,
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
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Set a JSON-like value on meta.json. VALUE is parsed as JSON when possible. File-backed and transition-managed keys are protected.")
    parser.add_argument("--clear", action="append", default=[], metavar="KEY", help="Clear a key by setting it to null. File-backed and transition-managed keys are protected.")
    return parser.parse_args()


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def derive_architecture_compliance_status(meta: dict[str, Any], architecture_verdict: str) -> str:
    if architecture_verdict == "compliant":
        return "approved_exception" if normalize_string_list(meta.get("exception_ids")) else "compliant"
    if architecture_verdict == "deviation":
        return "deviation"
    if architecture_verdict == "needs_architect_decision":
        return "needs_architect_decision"
    raise SystemExit(f"Unsupported architecture_verdict: {architecture_verdict}")


def validate_review_transition(
    transition: str,
    implementation_verdict: str | None,
    architecture_verdict: str | None,
) -> tuple[str, str]:
    if implementation_verdict not in {"pass", "changes_requested", "blocked"}:
        raise SystemExit("review.md must define implementation_verdict: pass | changes_requested | blocked.")
    if architecture_verdict not in {"compliant", "deviation", "needs_architect_decision"}:
        raise SystemExit("review.md must define architecture_verdict: compliant | deviation | needs_architect_decision.")

    expected_implementation_verdict = {
        "review-pass": "pass",
        "review-changes-requested": "changes_requested",
        "review-blocked": "blocked",
    }.get(transition)
    if expected_implementation_verdict and implementation_verdict != expected_implementation_verdict:
        raise SystemExit(
            f"Transition {transition} requires implementation_verdict={expected_implementation_verdict}, "
            f"but review.md says {implementation_verdict}."
        )

    if transition == "review-pass" and architecture_verdict != "compliant":
        raise SystemExit("review-pass requires architecture_verdict=compliant in review.md.")

    return implementation_verdict, architecture_verdict


def apply_transition(
    meta: dict[str, Any],
    transition: str,
    implementation_verdict: str | None = None,
    architecture_verdict: str | None = None,
) -> None:
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
        meta["architecture_compliance_status"] = derive_architecture_compliance_status(meta, str(architecture_verdict))
        meta["status"] = "developing"
        meta["last_review_verdict"] = str(implementation_verdict)
        meta["last_reviewed_at"] = timestamp
        meta["review_passed_at"] = timestamp
        meta["next_action"] = "done"
        meta["is_blocked"] = False
        meta["block_reason"] = None
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else None
    elif transition == "review-changes-requested":
        compliance_status = derive_architecture_compliance_status(meta, str(architecture_verdict))
        architecture_blocked = compliance_status in {"deviation", "needs_architect_decision"}
        meta["architecture_compliance_status"] = compliance_status
        meta["status"] = "developing"
        meta["last_review_verdict"] = str(implementation_verdict)
        meta["last_reviewed_at"] = now_iso()
        meta["next_action"] = "dev"
        meta["is_blocked"] = architecture_blocked
        if compliance_status == "needs_architect_decision":
            meta["block_reason"] = "Architecture review requires an Architect decision."
        elif compliance_status == "deviation":
            meta["block_reason"] = "Architecture deviation must be resolved before development continues."
        else:
            meta["block_reason"] = None
        meta["reviewer_agent_status"] = "stale" if meta.get("reviewer_agent_id") else None
    elif transition == "review-blocked":
        compliance_status = derive_architecture_compliance_status(meta, str(architecture_verdict))
        meta["architecture_compliance_status"] = compliance_status
        meta["status"] = "developing"
        meta["last_review_verdict"] = str(implementation_verdict)
        meta["last_reviewed_at"] = now_iso()
        meta["next_action"] = "review"
        meta["is_blocked"] = True
        if compliance_status == "needs_architect_decision":
            meta["block_reason"] = "Architecture review requires an Architect decision."
        elif compliance_status == "deviation":
            meta["block_reason"] = "Architecture deviation must be resolved before development continues."
        else:
            meta["block_reason"] = meta.get("block_reason") or "Review blocked."
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

    meta.setdefault("project_id", None)
    meta.setdefault("architecture_version", None)
    meta.setdefault("module_scope", [])
    meta.setdefault("constraint_refs", [])
    meta.setdefault("exception_ids", [])
    meta.setdefault("architecture_compliance_status", "pending")

    implementation_verdict = None
    architecture_verdict = None
    if args.transition in {"review-pass", "review-changes-requested", "review-blocked"}:
        implementation_verdict, architecture_verdict = parse_review_verdicts(
            read_text(meta_path.parent / "review.md")
        )
        implementation_verdict, architecture_verdict = validate_review_transition(
            args.transition,
            implementation_verdict,
            architecture_verdict,
        )

    if args.transition:
        apply_transition(meta, args.transition, implementation_verdict, architecture_verdict)

    validate_custom_meta_mutations(args.set, args.clear, TASK_META_PROTECTED_KEYS, label="Task")

    for item in args.set:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item}")
        key, raw_value = item.split("=", 1)
        meta[key] = parse_value(raw_value)

    for key in args.clear:
        meta[key] = None

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
