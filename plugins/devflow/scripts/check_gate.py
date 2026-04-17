#!/usr/bin/env python3
"""Check whether a DevFlow action is currently allowed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import ensure_workspace, evaluate_gate, load_meta, load_project_meta, resolve_task_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate whether a DevFlow action is allowed.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--task-id", help="Target task ID. Defaults to the focus task.")
    parser.add_argument("--project-id", help="Target project ID. Defaults to the active project.")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "start-project",
            "update-arch",
            "approve-arch",
            "start-plan",
            "update-plan",
            "approve-plan",
            "dev",
            "review",
            "done",
            "resume",
        ],
        help="Action to validate",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)

    task_actions = {"update-plan", "approve-plan", "dev", "review", "done", "resume"}
    meta = None
    task_id = None
    if args.action in task_actions:
        task_id = resolve_task_id(workspace, args.task_id)
        if task_id:
            try:
                _, meta = load_meta(workspace, task_id)
            except FileNotFoundError:
                meta = None

    project_meta = None
    project_id = None
    if args.action != "start-project":
        try:
            _, project_meta = load_project_meta(workspace, args.project_id)
            project_id = project_meta.get("project_id")
        except FileNotFoundError:
            project_meta = None
            project_id = None

    result = evaluate_gate(args.action, workspace, meta, task_id, project_meta, project_id)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
