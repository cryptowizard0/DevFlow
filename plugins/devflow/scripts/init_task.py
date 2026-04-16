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

from devflow_lib import (
    create_task_files,
    create_task_worktree,
    ensure_workspace,
    init_meta,
    next_task_id,
    repo_root_for_workspace,
    sync_workspace_state,
    task_dir_for_id,
    write_global_summary,
    write_json,
    write_task_summary,
)


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

    task_id = next_task_id(workspace)
    task_dir = task_dir_for_id(workspace, task_id)
    task_dir.mkdir(parents=True, exist_ok=False)

    create_task_files(task_dir, args.title, args.request, task_id)
    repo_root = repo_root_for_workspace(workspace)
    worktree_path, worktree_branch, worktree_base_ref = create_task_worktree(repo_root, task_id)
    meta = init_meta(
        task_id,
        args.title,
        str(worktree_path),
        worktree_branch,
        worktree_base_ref,
    )
    write_json(task_dir / "meta.json", meta)
    sync_workspace_state(workspace, preferred_focus_task_id=task_id)
    write_task_summary(task_dir)
    write_global_summary(workspace, touched_task_id=task_id)
    meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "created": True,
                "task_id": task_id,
                "task_dir": str(task_dir),
                "worktree_path": str(worktree_path),
                "worktree_branch": worktree_branch,
                "worktree_base_ref": worktree_base_ref,
                "meta": meta,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
