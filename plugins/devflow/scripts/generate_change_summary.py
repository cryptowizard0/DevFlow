#!/usr/bin/env python3
"""Generate change-summary.md from the repo diff and task dev log."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import read_text, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate change-summary.md for a DevFlow task.")
    parser.add_argument("--task-dir", required=True, help="Task directory")
    parser.add_argument("--repo-root", required=True, help="Repository root to inspect")
    return parser.parse_args()


def run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return f"[git {' '.join(args)} failed]\n{completed.stderr.strip()}\n"
    return completed.stdout.strip() or "(no output)"


def main() -> int:
    args = parse_args()
    task_dir = Path(args.task_dir).resolve()
    repo_root = Path(args.repo_root).resolve()
    dev_log = read_text(task_dir / "dev.md").strip() or "No development notes recorded yet."
    status_short = run_git(repo_root, "status", "--short")
    diff_stat = run_git(repo_root, "diff", "--stat")
    cached_diff_stat = run_git(repo_root, "diff", "--cached", "--stat")

    content = "\n".join(
        [
            "# Change Summary",
            "",
            "## Working Tree",
            "",
            "```text",
            status_short,
            "```",
            "",
            "## Unstaged Diff Stat",
            "",
            "```text",
            diff_stat,
            "```",
            "",
            "## Staged Diff Stat",
            "",
            "```text",
            cached_diff_stat,
            "```",
            "",
            "## Development Log Snapshot",
            "",
            "```md",
            dev_log,
            "```",
            "",
        ]
    )
    output_path = task_dir / "change-summary.md"
    write_text(output_path, content)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
