#!/usr/bin/env python3
"""Initialize a new DevFlow project architecture baseline."""

from __future__ import annotations

import argparse
import json
import shutil
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
    load_active_project,
    project_dir_for_id,
    sync_project_state,
    write_global_summary,
    write_json,
    write_project_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new DevFlow project.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--title", required=True, help="Project title")
    parser.add_argument("--request", required=True, help="Initial architecture request text")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="Project ID. Defaults to PROJECT-001.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    active_project = load_active_project(workspace)
    if active_project.get("project_id"):
        raise SystemExit(f"Workspace already has an active project: {active_project['project_id']}")

    project_dir = project_dir_for_id(workspace, args.project_id)
    if project_dir.exists():
        raise SystemExit(f"Project directory already exists: {project_dir}")

    try:
        project_dir.mkdir(parents=True, exist_ok=False)
        create_project_files(project_dir, args.title, args.request, args.project_id)
        meta = init_project_meta(args.project_id, args.title)
        write_json(project_dir / "meta.json", meta)
        sync_project_state(workspace, preferred_project_id=args.project_id)
        write_project_summary(project_dir)
        write_global_summary(workspace)
        meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        sync_project_state(workspace)
        raise

    print(
        json.dumps(
            {
                "created": True,
                "project_id": args.project_id,
                "project_dir": str(project_dir),
                "meta": meta,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
