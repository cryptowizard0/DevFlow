#!/usr/bin/env python3
"""Render a concise summary of the active DevFlow task."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import ensure_workspace, load_active_task, load_meta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render active task status for DevFlow.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    active = load_active_task(workspace)
    if not active.get("task_id"):
        print("# Resume\n\nNo active task.\n")
        return 0

    _, meta = load_meta(workspace, active.get("task_id"))
    print(
        "\n".join(
            [
                "# Resume",
                "",
                f"- Task ID: `{meta['task_id']}`",
                f"- Title: {meta['title']}",
                f"- Status: `{meta['status']}`",
                f"- Current Step: {meta.get('current_step') or 'n/a'}",
                f"- Last Completed Step: {meta.get('last_completed_step') or 'n/a'}",
                f"- Next Action: {meta.get('next_action') or 'n/a'}",
                f"- Last Review Verdict: {meta.get('last_review_verdict') or 'n/a'}",
                f"- Blocked: {'yes' if meta.get('is_blocked') else 'no'}",
                f"- Block Reason: {meta.get('block_reason') or 'n/a'}",
                f"- Planner Agent: {meta.get('planner_agent_name') or 'n/a'}",
                f"- Planner Agent ID: {meta.get('planner_agent_id') or 'n/a'}",
                f"- Planner Agent Status: {meta.get('planner_agent_status') or 'n/a'}",
                f"- Reviewer Agent: {meta.get('reviewer_agent_name') or 'n/a'}",
                f"- Reviewer Agent ID: {meta.get('reviewer_agent_id') or 'n/a'}",
                f"- Reviewer Agent Status: {meta.get('reviewer_agent_status') or 'n/a'}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
