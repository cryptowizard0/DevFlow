#!/usr/bin/env python3
"""Render a concise summary of the focus DevFlow task and parallel task state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    auto_dev_next_step,
    auto_dev_stop_reason,
    ensure_workspace,
    load_active_tasks,
    load_meta,
    read_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render focus task status for DevFlow.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)
    active_index = load_active_tasks(workspace)
    focus_task_id = active_index.get("focus_task_id")
    if not focus_task_id:
        print("# Resume\n\nNo active task.\n")
        return 0

    _, meta = load_meta(workspace, focus_task_id)
    global_summary = read_json(workspace / "global-summary.json")
    parallel_tasks = [
        entry
        for entry in active_index.get("tasks", [])
        if entry.get("task_id") != focus_task_id
    ]

    lines = [
        "# Resume",
        "",
        f"- Focus Task ID: `{meta['task_id']}`",
        f"- Title: {meta['title']}",
        f"- Stage Status: `{meta['status']}`",
        f"- Current Step: {meta.get('current_step') or 'n/a'}",
        f"- Last Completed Step: {meta.get('last_completed_step') or 'n/a'}",
        f"- Next Action: {meta.get('next_action') or 'n/a'}",
        f"- Execution Mode: {meta.get('execution_mode') or 'manual'}",
        f"- Auto Loop State: {meta.get('auto_loop_state') or 'n/a'}",
        f"- Auto Next Step: {auto_dev_next_step(meta) or 'n/a'}",
        f"- Auto Stop Reason: {auto_dev_stop_reason(meta) or 'n/a'}",
        f"- Last Review Verdict: {meta.get('last_review_verdict') or 'n/a'}",
        f"- Blocked: {'yes' if meta.get('is_blocked') else 'no'}",
        f"- Block Reason: {meta.get('block_reason') or 'n/a'}",
        f"- Active Subagent Role: {meta.get('active_subagent_role') or 'n/a'}",
        f"- Active Subagent Run ID: {meta.get('active_subagent_run_id') or 'n/a'}",
        f"- Active Subagent Name: {meta.get('active_subagent_name') or 'n/a'}",
        f"- Active Subagent ID: {meta.get('active_subagent_id') or 'n/a'}",
        f"- Active Subagent Status: {meta.get('active_subagent_status') or 'n/a'}",
        f"- Active Request Path: {meta.get('active_subagent_request_path') or 'n/a'}",
        f"- Active Result Path: {meta.get('active_subagent_result_path') or 'n/a'}",
        f"- Last Subagent Role: {meta.get('last_subagent_role') or 'n/a'}",
        f"- Last Subagent Run ID: {meta.get('last_subagent_run_id') or 'n/a'}",
        f"- Worktree Path: {meta.get('worktree_path') or 'n/a'}",
        f"- Worktree Branch: {meta.get('worktree_branch') or 'n/a'}",
        f"- Worktree Base Ref: {meta.get('worktree_base_ref') or 'n/a'}",
        f"- Architecture ID: {meta.get('architecture_id') or 'n/a'}",
        f"- Module ID: {meta.get('module_id') or 'n/a'}",
        f"- Architecture Path: {meta.get('architecture_path') or 'n/a'}",
        f"- Global Summary Updated At: {meta.get('global_summary_updated_at') or 'n/a'}",
        f"- Active Task Count: {len(active_index.get('tasks', []))}",
        f"- Architecture Count: {global_summary.get('architecture_count', 0)}",
        f"- Global Summary File: {workspace / 'global-summary.md'}",
        "",
    ]

    if parallel_tasks:
        lines.extend(["## Parallel Tasks", ""])
        for entry in parallel_tasks:
            lines.append(
                f"- `{entry.get('task_id')}` · {entry.get('title') or 'Untitled'} · "
                f"`{entry.get('status')}` · blocked={'yes' if entry.get('is_blocked') else 'no'}"
            )
        lines.append("")

    lines.extend(
        [
            "## Global Summary Snapshot",
            "",
            f"- Updated At: {global_summary.get('updated_at') or 'n/a'}",
            f"- Focus Task: `{global_summary.get('focus_task_id') or 'n/a'}`",
            f"- Active Tasks: {global_summary.get('active_task_count', 0)}",
            f"- Done Tasks: {global_summary.get('done_task_count', 0)}",
            f"- Architectures: {global_summary.get('architecture_count', 0)}",
            f"- Published Architectures: {global_summary.get('published_architecture_count', 0)}",
        ]
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
