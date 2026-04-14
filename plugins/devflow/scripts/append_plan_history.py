#!/usr/bin/env python3
"""Append the current plan snapshot to plan-history.md."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import now_iso, read_text, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append a plan snapshot to plan-history.md.")
    parser.add_argument("--task-dir", required=True, help="Task directory")
    parser.add_argument("--reason", required=True, help="Reason for the plan update")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_dir = Path(args.task_dir).resolve()
    plan_path = task_dir / "plan.md"
    history_path = task_dir / "plan-history.md"

    if not plan_path.exists():
        raise SystemExit(f"Missing plan file: {plan_path}")

    plan_content = read_text(plan_path).rstrip()
    history = read_text(history_path).rstrip()
    if not history:
        history = "# Plan History"

    entry = (
        f"\n\n## Snapshot {now_iso()}\n\n"
        f"- Reason: {args.reason}\n\n"
        f"```md\n{plan_content}\n```\n"
    )
    write_text(history_path, history + entry + "\n")
    print(str(history_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
