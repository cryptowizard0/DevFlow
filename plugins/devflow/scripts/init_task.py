#!/usr/bin/env python3
"""Initialize a new DevFlow task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import clear_active_task, create_task_files, ensure_workspace, init_meta, load_active_task, next_task_id, save_active_task, task_dir_for_id, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new DevFlow task.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--request", required=True, help="Initial user request text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)

    active = load_active_task(workspace)
    if active.get("task_id") and active.get("status") not in {None, "done"}:
        print(json.dumps({"created": False, "reason": "Another active task already exists.", "active_task": active}, ensure_ascii=False, indent=2))
        return 1

    if active.get("status") == "done":
        clear_active_task(workspace)

    task_id = next_task_id(workspace)
    task_dir = task_dir_for_id(workspace, task_id)
    task_dir.mkdir(parents=True, exist_ok=False)

    create_task_files(task_dir, args.title, args.request, task_id)
    meta = init_meta(task_id, args.title)
    write_json(task_dir / "meta.json", meta)
    save_active_task(
        workspace,
        {
            "task_id": task_id,
            "title": args.title,
            "task_dir": str(task_dir),
            "status": meta["status"],
        },
    )
    print(json.dumps({"created": True, "task_id": task_id, "task_dir": str(task_dir), "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
