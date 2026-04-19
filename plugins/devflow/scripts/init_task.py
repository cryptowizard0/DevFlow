#!/usr/bin/env python3
"""Initialize a new DevFlow task."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
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
    normalize_task_architecture_binding,
    next_task_id,
    repo_root_for_workspace,
    sync_workspace_state,
    task_dir_for_id,
    write_global_summary,
    write_json,
    write_task_summary,
)


def cleanup_failed_task_dir(task_dir: Path) -> None:
    if task_dir.exists():
        shutil.rmtree(task_dir)


def cleanup_failed_worktree(repo_root: Path, worktree_path: Path | None, worktree_branch: str | None) -> None:
    if worktree_path and worktree_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    if worktree_branch:
        subprocess.run(
            ["git", "branch", "-D", worktree_branch],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new DevFlow task.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--request", required=True, help="Initial user request text")
    parser.add_argument("--architecture-id", help="Optional architecture package to bind.")
    parser.add_argument("--module-id", help="Optional module id within the architecture package.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    repo_root = repo_root_for_workspace(workspace)

    task_id = next_task_id(workspace)
    task_dir = task_dir_for_id(workspace, task_id)
    task_dir.mkdir(parents=True, exist_ok=False)
    worktree_path: Path | None = None
    worktree_branch: str | None = None

    try:
        binding_preview = {
            "architecture_id": args.architecture_id,
            "module_id": args.module_id,
        }
        architecture_id, module_id, architecture_path = normalize_task_architecture_binding(
            workspace,
            binding_preview,
        )
        create_task_files(task_dir, args.title, args.request, task_id)
        worktree_path, worktree_branch, worktree_base_ref = create_task_worktree(repo_root, task_id)
        meta = init_meta(
            task_id,
            args.title,
            str(worktree_path),
            worktree_branch,
            worktree_base_ref,
            architecture_id=architecture_id,
            module_id=module_id,
            architecture_path=architecture_path,
        )
        write_json(task_dir / "meta.json", meta)
        sync_workspace_state(workspace, preferred_focus_task_id=task_id)
        write_task_summary(task_dir)
        write_global_summary(workspace, touched_task_id=task_id)
        meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        cleanup_failed_task_dir(task_dir)
        cleanup_failed_worktree(repo_root, worktree_path, worktree_branch)
        sync_workspace_state(workspace)
        raise

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
