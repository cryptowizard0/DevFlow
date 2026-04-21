#!/usr/bin/env python3
"""Manage persistent auto-dev orchestration state for a DevFlow task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    allowed_actions_for_meta,
    auto_dev_next_step,
    auto_dev_stop_reason,
    ensure_workspace,
    evaluate_gate,
    load_meta,
    now_iso,
    sync_workspace_state,
    write_global_summary,
    write_json,
    write_task_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start or inspect DevFlow auto-dev mode.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--task-id", help="Task ID. Defaults to the focus task.")
    parser.add_argument(
        "--mode",
        choices=["start", "resume", "inspect"],
        default="start",
        help="Whether to start auto-dev or inspect/resume existing auto-dev state.",
    )
    return parser.parse_args()


def persist_meta(workspace: Path, meta_path: Path, meta: dict[str, object]) -> dict[str, object]:
    task_id = str(meta.get("task_id"))
    meta["updated_at"] = now_iso()
    write_json(meta_path, meta)
    sync_workspace_state(workspace, preferred_focus_task_id=task_id)
    write_task_summary(meta_path.parent)
    write_global_summary(workspace, touched_task_id=task_id)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def build_payload(meta: dict[str, object], requested_mode: str, activation: str) -> dict[str, object]:
    return {
        "ok": True,
        "requested_mode": requested_mode,
        "activation": activation,
        "task_id": meta.get("task_id"),
        "status": meta.get("status"),
        "next_action": meta.get("next_action"),
        "execution_mode": meta.get("execution_mode", "manual"),
        "auto_loop_state": meta.get("auto_loop_state"),
        "should_continue": auto_dev_next_step(meta) is not None,
        "next_step": auto_dev_next_step(meta),
        "stop_reason": auto_dev_stop_reason(meta),
        "is_blocked": meta.get("is_blocked", False),
        "block_reason": meta.get("block_reason"),
        "allowed_actions": allowed_actions_for_meta(meta),
    }


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    meta_path, meta = load_meta(workspace, args.task_id)

    activation = "noop"
    if args.mode == "start":
        gate = evaluate_gate("auto-dev", meta, str(meta.get("task_id")))
        if not gate.allowed:
            print(json.dumps({"ok": False, "gate": gate.to_dict()}, ensure_ascii=False, indent=2))
            return 1

        if meta.get("execution_mode") == "auto_dev" and meta.get("auto_loop_state") == "running":
            activation = "already_running"
        else:
            meta["execution_mode"] = "auto_dev"
            meta["auto_loop_state"] = "running"
            activation = "started"
            meta = persist_meta(workspace, meta_path, meta)
    elif args.mode == "resume":
        activation = "resume_requested"
    else:
        activation = "inspect_only"

    payload = build_payload(meta, args.mode, activation)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
