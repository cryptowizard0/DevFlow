#!/usr/bin/env python3
"""Create a project scaffold for a legacy workspace and block legacy tasks until architecture binding is added."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    DEFAULT_PROJECT_ID,
    create_project_files,
    ensure_workspace,
    init_project_meta,
    iter_project_meta,
    iter_task_meta,
    repo_root_for_workspace,
    sync_project_state,
    sync_workspace_state,
    write_global_summary,
    write_json,
    write_project_summary,
    write_task_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate a legacy workspace to the architecture-first protocol.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--title", help="Project title. Defaults to the repository name.")
    parser.add_argument(
        "--request",
        default="Bootstrap an architecture-first DevFlow project for this legacy workspace.",
        help="Initial architecture request text.",
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="Project ID. Defaults to PROJECT-001.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    if iter_project_meta(workspace):
        raise SystemExit("Workspace already contains project metadata; migration is not needed.")

    repo_root = repo_root_for_workspace(workspace)
    title = args.title or repo_root.name
    project_dir = workspace / "projects" / args.project_id
    project_dir.mkdir(parents=True, exist_ok=False)
    create_project_files(project_dir, title, args.request, args.project_id)
    project_meta = init_project_meta(args.project_id, title)
    write_json(project_dir / "meta.json", project_meta)

    migrated_task_ids: list[str] = []
    for meta_path, meta in iter_task_meta(workspace):
        meta.setdefault("project_id", args.project_id)
        meta.setdefault("architecture_version", 1)
        meta.setdefault("module_scope", [])
        meta.setdefault("constraint_refs", [])
        meta.setdefault("exception_ids", [])
        meta["architecture_compliance_status"] = "needs_architect_decision"
        if meta.get("status") != "done":
            meta["is_blocked"] = True
            meta["block_reason"] = "Legacy task requires architecture migration."
        meta["updated_at"] = project_meta["updated_at"]
        write_json(meta_path, meta)
        write_task_summary(meta_path.parent)
        migrated_task_ids.append(str(meta.get("task_id")))

    sync_project_state(workspace, preferred_project_id=args.project_id)
    sync_workspace_state(workspace)
    write_project_summary(project_dir)
    write_global_summary(workspace)

    print(
        json.dumps(
            {
                "migrated": True,
                "project_id": args.project_id,
                "project_dir": str(project_dir),
                "migrated_task_ids": migrated_task_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
