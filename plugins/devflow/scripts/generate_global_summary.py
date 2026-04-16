#!/usr/bin/env python3
"""Generate global summary artifacts for a DevFlow workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import ensure_workspace, write_global_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate global summary files for a DevFlow workspace.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--task-id", help="Optional task ID whose meta should record the summary refresh timestamp.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    json_path, md_path = write_global_summary(workspace, touched_task_id=args.task_id)
    print(f"{json_path}\n{md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
