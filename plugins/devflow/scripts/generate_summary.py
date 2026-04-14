#!/usr/bin/env python3
"""Generate summary.md for a completed or ready-to-complete DevFlow task."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import read_json, read_text, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate summary.md for a DevFlow task.")
    parser.add_argument("--task-dir", required=True, help="Task directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_dir = Path(args.task_dir).resolve()
    meta = read_json(task_dir / "meta.json")
    request_text = read_text(task_dir / "request.md").strip()
    plan_text = read_text(task_dir / "plan.md").strip()
    dev_text = read_text(task_dir / "dev.md").strip()
    review_text = read_text(task_dir / "review.md").strip()

    content = "\n".join(
        [
            "# Summary",
            "",
            f"- Task ID: `{meta.get('task_id')}`",
            f"- Title: {meta.get('title')}",
            f"- Status: `{meta.get('status')}`",
            f"- Last Review Verdict: {meta.get('last_review_verdict') or 'n/a'}",
            f"- Completed At: {meta.get('completed_at') or 'n/a'}",
            "",
            "## Request Snapshot",
            "",
            "```md",
            request_text or "(empty)",
            "```",
            "",
            "## Plan Snapshot",
            "",
            "```md",
            plan_text or "(empty)",
            "```",
            "",
            "## Development Snapshot",
            "",
            "```md",
            dev_text or "(empty)",
            "```",
            "",
            "## Review Snapshot",
            "",
            "```md",
            review_text or "(empty)",
            "```",
            "",
        ]
    )
    output_path = task_dir / "summary.md"
    write_text(output_path, content)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
