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

from devflow_lib import ensure_workspace, evaluate_gate, load_active_task, load_meta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate whether a DevFlow action is allowed.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--action", required=True, choices=["start", "update-plan", "approve-plan", "dev", "review", "done", "resume"], help="Action to validate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    active = load_active_task(workspace)
    meta = None
    if active.get("task_id"):
        try:
            _, meta = load_meta(workspace, active.get("task_id"))
        except FileNotFoundError:
            meta = None
    result = evaluate_gate(args.action, active, meta)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
